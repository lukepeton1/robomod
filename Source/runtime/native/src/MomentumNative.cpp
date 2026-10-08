// Roboquest Momentum native bridge.
//
// A UE4SS Lua mod supplies reflected UClass / CDO pointers. This DLL does not
// depend on UE4SS headers or libraries, so it can be built from public sources.
// Any game pointer/offset below is valid ONLY for the fingerprinted shipping build.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <Windows.h>
#include <wincrypt.h>
#include <algorithm>
#include <array>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <cstddef>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <mutex>
#include <sstream>
#include <string>
#include <vector>

#include "../../momentum_core.hpp"
#include "../include/momentum_native_layout.hpp"

#pragma comment(lib, "advapi32.lib")

namespace momentum_native {

namespace layout = momentum_native_layout;
using CalcVelocity = void (*)(void*, float, float, bool, float);

struct FVector3f {
    float x{};
    float y{};
    float z{};
};
static_assert(sizeof(FVector3f) == 12);

struct Config {
    bool active{false}; // Observe-only until user explicitly enables movement edits.
    double ground_speed{1050.0};
    double ground_acceleration{12.0};
    double ground_friction{7.0};
    double stop_speed{220.0};
    double air_acceleration{12.0};
    double air_wish_cap{320.0};
    double air_soft_threshold{5000.0};
    double air_soft_damping{0.15};
    double slide_friction{1.15};
    double slide_acceleration{3.5};
    double absolute_cap{12000.0};
};

static HMODULE g_library{};
static std::filesystem::path g_mod_root{};
static std::mutex g_log_mutex{};
static std::atomic<std::uint64_t> g_target_calls{0};
static std::atomic<int> g_last_movement_mode{-1};
static std::atomic<int> g_last_dash{-1};
static std::atomic<bool> g_installed{false};
static std::atomic<bool> g_slide_active{false};
static CalcVelocity g_original{};
static void** g_vtable{};
static void* g_movement_class{};
static void* g_player_class{};
static Config g_config{};

template <class T>
T& at(void* object, std::size_t offset) noexcept {
    return *reinterpret_cast<T*>(reinterpret_cast<unsigned char*>(object) + offset);
}

std::string trim(std::string value) {
    auto nonspace = [](unsigned char c) {
        return c != ' ' && c != '\t' && c != '\r' && c != '\n';
    };
    const auto first = std::find_if(value.begin(), value.end(), nonspace);
    if (first == value.end()) return {};
    const auto last = std::find_if(value.rbegin(), value.rend(), nonspace).base();
    return std::string(first, last);
}

std::string timestamp() {
    SYSTEMTIME t{};
    GetLocalTime(&t);
    char result[64]{};
    std::snprintf(result, sizeof(result),
                  "%04u-%02u-%02uT%02u:%02u:%02u.%03u",
                  t.wYear, t.wMonth, t.wDay,
                  t.wHour, t.wMinute, t.wSecond, t.wMilliseconds);
    return result;
}

void log(const std::string& message) {
    OutputDebugStringA(("[MomentumOverhaul] " + message + "\n").c_str());
    if (g_mod_root.empty()) return;
    std::lock_guard<std::mutex> lock(g_log_mutex);
    std::ofstream output(g_mod_root / "momentum-runtime.log", std::ios::app);
    if (output) output << timestamp() << " " << message << '\n';
}

void write_status(const std::string& message) {
    if (g_mod_root.empty()) return;
    std::ofstream output(g_mod_root / "runtime-status.txt", std::ios::trunc);
    if (output) output << message << '\n';
    log(message);
}

bool valid_readable_address(const void* p) {
    if (!p || reinterpret_cast<std::uintptr_t>(p) < 0x10000) return false;
    MEMORY_BASIC_INFORMATION mbi{};
    if (!VirtualQuery(p, &mbi, sizeof(mbi)) || mbi.State != MEM_COMMIT) return false;
    if (mbi.Protect & (PAGE_NOACCESS | PAGE_GUARD)) return false;
    return true;
}

bool is_instance_of(void* object, void* wanted_class) {
    if (!valid_readable_address(object) || !valid_readable_address(wanted_class)) return false;
    void* klass = at<void*>(object, layout::uobject_class_private);
    for (int i = 0; i < 64 && valid_readable_address(klass); ++i) {
        if (klass == wanted_class) return true;
        klass = at<void*>(klass, layout::ustruct_super);
    }
    return false;
}

std::filesystem::path executable_path() {
    std::wstring path(32768, L'\0');
    const DWORD n = GetModuleFileNameW(nullptr, path.data(), static_cast<DWORD>(path.size()));
    if (!n || n >= path.size()) return {};
    path.resize(n);
    return {path};
}

bool executable_sha256_matches(const std::filesystem::path& file) {
    HANDLE input = CreateFileW(file.c_str(), GENERIC_READ,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        nullptr, OPEN_EXISTING, FILE_FLAG_SEQUENTIAL_SCAN, nullptr);
    if (input == INVALID_HANDLE_VALUE) return false;

    HCRYPTPROV provider{};
    HCRYPTHASH hash{};
    std::array<BYTE, 32> digest{};
    bool ok = CryptAcquireContextW(&provider, nullptr, nullptr, PROV_RSA_AES, CRYPT_VERIFYCONTEXT);
    if (ok) ok = CryptCreateHash(provider, CALG_SHA_256, 0, 0, &hash);

    if (ok) {
        std::vector<BYTE> buffer(1024 * 1024);
        while (true) {
            DWORD count{};
            if (!ReadFile(input, buffer.data(), static_cast<DWORD>(buffer.size()), &count, nullptr)) {
                ok = false;
                break;
            }
            if (count == 0) break;
            if (!CryptHashData(hash, buffer.data(), count, 0)) {
                ok = false;
                break;
            }
        }
    }

    if (ok) {
        DWORD count = static_cast<DWORD>(digest.size());
        ok = CryptGetHashParam(hash, HP_HASHVAL, digest.data(), &count, 0) &&
            count == digest.size();
    }

    if (hash) CryptDestroyHash(hash);
    if (provider) CryptReleaseContext(provider, 0);
    CloseHandle(input);

    if (!ok) return false;
    std::ostringstream hex;
    hex << std::hex << std::setfill('0');
    for (auto octet : digest) hex << std::setw(2) << static_cast<unsigned>(octet);
    return hex.str() == layout::expected_executable_sha256;
}

bool verify_game_binary() {
    auto* image = reinterpret_cast<const unsigned char*>(GetModuleHandleW(nullptr));
    if (!image) return false;
    const auto* dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(image);
    if (dos->e_magic != IMAGE_DOS_SIGNATURE || dos->e_lfanew <= 0) return false;
    const auto* nt = reinterpret_cast<const IMAGE_NT_HEADERS64*>(image + dos->e_lfanew);
    if (nt->Signature != IMAGE_NT_SIGNATURE) return false;
    if (nt->FileHeader.TimeDateStamp != layout::expected_coff_timestamp) return false;
    if (nt->OptionalHeader.Magic != IMAGE_NT_OPTIONAL_HDR64_MAGIC) return false;

    const auto file = executable_path();
    if (file.empty()) return false;
    LARGE_INTEGER bytes{};
    HANDLE input = CreateFileW(file.c_str(), FILE_READ_ATTRIBUTES,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        nullptr, OPEN_EXISTING, 0, nullptr);
    if (input == INVALID_HANDLE_VALUE) return false;
    const bool size_ok = GetFileSizeEx(input, &bytes) &&
        static_cast<std::uint64_t>(bytes.QuadPart) == layout::expected_file_size;
    CloseHandle(input);
    return size_ok && executable_sha256_matches(file);
}

void ensure_mod_root() {
    if (!g_mod_root.empty() || !g_library) return;
    std::wstring path(32768, L'\0');
    const DWORD n = GetModuleFileNameW(g_library, path.data(), static_cast<DWORD>(path.size()));
    if (!n || n >= path.size()) return;
    path.resize(n);
    // <mod_root>/dlls/main.dll
    g_mod_root = std::filesystem::path(path).parent_path().parent_path();
}

bool read_bindings(void*& movement_class, void*& player_class, void*& movement_cdo) {
    std::ifstream input(g_mod_root / "runtime-bindings.ini");
    if (!input) return false;
    std::string line;
    bool schema = false;
    std::uintptr_t m{}, p{}, c{};
    while (std::getline(input, line)) {
        line = trim(line);
        if (line.empty() || line.front() == '#') continue;
        const auto equals = line.find('=');
        if (equals == std::string::npos) continue;
        const auto key = trim(line.substr(0, equals));
        const auto value = trim(line.substr(equals + 1));
        try {
            if (key == "schema" && value == "1") schema = true;
            else if (key == "movement_class") m = std::stoull(value, nullptr, 0);
            else if (key == "player_class") p = std::stoull(value, nullptr, 0);
            else if (key == "movement_cdo") c = std::stoull(value, nullptr, 0);
        } catch (...) {
            return false;
        }
    }
    movement_class = reinterpret_cast<void*>(m);
    player_class = reinterpret_cast<void*>(p);
    movement_cdo = reinterpret_cast<void*>(c);
    return schema && m && p && c &&
        valid_readable_address(movement_class) &&
        valid_readable_address(player_class) &&
        valid_readable_address(movement_cdo);
}

void read_settings() {
    const auto settings = g_mod_root / "config" / "momentum.ini";
    std::ifstream input(settings);
    if (!input) {
        log("momentum.ini missing; defaulting to observe-only.");
        return;
    }
    std::string line;
    while (std::getline(input, line)) {
        line = trim(line);
        const auto equals = line.find('=');
        if (equals == std::string::npos) continue;
        const auto key = trim(line.substr(0, equals));
        const auto val = trim(line.substr(equals + 1));
        if (key == "active") {
            g_config.active = (val == "1" || val == "true");
        }
    }
}

momentum::Vec3 convert(const FVector3f& src) {
    return {static_cast<double>(src.x), static_cast<double>(src.y),
            static_cast<double>(src.z)};
}

FVector3f convert(const momentum::Vec3& src) {
    return {static_cast<float>(src.x), static_cast<float>(src.y),
            static_cast<float>(src.z)};
}

void calc_velocity_hook(void* self, float dt, float friction, bool fluid, float deceleration) {
    const auto original = g_original;
    if (!original) return;

    // Global base vtable slot: every non-target component must pass through untouched.
    if (!is_instance_of(self, g_movement_class)) {
        original(self, dt, friction, fluid, deceleration);
        return;
    }

    auto* owner = at<void*>(self, layout::character_owner);
    if (!is_instance_of(owner, g_player_class) ||
        !std::isfinite(dt) || dt <= 0.0f || dt > 0.25f) {
        original(self, dt, friction, fluid, deceleration);
        return;
    }

    const std::uint8_t movement_mode = at<std::uint8_t>(self, layout::movement_mode);
    const bool dashing = (at<std::uint8_t>(owner, layout::b_is_dashing) & 1u) != 0;
    const bool bypass = dashing || (movement_mode != 1 && movement_mode != 2 && movement_mode != 3);
    const auto before = at<FVector3f>(self, layout::velocity);
    const auto wish = at<FVector3f>(self, layout::acceleration);
    const float max_walk = at<float>(self, layout::max_walk_speed);
    const float max_accel = at<float>(self, layout::max_acceleration);
    const float slide_rate = at<float>(owner, layout::power_slide_rate);
    const bool slide_active = g_slide_active.load(std::memory_order_acquire);

    const int previous_mode = g_last_movement_mode.exchange(
        static_cast<int>(movement_mode), std::memory_order_relaxed);
    if (previous_mode != static_cast<int>(movement_mode)) {
        std::ostringstream state;
        state << "movement_mode=" << static_cast<unsigned>(movement_mode);
        log(state.str());
    }

    const int dash_state = dashing ? 1 : 0;
    const int previous_dash = g_last_dash.exchange(dash_state, std::memory_order_relaxed);
    if (previous_dash != dash_state) {
        log(dashing ? "dash_event=start" : "dash_event=end");
    }

    original(self, dt, friction, fluid, deceleration);
    const auto vanilla = at<FVector3f>(self, layout::velocity);

    momentum::Vec3 result = convert(vanilla);
    if (!bypass) {
        result = convert(before);
        const momentum::Vec3 input = convert(wish);
        const double analog = input.horizontal_speed() <= 1.0e-6 ? 0.0 :
            (max_accel > 1.0f && std::isfinite(max_accel)
              ? std::clamp(input.horizontal_speed() / static_cast<double>(max_accel), 0.0, 1.0)
              : 1.0);
        const double speed = (std::isfinite(max_walk) && max_walk > 1.0f)
            ? static_cast<double>(max_walk) : g_config.ground_speed;

        if (movement_mode == 1 || movement_mode == 2) {
            if (slide_active) {
                result = momentum::apply_slide_friction(result, g_config.slide_friction, dt);
                result = momentum::accelerate_horizontal(
                    result, input, speed * analog, g_config.slide_acceleration, dt);
            } else {
                result = momentum::apply_ground_friction(
                    result, g_config.ground_friction, g_config.stop_speed, dt);
                result = momentum::accelerate_horizontal(
                    result, input, speed * analog, g_config.ground_acceleration, dt);
            }
        } else { // MOVE_Falling
            result = momentum::accelerate_horizontal(
                result, input, g_config.air_wish_cap * analog, g_config.air_acceleration, dt);
            result = momentum::soft_high_speed_damping(
                result, g_config.air_soft_threshold, g_config.air_soft_damping, dt);
        }

        // Let vanilla own gravity, jump, jetpack, and every vertical impulse.
        result.z = vanilla.z;
        result = momentum::safety_clamp(result, g_config.absolute_cap);
        if (!std::isfinite(result.x) || !std::isfinite(result.y) || !std::isfinite(result.z)) {
            result = convert(vanilla);
        }
    }

    const auto call_number = g_target_calls.fetch_add(1, std::memory_order_relaxed);
    if (call_number < 80 || call_number % 300 == 0) {
        std::ostringstream msg;
        msg << std::fixed << std::setprecision(3)
            << "sample=" << call_number << " active=" << g_config.active
            << " mode=" << static_cast<unsigned>(movement_mode)
            << " dash=" << dashing
            << " slide_active=" << slide_active
            << " slide_rate=" << slide_rate
            << " dt=" << dt << " max_walk=" << max_walk
            << " max_accel=" << max_accel
            << " pre=(" << before.x << "," << before.y << "," << before.z << ")"
            << " wish=(" << wish.x << "," << wish.y << "," << wish.z << ")"
            << " vanilla=(" << vanilla.x << "," << vanilla.y << "," << vanilla.z << ")"
            << " predicted=(" << result.x << "," << result.y << "," << result.z << ")";
        log(msg.str());
    }

    if (g_config.active && !bypass) {
        at<FVector3f>(self, layout::velocity) = convert(result);
    }
}

bool patch_slot(void** table, void* replacement, void* expected) {
    auto* slot = &table[layout::calc_velocity_slot];
    DWORD old{};
    if (!VirtualProtect(slot, sizeof(void*), PAGE_READWRITE, &old)) return false;
    const auto before = InterlockedCompareExchangePointer(
        reinterpret_cast<PVOID volatile*>(slot), replacement, expected);
    DWORD ignored{};
    VirtualProtect(slot, sizeof(void*), old, &ignored);
    return before == expected;
}

void set_slide_active(bool active) {
    const bool previous = g_slide_active.exchange(active, std::memory_order_acq_rel);
    if (previous != active) {
        log(active ? "slide_event=start" : "slide_event=end");
    }
}

void uninstall() {
    g_slide_active.store(false, std::memory_order_release);
    g_last_movement_mode.store(-1, std::memory_order_relaxed);
    g_last_dash.store(-1, std::memory_order_relaxed);
    if (!g_installed.exchange(false)) return;
    if (g_vtable && g_original) {
        if (patch_slot(g_vtable, reinterpret_cast<void*>(g_original),
                       reinterpret_cast<void*>(&calc_velocity_hook))) {
            log("CalcVelocity slot 215 restored.");
        } else {
            log("WARNING: slot changed by another mod; leaving its pointer untouched.");
        }
    }
}

bool install() {
    ensure_mod_root();
    if (g_mod_root.empty()) return false;
    if (g_installed.load()) return true;

    read_settings();
    if (!verify_game_binary()) {
        write_status("ERROR: game executable does not match pinned SHA256/size/timestamp.");
        return false;
    }

    void* movement_class{};
    void* player_class{};
    void* movement_cdo{};
    if (!read_bindings(movement_class, player_class, movement_cdo)) {
        write_status("ERROR: invalid Lua reflection bindings.");
        return false;
    }
    if (!is_instance_of(movement_cdo, movement_class)) {
        write_status("ERROR: movement CDO does not belong to the expected movement class.");
        return false;
    }

    void** vtable = *reinterpret_cast<void***>(movement_cdo);
    const auto image_base = reinterpret_cast<std::uintptr_t>(GetModuleHandleW(nullptr));
    if (!valid_readable_address(vtable) ||
        reinterpret_cast<std::uintptr_t>(vtable) != image_base + layout::expected_vtable_rva) {
        write_status("ERROR: movement component vtable RVA mismatch.");
        return false;
    }

    void* expected = reinterpret_cast<void*>(image_base + layout::calc_velocity_function_rva);
    if (vtable[layout::calc_velocity_slot] != expected) {
        write_status("ERROR: CalcVelocity slot 215 target RVA mismatch; hook disabled.");
        return false;
    }

    g_slide_active.store(false, std::memory_order_release);
    g_last_movement_mode.store(-1, std::memory_order_relaxed);
    g_last_dash.store(-1, std::memory_order_relaxed);
    g_movement_class = movement_class;
    g_player_class = player_class;
    g_original = reinterpret_cast<CalcVelocity>(expected);
    g_vtable = vtable;

    if (!patch_slot(vtable, reinterpret_cast<void*>(&calc_velocity_hook), expected)) {
        write_status("ERROR: atomic vtable patch failed.");
        g_original = nullptr;
        g_vtable = nullptr;
        return false;
    }

    g_installed.store(true, std::memory_order_release);
    write_status(g_config.active
        ? "ACTIVE: Momentum CalcVelocity hook installed at slot 215."
        : "OBSERVE: CalcVelocity hook installed at slot 215; vanilla movement unchanged.");
    return true;
}
} // namespace momentum_native

// No Lua headers/libs are necessary: the Lua loader calls this exact C entrypoint
// and expects the number of values returned on the Lua stack. We return zero.
extern "C" __declspec(dllexport) int luaopen_momentum_native(void*) {
    momentum_native::install();
    return 0;
}

extern "C" __declspec(dllexport) int luaopen_momentum_native_uninstall(void*) {
    momentum_native::uninstall();
    return 0;
}

extern "C" __declspec(dllexport) int luaopen_momentum_slide_start(void*) {
    momentum_native::set_slide_active(true);
    return 0;
}

extern "C" __declspec(dllexport) int luaopen_momentum_slide_end(void*) {
    momentum_native::set_slide_active(false);
    return 0;
}

BOOL WINAPI DllMain(HMODULE handle, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        momentum_native::g_library = handle;
        DisableThreadLibraryCalls(handle);
    } else if (reason == DLL_PROCESS_DETACH) {
        // On normal process exit the OS unmaps code together. The Lua OnUnload
        // callback handles hot-removal; never block or allocate under loader lock.
    }
    return TRUE;
}
