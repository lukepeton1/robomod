# Momentum runtime observe run — findings

Date: 2026-10-07

Source handoff: `momentum-runtime-test.zip`

## Run status

The first observe-only native runtime test completed cleanly.

Manifest:

- `status = game_exited`
- `mode = observe`
- `error_present = false`
- runtime artifact SHA-256:
  `431ad191ba5ec8ea48b8dba5d339cfa3b8ac646dda34ed5d5ca2b9a097f12c63`
- game executable SHA-256:
  `158487e80be71d5570ca0a1e1a1208ab1c0842daf181f4cb6c98920bc4b4dc1f`

Runtime status:

`OBSERVE: CalcVelocity hook installed at slot 215; vanilla movement unchanged.`

The hook remained installed through the movement session and the test runner restored the staged UE4SS/game-directory state on exit.

## ABI / layout validation

Observed values were coherent with the JMAP-derived offsets and the expected UE4.26 CharacterMovement ABI:

- movement modes observed: `1` (walking) and `3` (falling)
- `MaxAcceleration = 10000`
- nonzero `Acceleration` vectors had horizontal magnitude ~10000
- `MaxWalkSpeed` observed at:
  - 1050 — ordinary run
  - 1602 — boosted/sprint state
  - 2020 — Power Slide start sample
- all sampled pre/vanilla/predicted vectors remained finite
- no executable fingerprint, vtable or slot guard failed

This validates the CalcVelocity signature, the target-class guard, the velocity/acceleration offsets, and the core directional-acceleration adapter sufficiently for continued observe-mode testing.

## Power Slide finding

The initial bridge incorrectly treated any nonzero `PowerSlideRate` as active Power Slide.

Telemetry disproved that assumption.

A real Power Slide sample showed:

- `PowerSlideRate = 1.0`
- `MaxWalkSpeed = 2020`

but after the slide ended, `PowerSlideRate` remained around `0.258–0.259` during normal walking and falling.

Therefore `PowerSlideRate` is a timeline/animation value, **not an authoritative active-state flag**. Enabling the original heuristic would have caused ordinary ground movement after a slide to use slide friction.

The full JMAP exposes a better source:

`/Script/RoboQuest.APlayerAnimInstance:OnDelegatePowerSlide(bool bIsStart)`

The runtime bootstrap now hooks that native UFunction and forwards explicit start/end events to the standalone DLL. The DLL stores an atomic slide-state latch. `PowerSlideRate` remains telemetry-only.

## UE4SS native-DLL packaging finding

UE4SS logged a failed C++ mod auto-install attempt for `MomentumOverhaul` because the standalone bridge was packaged at:

`MomentumOverhaul/dlls/main.dll`

The Lua bootstrap subsequently loaded the DLL successfully via `package.loadlib`, so this did not break the run, but it is unnecessary and noisy.

The standalone bridge is now packaged at:

`MomentumOverhaul/native/main.dll`

and loaded only by the Lua bootstrap. This avoids UE4SS treating it as a normal C++ UE4SS lifecycle mod.

## Next validation

Before active movement:

1. run observe mode again;
2. perform at least one full Power Slide start/end;
3. perform one or more Dashes;
4. verify telemetry contains:
   - `slide_event=start`
   - `slide_event=end`
   - Dash transition events
   - sensible walking/falling movement-mode transitions;
5. only then run with `-Active`.

Co-op remains out of scope until prediction behavior is explicitly validated.
