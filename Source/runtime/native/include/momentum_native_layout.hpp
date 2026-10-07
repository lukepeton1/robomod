#pragma once
// Exact-build JMAP layout. Fail closed if the executable fingerprint drifts.
#include <cstddef>
#include <cstdint>

namespace momentum_native_layout {
inline constexpr char expected_executable_sha256[] =
    "158487e80be71d5570ca0a1e1a1208ab1c0842daf181f4cb6c98920bc4b4dc1f";
inline constexpr std::uint64_t expected_file_size = 93293056ULL;
inline constexpr std::uint32_t expected_coff_timestamp = 0x699F0130U;
inline constexpr std::uintptr_t expected_vtable_rva = 0x0411D150ULL;
inline constexpr std::size_t calc_velocity_slot = 215;
inline constexpr std::uintptr_t calc_velocity_displacement = 0x6B8;
inline constexpr std::uintptr_t calc_velocity_function_rva = 0x02EB5440ULL;

inline constexpr std::size_t uobject_class_private = 0x10;
inline constexpr std::size_t ustruct_super = 0x40;

inline constexpr std::size_t velocity = 0xC4;
inline constexpr std::size_t character_owner = 0x148;
inline constexpr std::size_t movement_mode = 0x168;
inline constexpr std::size_t max_walk_speed = 0x18C;
inline constexpr std::size_t max_acceleration = 0x1A0;
inline constexpr std::size_t acceleration = 0x22C;

inline constexpr std::size_t b_is_dashing = 0x4D30;
inline constexpr std::size_t power_slide_rate = 0x4E84;
}
