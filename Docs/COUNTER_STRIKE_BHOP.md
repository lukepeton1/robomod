# Counter-Strike-style bunny hopping — Momentum native alpha

**Status: C++ core and UE4.26 native adapter implemented. CI builds and physics tests pass. Real Roboquest gameplay behavior still requires active-mode testing.**

## What changed

This is an actual horizontal-velocity integration change, not a cosmetic effect or a simple running-speed multiplier.

### Source/Quake air acceleration

For airborne velocity `v`, normalized player wish direction `d`, full input wish speed `s`, projection cap `c`, acceleration coefficient `a` and timestep `dt`:

```text
allowed_projection = min(s, c)
remaining = allowed_projection - dot(v, d)
if remaining > 0:
    impulse = min(remaining, a * s * dt)
    v.xy += d.xy * impulse
```

Unlike the previous prototype, acceleration uses the **uncapped wish speed** `s`, not the much smaller directional cap `c`. The cap applies only to the velocity **projection into the requested strafe direction**, not total horizontal speed. A skilled player can continue accumulating speed while turning and alternating A/D, as in Source movement. Holding W without a lateral component does **not** grant free acceleration once its directional projection is saturated.

Native defaults:

| Tuning | Value | Function |
| --- | ---: | --- |
| `air_acceleration` | 9.0 | Source-style acceleration coefficient |
| `air_wish_cap` | 320 cm/s | Directional projection limit |
| `landing_grace_ms` | 90 ms | Ground-contact window without normal friction |
| `ground_friction` | 7.0 | Missed hops slow the player normally |
| `air_soft_damping` | 0.0 | No artificial high-speed aerial drag |
| `absolute_speed_cap` | 30,000 cm/s | Emergency physics safeguard, **not** run-speed ceiling |

The ordinary `MaxWalkSpeed` still determines requested movement speed, but does not cap existing horizontal momentum.

### Landing chain and speed conservation

- A dedicated `BunnyhopChainState` is tracked per movement-component pointer in the native hook, not one shared velocity or a screen-space trick.
- During `MOVE_Falling`, it records the actual applied horizontal velocity.
- On the first grounded update, if Unreal/Roboquest has reduced the speed while preserving almost exactly the same horizontal direction, it restores the last genuine airborne speed. It **never increases speed beyond the previously earned airborne value**.
- The first 90 ms of walking movement following an airborne state skip ordinary ground friction. Ground friction for any remaining time in a crossing frame is correctly applied.
- A delayed landing/hop beyond the grace window incurs the normal friction penalty.
- Dash, custom movement and slides bypass/clear the special bhop state so their separate gameplay systems are not overwritten.
- Vanilla Unreal physics owns collisions, floor detection, vertical velocity and jump impulses; Momentum only replaces valid horizontal velocity integration.

No automatic repeated jump key input, wallrunning or grappling changes are claimed in this patch. The player must still use Roboquest's existing jump input each hop. Add optional held-jump auto-hop **only after** the actual jump-call path has been validated. Do not implement jump by teleporting.

## Reproducible physics tests

`tests/cpp/test_momentum_core.cpp` now exercises:

- straight forward air movement does not magically increase speed;
- dynamically coordinated strafe inputs add velocity over **eight consecutive hops**;
- each quick hop preserves the prior airborne speed through the landing grace;
- missing the landing window incurs actual ground friction;
- a sudden aligned speed drop at touchdown can be safely restored;
- a direction-changing wall impact is not restored;
- existing ground acceleration, slide, impulses and emergency safety logic.

The test constructs steering vectors from the current horizontal velocity; the player must achieve a similar changing wish direction with A/D and mouse steering in-game. The test's speed numbers are **simulated**, not a measured Roboquest gameplay result.

## How to actually feel the changed physics

From the repository root (Windows):

```powershell
git switch feature/movement-overhaul
git pull --ff-only
.\tools\windows\run-momentum-runtime-test.cmd -Bhop
```

The command requires the compiled `MomentumOverhaul-runtime.zip` from the latest successful [Build Momentum Runtime](https://github.com/lukepeton1/robomod/actions/workflows/build-momentum-runtime.yml), placed in `handoff\`, the repo root or Downloads. The runner stages the mod temporarily, sets `active=1` while preserving physics tuning, launches Roboquest, gathers logs, and restores game files upon exit.

**Before testing active mode**, verify that the [startup-crash isolation run](MOMENTUM_STARTUP_DIAGNOSIS.md) has ruled out the prior `BP_APlayer_C` constructor failure. Only play single-player; co-op prediction is not validated.

To test the mechanic: gain ordinary run speed, jump, strafe sideways with A or D while rotating view into the strafe; jump again within ~90 ms of touching down, then reverse strafes on subsequent hops. Sustained A/D + mouse coordination should increase speed from hop to hop. Simply holding forward and tapping jump does not demonstrate this mechanic.

Verify the generated `handoff\momentum-runtime-test.zip` reports:

```text
runtime-status.txt: ACTIVE: Source bhop air acceleration, landing speed preservation and grace enabled.
momentum-runtime.log: bhop_event=landing ... active=1 ... result_speed=...
momentum-runtime.log: sample=... active=1 ... horizontal_speed=... predicted=...
```

If status says `OBSERVE` or telemetry says `active=0`, then the game ran with vanilla movement; it is not an evaluation of bunny hopping.

If the game crashes, the test runner preserves diagnostic files. Do not remove the backup by hand; follow the recovery guide. Avoid co-op.

## Further development after active verification

1. Instrument speed-over-time on a visible HUD (no logging overhead each tick), after validating correct high-speed momentum in telemetry.
2. Validate near-landing jump buffering and determine whether optional hold-to-autohop is supported by the native/Blueprint jump event.
3. Check unintended speed cuts from collision / slope transitions and implement specific fixes rather than bypassing Unreal movement.
4. Tune strafe acceleration and grace from gameplay traces, and add frame-rate comparison in the actual runtime.
5. Later integrate Dash, Grapple, wallrunning, slides, Jetpack and rocket jumps with the same momentum model.
