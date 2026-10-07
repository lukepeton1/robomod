#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <iterator>

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <Windows.h>

#include <DynamicOutput/Output.hpp>
#include <File/Macros.hpp>
#include <Mod/CppUserModBase.hpp>
#include <Unreal/CoreUObject/UObject/Class.hpp>
#include <Unreal/CoreUObject/UObject/UnrealType.hpp>
#include <Unreal/UObject.hpp>
#include <Unreal/UObjectGlobals.hpp>

#include "momentum_core.hpp"
#include "momentum_runtime_fingerprint.hpp"

namespace MomentumOverhaul
{
using namespace RC;
using namespace RC::Unreal;

namespace
{
using CalcVelocityFn = void (*)(UObject*, float, float, bool, float);

constexpr std::uint8_t MOVE_Walking = 1;
constexpr std::uint8_t MOVE_NavWalking = 2;
constexpr std::uint8_t MOVE_Falling = 3;
constexpr std::uint8_t MOVE_Custom = 6;

struct RuntimeTuning
{
    double ground_wish_speed{1050.0};
    double ground_acceleration{12.0};
    double ground_friction{7.0};
    double ground_stop_speed{220.0};
    double air_acceleration{12.0};
    double air_directional_wish_cap{320.0};
    double air_soft_speed_threshold{5000.0};
    double air_soft_damping{0.15};
    double slide_friction{1.15};
    double slide_steering_acceleration{3.5};
    double absolute_speed_limit{12000.0};
};

RuntimeTuning g_tuning{};
CalcVelocityFn g_original_calc_velocity{};
void** g_character_movement_vtable{};
UClass* g_roboquest_movement_class{};
UClass* g_character_player_class{};

FProperty* g_velocity_property{};
FProperty* g_acceleration_property{};
FProperty* g_movement_mode_property{};
FProperty* g_character_owner_property{};
FProperty* g_max_walk_speed_property{};
FProperty* g_max_acceleration_property{};
FProperty* g_power_slide_rate_property{};
FBoolProperty* g_is_dashing_property{};

std::atomic<std::uint64_t> g_target_hook_calls{0};
std::atomic_bool g_hook_installed{false};

[[nodiscard]] auto executable_build_fingerprint_matches() -> bool
{
    auto* module = reinterpret_cast<const std::uint8_t*>(GetModuleHandleW(nullptr));
    if (!module) return false;

    const auto* dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(module);
    if (dos->e_magic != IMAGE_DOS_SIGNATURE || dos->e_lfanew <= 0) return false;

    const auto* nt = reinterpret_cast<const IMAGE_NT_HEADERS64*>(module + dos->e_lfanew);
    if (nt->Signature != IMAGE_NT_SIGNATURE ||
        nt->FileHeader.TimeDateStamp != runtime_fingerprint::expected_coff_timestamp)
    {
        return false;
    }

    wchar_t path[MAX_PATH]{};
    const DWORD length = GetModuleFileNameW(nullptr, path, static_cast<DWORD>(std::size(path)));
    if (length == 0 || length >= std::size(path)) return false;

    WIN32_FILE_ATTRIBUTE_DATA attrs{};
    if (!GetFileAttributesExW(path, GetFileExInfoStandard, &attrs)) return false;

    ULARGE_INTEGER file_size{};
    file_size.HighPart = attrs.nFileSizeHigh;
    file_size.LowPart = attrs.nFileSizeLow;
    return file_size.QuadPart == runtime_fingerprint::expected_executable_file_size;
}

[[nodiscard]] auto read_bool(FBoolProperty* property, UObject* container) -> bool
{
    if (!property || !container) return false;
    auto* storage = property->ContainerPtrToValuePtr<std::uint8_t>(container);
    return storage && ((*storage & property->GetFieldMask()) != 0);
}

[[nodiscard]] auto reflected_float(FProperty* property, UObject* container) -> float*
{
    return property && container ? property->ContainerPtrToValuePtr<float>(container) : nullptr;
}

[[nodiscard]] auto reflected_byte(FProperty* property, UObject* container) -> std::uint8_t*
{
    return property && container ? property->ContainerPtrToValuePtr<std::uint8_t>(container) : nullptr;
}

[[nodiscard]] auto reflected_vector(FProperty* property, UObject* container) -> FVector*
{
    return property && container ? property->ContainerPtrToValuePtr<FVector>(container) : nullptr;
}

[[nodiscard]] auto reflected_object(FProperty* property, UObject* container) -> UObject*
{
    if (!property || !container) return nullptr;
    auto** value = property->ContainerPtrToValuePtr<UObject*>(container);
    return value ? *value : nullptr;
}

[[nodiscard]] auto to_vec(const FVector& value) -> momentum::Vec3
{
    return {
        static_cast<double>(value.X()),
        static_cast<double>(value.Y()),
        static_cast<double>(value.Z()),
    };
}

auto write_vec(FVector& target, const momentum::Vec3& value) -> void
{
    target.X() = static_cast<float>(value.x);
    target.Y() = static_cast<float>(value.y);
    target.Z() = static_cast<float>(value.z);
}

[[nodiscard]] auto input_scale(const momentum::Vec3& acceleration, float* max_acceleration) -> double
{
    const double magnitude = acceleration.horizontal_speed();
    if (magnitude <= 1.0e-6) return 0.0;
    if (max_acceleration && std::isfinite(*max_acceleration) && *max_acceleration > 1.0f)
    {
        return std::clamp(magnitude / static_cast<double>(*max_acceleration), 0.0, 1.0);
    }
    return 1.0;
}

[[nodiscard]] auto live_ground_wish_speed(float* max_walk_speed) -> double
{
    if (max_walk_speed && std::isfinite(*max_walk_speed) && *max_walk_speed > 1.0f)
    {
        return static_cast<double>(*max_walk_speed);
    }
    return g_tuning.ground_wish_speed;
}

[[nodiscard]] auto is_target_component(UObject* movement_component, UObject*& owner) -> bool
{
    if (!movement_component || !g_roboquest_movement_class || !g_character_player_class) return false;
    if (!movement_component->IsA(g_roboquest_movement_class)) return false;
    owner = reflected_object(g_character_owner_property, movement_component);
    return owner && owner->IsA(g_character_player_class);
}

auto momentum_calc_velocity(
    UObject* movement_component,
    float delta_time,
    float friction,
    bool fluid,
    float braking_deceleration) -> void
{
    auto original = g_original_calc_velocity;
    if (!original) return;

    UObject* owner{};
    if (!is_target_component(movement_component, owner) ||
        !std::isfinite(delta_time) || delta_time <= 0.0f || delta_time > 0.25f)
    {
        original(movement_component, delta_time, friction, fluid, braking_deceleration);
        return;
    }

    auto* velocity = reflected_vector(g_velocity_property, movement_component);
    auto* acceleration = reflected_vector(g_acceleration_property, movement_component);
    auto* movement_mode = reflected_byte(g_movement_mode_property, movement_component);
    if (!velocity || !acceleration || !movement_mode)
    {
        original(movement_component, delta_time, friction, fluid, braking_deceleration);
        return;
    }

    // Keep Grapple (MOVE_Custom) and Dash fully vanilla in the first runtime milestone.
    if (*movement_mode == MOVE_Custom || read_bool(g_is_dashing_property, owner))
    {
        original(movement_component, delta_time, friction, fluid, braking_deceleration);
        return;
    }

    const auto pre_velocity = to_vec(*velocity);
    const auto wish = to_vec(*acceleration);
    const auto pre_mode = *movement_mode;
    auto* max_walk_speed = reflected_float(g_max_walk_speed_property, movement_component);
    auto* max_acceleration = reflected_float(g_max_acceleration_property, movement_component);
    auto* power_slide_rate = reflected_float(g_power_slide_rate_property, owner);

    // Run vanilla first so requested-move state and native side effects still happen.
    original(movement_component, delta_time, friction, fluid, braking_deceleration);
    const double vanilla_post_z = static_cast<double>(velocity->Z());

    momentum::Vec3 result = pre_velocity;
    const double analog = input_scale(wish, max_acceleration);
    const double ground_wish_speed = live_ground_wish_speed(max_walk_speed) * analog;
    const bool sliding = power_slide_rate && *power_slide_rate > 1.0e-4f;

    if (pre_mode == MOVE_Walking || pre_mode == MOVE_NavWalking)
    {
        if (sliding)
        {
            result = momentum::apply_slide_friction(
                result, g_tuning.slide_friction, static_cast<double>(delta_time));
            result = momentum::accelerate_horizontal(
                result, wish, ground_wish_speed,
                g_tuning.slide_steering_acceleration, static_cast<double>(delta_time));
        }
        else
        {
            result = momentum::apply_ground_friction(
                result, g_tuning.ground_friction,
                g_tuning.ground_stop_speed, static_cast<double>(delta_time));
            result = momentum::accelerate_horizontal(
                result, wish, ground_wish_speed,
                g_tuning.ground_acceleration, static_cast<double>(delta_time));
        }
    }
    else if (pre_mode == MOVE_Falling)
    {
        const double air_wish_speed =
            std::min(live_ground_wish_speed(max_walk_speed), g_tuning.air_directional_wish_cap) * analog;
        result = momentum::accelerate_horizontal(
            result, wish, air_wish_speed,
            g_tuning.air_acceleration, static_cast<double>(delta_time));
        result = momentum::soft_high_speed_damping(
            result, g_tuning.air_soft_speed_threshold,
            g_tuning.air_soft_damping, static_cast<double>(delta_time));
    }
    else
    {
        return;
    }

    // Vertical velocity remains entirely Roboquest/Unreal-owned in this milestone.
    result.z = vanilla_post_z;
    result = momentum::safety_clamp(result, g_tuning.absolute_speed_limit);
    write_vec(*velocity, result);

    const auto sample = g_target_hook_calls.fetch_add(1, std::memory_order_relaxed);
    if (sample < 16)
    {
        Output::send<LogLevel::Verbose>(
            STR("[MomentumOverhaul] sample={} mode={} slide={} dt={} pre=({}, {}, {}) wish=({}, {}) out=({}, {}, {})\n"),
            sample, static_cast<unsigned>(pre_mode), sliding, delta_time,
            pre_velocity.x, pre_velocity.y, pre_velocity.z,
            wish.x, wish.y, result.x, result.y, result.z);
    }
}

[[nodiscard]] auto patch_vtable_slot(
    void** vtable, std::size_t slot, void* replacement, void*& previous) -> bool
{
    if (!vtable || !replacement) return false;
    auto* address = &vtable[slot];

    DWORD old_protect{};
    if (!VirtualProtect(address, sizeof(void*), PAGE_READWRITE, &old_protect)) return false;

    previous = InterlockedExchangePointer(
        reinterpret_cast<PVOID volatile*>(address),
        reinterpret_cast<PVOID>(replacement));

    DWORD ignored{};
    VirtualProtect(address, sizeof(void*), old_protect, &ignored);
    return previous != nullptr;
}

auto restore_vtable_slot() -> void
{
    if (!g_hook_installed.load(std::memory_order_acquire) ||
        !g_character_movement_vtable || !g_original_calc_velocity)
    {
        return;
    }

    auto* address =
        &g_character_movement_vtable[runtime_fingerprint::calc_velocity_vtable_slot];

    // Never overwrite a hook that another mod installed after Momentum.
    if (*address != reinterpret_cast<void*>(&momentum_calc_velocity))
    {
        Output::send<LogLevel::Warning>(
            STR("[MomentumOverhaul] CalcVelocity slot changed after install; leaving it untouched on unload.\n"));
        return;
    }

    DWORD old_protect{};
    if (VirtualProtect(address, sizeof(void*), PAGE_READWRITE, &old_protect))
    {
        InterlockedExchangePointer(
            reinterpret_cast<PVOID volatile*>(address),
            reinterpret_cast<PVOID>(g_original_calc_velocity));
        DWORD ignored{};
        VirtualProtect(address, sizeof(void*), old_protect, &ignored);
        g_hook_installed.store(false, std::memory_order_release);
        Output::send<LogLevel::Verbose>(
            STR("[MomentumOverhaul] CalcVelocity hook restored.\n"));
    }
}

[[nodiscard]] auto find_movement_exemplar() -> UObject*
{
    UObject* exemplar{};
    UObjectGlobals::ForEachUObject(
        [&](void* raw, [[maybe_unused]] int32_t chunk_index, [[maybe_unused]] int32_t object_index)
        {
            if (exemplar || !raw) return;
            auto* object = static_cast<UObject*>(raw);
            if (object->IsA(g_roboquest_movement_class)) exemplar = object;
        });
    return exemplar;
}

[[nodiscard]] auto cache_reflected_properties() -> bool
{
    g_velocity_property = g_roboquest_movement_class->GetPropertyByNameInChain(STR("Velocity"));
    g_acceleration_property = g_roboquest_movement_class->GetPropertyByNameInChain(STR("Acceleration"));
    g_movement_mode_property = g_roboquest_movement_class->GetPropertyByNameInChain(STR("MovementMode"));
    g_character_owner_property = g_roboquest_movement_class->GetPropertyByNameInChain(STR("CharacterOwner"));
    g_max_walk_speed_property = g_roboquest_movement_class->GetPropertyByNameInChain(STR("MaxWalkSpeed"));
    g_max_acceleration_property = g_roboquest_movement_class->GetPropertyByNameInChain(STR("MaxAcceleration"));
    g_power_slide_rate_property = g_character_player_class->GetPropertyByNameInChain(STR("PowerSlideRate"));
    g_is_dashing_property = CastField<FBoolProperty>(
        g_character_player_class->GetPropertyByNameInChain(STR("bIsDashing")));

    return g_velocity_property && g_acceleration_property && g_movement_mode_property &&
           g_character_owner_property && g_max_walk_speed_property &&
           g_max_acceleration_property && g_power_slide_rate_property &&
           g_is_dashing_property;
}

[[nodiscard]] auto install_calc_velocity_hook() -> bool
{
    if (g_hook_installed.load(std::memory_order_acquire)) return true;

    if (!executable_build_fingerprint_matches())
    {
        Output::send<LogLevel::Error>(
            STR("[MomentumOverhaul] executable build fingerprint mismatch; hook disabled.\n"));
        return false;
    }

    g_roboquest_movement_class = UObjectGlobals::StaticFindObject<UClass*>(
        nullptr, nullptr, STR("/Script/RoboQuest.RoboquestMovementComponent"));
    g_character_player_class = UObjectGlobals::StaticFindObject<UClass*>(
        nullptr, nullptr, STR("/Script/RoboQuest.Character_Player"));

    if (!g_roboquest_movement_class || !g_character_player_class)
    {
        Output::send<LogLevel::Error>(
            STR("[MomentumOverhaul] required Roboquest classes are not loaded.\n"));
        return false;
    }
    if (!cache_reflected_properties())
    {
        Output::send<LogLevel::Error>(
            STR("[MomentumOverhaul] reflected property contract mismatch.\n"));
        return false;
    }

    auto* exemplar = find_movement_exemplar();
    if (!exemplar)
    {
        Output::send<LogLevel::Error>(
            STR("[MomentumOverhaul] no RoboquestMovementComponent exemplar found.\n"));
        return false;
    }

    auto*** object_as_vtable = reinterpret_cast<void***>(exemplar);
    if (!object_as_vtable || !*object_as_vtable) return false;
    g_character_movement_vtable = *object_as_vtable;

    const auto module_base =
        reinterpret_cast<std::uintptr_t>(GetModuleHandleW(nullptr));
    const auto expected = reinterpret_cast<void*>(
        module_base + runtime_fingerprint::calc_velocity_function_rva);
    const auto observed =
        g_character_movement_vtable[runtime_fingerprint::calc_velocity_vtable_slot];

    if (observed != expected)
    {
        Output::send<LogLevel::Error>(
            STR("[MomentumOverhaul] slot {} fingerprint mismatch: observed={} expected={}.\n"),
            runtime_fingerprint::calc_velocity_vtable_slot, observed, expected);
        return false;
    }

    g_original_calc_velocity = reinterpret_cast<CalcVelocityFn>(observed);

    void* previous{};
    if (!patch_vtable_slot(
            g_character_movement_vtable,
            runtime_fingerprint::calc_velocity_vtable_slot,
            reinterpret_cast<void*>(&momentum_calc_velocity),
            previous))
    {
        g_original_calc_velocity = nullptr;
        Output::send<LogLevel::Error>(
            STR("[MomentumOverhaul] vtable swap failed; vanilla remains active.\n"));
        return false;
    }

    if (previous != observed)
    {
        DWORD old_protect{};
        auto* address =
            &g_character_movement_vtable[runtime_fingerprint::calc_velocity_vtable_slot];
        if (VirtualProtect(address, sizeof(void*), PAGE_READWRITE, &old_protect))
        {
            InterlockedExchangePointer(
                reinterpret_cast<PVOID volatile*>(address),
                reinterpret_cast<PVOID>(previous));
            DWORD ignored{};
            VirtualProtect(address, sizeof(void*), old_protect, &ignored);
        }
        g_original_calc_velocity = nullptr;
        Output::send<LogLevel::Error>(
            STR("[MomentumOverhaul] slot changed during install; hook aborted.\n"));
        return false;
    }

    g_hook_installed.store(true, std::memory_order_release);
    Output::send<LogLevel::Verbose>(
        STR("[MomentumOverhaul] CalcVelocity hook installed: slot={} displacement=0x{:X} target_rva=0x{:X}.\n"),
        runtime_fingerprint::calc_velocity_vtable_slot,
        runtime_fingerprint::calc_velocity_vtable_displacement,
        runtime_fingerprint::calc_velocity_function_rva);
    return true;
}
}

class MomentumOverhaulMod final : public CppUserModBase
{
public:
    MomentumOverhaulMod()
    {
        ModName = STR("MomentumOverhaul");
        ModVersion = STR("0.1.0-alpha");
        ModAuthors = STR("robomod");
        ModDescription = STR("Momentum-first Roboquest movement overhaul runtime core.");
        Output::send<LogLevel::Verbose>(
            STR("[MomentumOverhaul] runtime mod loaded.\n"));
    }

    ~MomentumOverhaulMod() override
    {
        restore_vtable_slot();
    }

    auto on_unreal_init() -> void override
    {
        if (!install_calc_velocity_hook())
        {
            Output::send<LogLevel::Error>(
                STR("[MomentumOverhaul] runtime core disabled; vanilla movement untouched.\n"));
        }
    }
};
}

#define MOD_EXPORT __declspec(dllexport)
extern "C"
{
MOD_EXPORT RC::CppUserModBase* start_mod()
{
    return new MomentumOverhaul::MomentumOverhaulMod();
}

MOD_EXPORT void uninstall_mod(RC::CppUserModBase* mod)
{
    delete mod;
}
}
