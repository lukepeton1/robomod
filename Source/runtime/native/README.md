# Roboquest Momentum — standalone runtime alpha

Native x64 Win32 DLL loaded by the confirmed-working UE4SS Lua runtime.
It does not link against UE4SS or restricted UEPseudo headers/libraries.

## Exact build gate

- Shipping executable SHA-256: 158487e80be71d5570ca0a1e1a1208ab1c0842daf181f4cb6c98920bc4b4dc1f
- File size: 93,293,056 bytes; COFF: 0x699F0130
- CalcVelocity slot: 215, displacement 0x6B8, function RVA 0x02EB5440
- Shared CharacterMovementComponent vtable RVA: 0x0411D150
- UObject and movement raw offsets: see include/momentum_native_layout.hpp

An executable update must fail closed. Never remove the fingerprint check to make an unknown version run.

## Runtime layout (UE4SS experimental new directory layout)

Copy under game Win64 directory:

    ue4ss/Mods/MomentumOverhaul/Scripts/main.lua
    ue4ss/Mods/MomentumOverhaul/native/main.dll
    ue4ss/Mods/MomentumOverhaul/config/momentum.ini

Lua obtains UClass and CDO addresses by reflection, writes runtime-bindings.ini,
then uses package.loadlib to load the standalone native DLL.
The DLL SHA-verifies the shipping EXE and atomically swaps the guarded CalcVelocity
vtable slot. It restores the original pointer through an uninstall export.

The hook accepts only subclasses of RoboquestMovementComponent owned by a
Character_Player. All other components pass through to vanilla CalcVelocity.
Dash, Grapple/MOVE_Custom, other non-walking modes remain vanilla.
Vertical velocity is kept from the vanilla solver. No actor position manipulation
or per-frame RPC is used.

## Startup crash status and isolation

The `BP_APlayer_C` ClassConstructor crash remains unproven as fixed. A successful early observe test was followed by startup crashes before any target movement frame. The bootstrap now waits for a non-default `Character_Player` with a usable world, and the native loader verifies its install status. GitHub Actions compilation is **not** proof of an in-game fix.

The runner supports `-Baseline`, `-LoaderOnly`, `-BootstrapOnly`, and default observe mode. Only observe mode needs the GitHub Actions runtime ZIP; loader-only stages a pinned UE4SS build with all shipped mods disabled. All tests back up and restore pre-existing game-directory modifications.

**Use `-LoaderOnly` for the next local diagnosis.** Full instructions and the result-interpretation matrix: [Momentum startup crash isolation](../../../Docs/MOMENTUM_STARTUP_DIAGNOSIS.md).

## Test mode

config/momentum.ini defaults to active=0: OBSERVE.
In this mode the guarded vtable hook logs input/velocity samples, but does not
modify movement. This is the safe first single-player smoke test.
Set active=1 only after observation is clean, then relaunch.
Do not test co-op until prediction validation is done.

Logs are written beside the mod:

    momentum-runtime.log
    runtime-status.txt
    runtime-bindings.ini

## Build

    cmake -S Source/runtime/native -B build/momentum-native -G "Visual Studio 17 2022" -A x64
    cmake --build build/momentum-native --config Release

Windows GitHub Actions builds and packages the DLL, Lua bootstrap and config.

## Scope

This is the initial guarded native bridge, not the full overhaul.
Wallrunning, lurch, buffered jumping, momentum Dash/Grapple/Jetpack/
Rocket Jump, surf/slope interaction, camera polish and co-op prediction
are remaining work.
