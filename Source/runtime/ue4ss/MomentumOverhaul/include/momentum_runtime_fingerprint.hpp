#pragma once
#include <cstddef>
#include <cstdint>

namespace MomentumOverhaul::runtime_fingerprint
{
// RoboQuest-Win64-Shipping.exe
// SHA-256: 158487e80be71d5570ca0a1e1a1208ab1c0842daf181f4cb6c98920bc4b4dc1f
// JMAP SHA-256: dcf85f680996aedb1ac0c98d5d48b357e8a55d68dcb5d52ed577f84ea08ea8cc
inline constexpr std::uint64_t expected_executable_file_size = 93293056ULL;
inline constexpr std::uint32_t expected_coff_timestamp = 0x699F0130U;
inline constexpr std::size_t calc_velocity_vtable_slot = 215;
inline constexpr std::uintptr_t calc_velocity_vtable_displacement = 0x6B8;
inline constexpr std::uintptr_t calc_velocity_function_rva = 0x02EB5440;
inline constexpr std::uintptr_t calc_velocity_exec_thunk_rva = 0x03494760;
}
