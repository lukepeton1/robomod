# Roboquest Momentum — first successful UE4SS runtime probe

Date: 2026-10-06

Source handoff ZIP SHA-256:

`7e46357b984202b950852afd23adbc36e1c9853e6bff6d734cf9eecdbe948c82`

## Probe result

The runtime probe reached the real shipping executable and UE4SS initialized successfully on:

- `RoboQuest-Win64-Shipping.exe`
- 93,293,056 bytes
- SHA-256 `158487e80be71d5570ca0a1e1a1208ab1c0842daf181f4cb6c98920bc4b4dc1f`
- forced Unreal Engine version 4.26
- shipping configuration
- STATS off

The runtime manifest reported:

- `probe_status = game_exited`
- `probe_error_present = false`
- UE4SS `experimental-latest`
- asset `zDEV-UE4SS_v3.0.1-1161-g6eb3d9bc.zip`
- `jmap_count = 0`

The zero JMAP count was **not** a UE4SS compatibility failure.

## UE4SS runtime compatibility confirmed

The log shows successful discovery and initialization of the critical Unreal runtime surfaces:

- `GUObjectArray`
- `GMalloc`
- `FName::ToString`
- `FName::FName(wchar_t*)`
- `StaticConstructObject_Internal`
- `FUObjectHashTables::Get()`
- `GNatives`
- `GameEngine::Tick`
- `ProcessEvent`
- `ProcessConsoleExec`
- `UStruct::Link`
- `ProcessInternal`
- `ProcessLocalScriptFunction`

UE4SS also successfully initialized its reflected type system and resolved core UObject/UClass/UFunction/FProperty layouts for this build.

This establishes that a narrow UE4SS/C++ runtime extension is viable for Momentum on the current Roboquest shipping build.

## Why the JMAP did not appear

The Momentum Lua mod was discovered and started:

`Starting Lua mod 'MomentumProbe'`

but failed on the first byte of `main.lua`:

`unexpected symbol near '<\239>'`

Byte 239 (`0xEF`) is the first byte of a UTF-8 BOM (`EF BB BF`).

Windows PowerShell 5's `Set-Content -Encoding UTF8` writes a BOM, while this UE4SS Lua loader rejected the BOM before parsing the script.

No `DumpJMAP` call was therefore executed.

## Fix

The runtime probe now writes `MomentumProbe/Scripts/main.lua` with `System.Text.UTF8Encoding(false)`, i.e. UTF-8 without BOM.

The JMAP call is also run immediately when the Lua mod starts instead of waiting on a fixed delay:

`DumpJMAP(false, false)`

This requests native types only while preserving property/CDO values and approximate vtable information needed for the movement-hook decision.

## Architecture impact

This result removes the loader-compatibility uncertainty.

The remaining runtime gate is now strictly:

1. produce the native JMAP;
2. inspect `/Script/RoboQuest.RoboquestMovementComponent`;
3. compare its approximate vtable/function surface to `UCharacterMovementComponent`;
4. determine whether Roboquest overrides the relevant velocity integration virtual;
5. bind the checked-in `Source/runtime/momentum_core.*` equations to that exact seam.

No actor-transform replacement architecture is needed or justified.
