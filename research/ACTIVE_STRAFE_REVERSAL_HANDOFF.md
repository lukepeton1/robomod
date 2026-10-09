# Momentum active air-strafe reversal investigation

Date: 2026-10-09.

## User report
Roboquest now feels non-vanilla and D/right air strafing partly works, but changing to A/left appears to destroy acquired momentum. Diagnostic attachment: `momentum-runtime-test.zip` (run starting 2026-10-09 20:58:10Z).

## Confirmed facts from attached runtime test

- Manifest: `status=game_exited`, `mode=active`, `native_dll_staged=true`, `game_files_restored=true`, and `error_present=false`.
- Game EXE fingerprint matches the supported shipping build.
- UE4SS asset was the pinned 1161 development build.
- **Stale native artifact:** the installed runtime's status is `ACTIVE: Momentum CalcVelocity hook installed at slot 215.`, which was removed from the source *before* the new Source-style bhop build. The log also lacks `bhop_event=landing`, `bhop_friction_dt`, and `horizontal_speed` telemetry added by the newer adapter. Its ZIP SHA-256 in the manifest was `7e3b6c83a37968441872ada281ffd1445ef0497cb762d56bc61270db07211704`. The run therefore does **not** test the new air-acceleration / landing-grace implementation.
- The hook was active, reaching `sample=7800`. Movement mode alternated between walking (1) and falling (3). PowerSlide start/end events were logged. Sampling was initially 80 consecutive frames, then every 300 frames: too sparse to isolate the exact D→A transition.
- A parsed subset of 106 frame samples has pre-speed up to approximately 1786 cm/s and 15 sampled airborne frames, so there is no basis for diagnosing the exact reversal from sparse logged frames.
- **False-positive fatal indicator:** the test manifest said `fatal_error_detected=true`, but the only matching diagnostic was an ordinary UE4SS layout line `UClass::ClassConstructor = 0xB0`. No actual `Can't find ClassConstructor`, `LowLevelFatalError`, or game fatal was present in the captured logs. The runner's broad `ClassConstructor` regex has been narrowed; a test now ensures a harmless field offset is not flagged.

## Corrections committed

1. The runner now reads `runtime-build.txt` from each candidate Momentum artifact ZIP, validates the embedded native DLL against the declared SHA-256, confirms the build commit belongs to local branch history and compares all `Source/runtime` files against the checked-out HEAD. It refuses any ZIP whose compiled inputs are stale.
2. The ZIP search examines the repository, `handoff` and Downloads, including Windows browser names like `MomentumOverhaul-runtime (1).zip`. A stale first candidate will be skipped in favor of a newer compatible download.
3. A C++ test explicitly alternates coordinated D→A→D→A wish-direction handedness and verifies speed does not decrease on these transitions. An existing eight-hop test separately verifies sustained speed growth and the 90 ms landing grace.
4. Active-mode native logging now emits `air_trace=sample` approximately every 12 movement calls while falling and immediately on significant within-hook or between-call speed loss. Logs include:
   - `alignment`: cosine of incoming horizontal velocity against input wish direction
   - `previous_applied_speed`: speed written by previous airborne hook update
   - `pre_speed`: speed at current hook entrance
   - `vanilla_speed`: vanilla `CalcVelocity` result
   - `result_speed`: Momentum prediction to be written
   - `outside_cut`: significant loss between previous applied and current pre-hook velocity
   - `in_hook_braking`: significant speed loss caused by current Momentum calculation
5. Native status now includes `AIR_TRACE_V2` to disambiguate old runtime binaries; ZIP source integrity check is a stronger guarantee than a log marker.

## Remaining question

The uploaded attachment is from the **old** runtime. It is not evidence that the latest air-strafe correction fails. In-game reversal behavior must be rechecked using the new artifact containing the high-resolution telemetry.

Source/Quake-style directional acceleration legitimately slows a player whose input wish vector points backward against current movement. Correct A/D plus mouse-turn strafing normally keeps the wish direction near perpendicular to actual velocity. A full speed reset when properly alternating strafe and turn, especially with `outside_cut=true`, would instead indicate a genuine integration/collision/landing bug. The high-resolution log now distinguishes these hypotheses.

The user's previous ZIP should not be sent back as a runtime artifact, and a successful game exit should not be misclassified as a crash due to UE4SS reflection output.

## Next action

Download the latest `MomentumOverhaul-runtime` artifact built from the most recent native source from the successful [Build Momentum Runtime workflow](https://github.com/lukepeton1/robomod/actions/workflows/build-momentum-runtime.yml). Place the ZIP in Downloads (no need to delete old `handoff` ZIP), pull `feature/movement-overhaul`, and run `tools\windows\run-momentum-runtime-test.cmd -Bhop`. The runner must print a compatible commit and native SHA-256 **before** modifying the game directory. The resulting diagnostic ZIP's native status must contain `AIR_TRACE_V2`. Keep tests to single-player until movement prediction is validated.
