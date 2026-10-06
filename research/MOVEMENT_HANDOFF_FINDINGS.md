# Roboquest Momentum — decoded movement architecture

Date: 2026-10-06

This document records the first raw-cooked movement handoff results for `feature/movement-overhaul`.

## Handoff integrity

The supplied movement handoff contained every requested package:

- 35 / 35 target packages collected;
- zero missing packages;
- all requested UAssetAPI JSON exports present;
- `BP_APlayer`: 349 / 349 FunctionExports decoded;
- `BP_APlayerController`: 126 / 126 decoded;
- `BP_IngamePlayerController`: 77 / 77 decoded;
- `BP_Grapple`: 31 / 31 decoded;
- `BP_PS_Dash`: 8 / 8 decoded;
- `BP_PowerSlideSkill`: 8 / 8 decoded;
- `BP_Jetpack`: 3 / 3 decoded;
- `BP_WS_RocketJump`: 2 / 2 decoded;
- `BP_PS_RocketJump`: 2 / 2 decoded;
- `BP_Jumpad`: 6 / 6 decoded;
- zero raw-bytecode fallback functions in the movement handoff.

The handoff ZIP used for this pass had SHA-256:

`91f90ba53c3f4b2e2127e31d5682be6320ab30f44b42388bdeb61ac1348399bf`

Raw game packages are not committed to this repository.

## Core result

The first architecture decision is now evidence-based:

> The full Source-style ground/air momentum integrator cannot be implemented correctly using only the currently exposed cooked Blueprint seams.

This does **not** mean Momentum must become a giant runtime framework. It means the correct layer for the core locomotion model is native `Character_Player` / `RoboquestMovementComponent`, and the next phase must identify the smallest safe way to extend or hook that layer.

The project will still prefer cooked Blueprint patches for movement verbs that are genuinely Blueprint-authored.

## Why the core is native

`BP_APlayer` owns `CharMoveComp`, a native `RoboquestMovementComponent`, but the cooked component CDO has stock Unreal movement inputs largely disabled:

- `GravityScale = 0`
- `JumpZVelocity = 0`
- `MaxWalkSpeed = 0`
- `MaxAcceleration = 0`
- `AirControl = 0`
- `MaxCustomMovementSpeed = 5000`
- `BrakingDecelerationFalling = 200`
- `bMaintainHorizontalGroundVelocity = false`

The player also has:

- `bMovementPredict = true`
- `bReplicateMovement = false`

Across the decoded movement handoff there is no direct reflected Kismet call target of the form `RoboquestMovementComponent.<movement function>`.

That combination is strong evidence that the actual walking/falling/jump integration and prediction path is implemented in native code rather than ordinary Blueprint manipulation of `CharacterMovementComponent` settings.

## Decoded control flow by movement verb

### Normal jump / input

`BP_IngamePlayerController` receives the Jump input and dispatches to inherited/native `OnPressedJump`.

`BP_APlayer` exposes semantic hooks such as `OnJumped`, native `Character_Player.OnJump`, `OnBlueprintLanded`, and `ResetJump`, but the cooked call graph does not expose a per-step Blueprint walking/falling integrator.

### Dash

`BP_PS_Dash.ExecuteUbergraph_BP_PS_Dash` resolves directly into:

`/Script/RoboQuest.Character_Player.OnStartDash`

The Blueprint handles skill/event behavior around the Dash, while the physical Dash entry point is native.

Therefore Momentum must preserve the native Dash semantic event even if the physical effect becomes momentum-compositional.

### Power Slide

`BP_PowerSlideSkill` is a listener/item behavior surface. It binds `DelegatePowerSlide_Event_0`; it is not the physical slide integrator.

Vanilla slide curves are:

`CU_PowerSlide`
- `t=0.10 -> 2020`
- `t=0.55 -> 1050`

`CU_PowerSlide_Superbot`
- `t=0.10 -> 1680`
- `t=0.60 -> 925`

This confirms that vanilla already treats Power Slide as a decaying high-speed movement state, but the physical state transition itself is native/core-player behavior.

### Grapple

Grapple is the major exception.

`BP_Grapple.ExecuteUbergraph_BP_Grapple` is a large decoded Blueprint graph and directly uses:

- `GetWorldDeltaSeconds`
- `VInterpTo_Constant`
- `K2_SetActorLocation`
- `SetMovementMode`
- `ResetJump`
- `LaunchCharacter`
- native `Character_Player.OnStartGrapple`
- native `Character_Player.OnStopGrapple`
- native `Character_Player.GetGrappleHitResult`

The current Grapple disables normal movement verbs while active. Its `ForbiddenActions` include Move, Crouch, Jump and PowerSlide.

The Blueprint switches the player to movement mode `6` (`MOVE_Custom`) on pull start and returns to mode `1` (`MOVE_Walking`) on stop.

The current attract path is therefore effectively a controlled positional pull rather than a true tangential-momentum swing.

On detach, `LaunchCharacter` is called with horizontal override disabled and vertical override enabled. That means vanilla already preserves incoming horizontal velocity at one important release seam.

**Conclusion:** Grapple can likely receive substantial Momentum behavior through cooked Blueprint patching, but it should be rewritten only after the shared core velocity model exists.

### Jetpack

`BP_Jetpack` is thin. Its movement-relevant call is:

`/Script/RoboQuest.Character_Player.SetJetpackActivate`

The actual thrust/gravity behavior is native.

Vanilla curves:

`CU_Jetpack`
- `(0.00, -2.0)`
- `(0.05, -6.0)`
- `(0.12, -2.0)`
- `(0.30, 0.5)`
- `(1.00, 0.0)`
- `(3.50, 0.25)`

`CU_Jetpack_Gravity`
- `(0.00, -0.9)`
- `(1.00, -0.3)`

Horizontal-momentum preservation must therefore be handled in the native/core movement layer, not by merely editing `BP_Jetpack`.

### Rocket Jump

Both Rocket Jump Blueprints invoke inherited/native `OnTriggerRocketJump` with launch vector/location/radius data.

Vanilla curves:

`CU_RocketJump`
- `(200, 2000)`
- `(400, 2600)`
- `(600, 2800)`

`CU_RocketJump_DistanceRatio`
- `(0.00, 1.0)`
- `(0.66, 1.0)`
- `(1.00, 0.5)`

The final Momentum policy should make this an additive external impulse, but the physical application point is native.

### Jump pads

`BP_Jumpad` derives from native `AJumpad` and exposes `GetImpulse`, `IsTubeEffect`, and `IsSpecialExitingJumpad`.

Its cooked CDO has `Impulse = 2750`.

The player has a `DelegateOnTakeJumpad` semantic hook, but application of the launch is native-facing. Normal and special/tube pads must be tested separately.

## Network implications

The most important network facts from the cooked player remain:

- `bMovementPredict = true`
- `bReplicateMovement = false`

Momentum must not use per-frame position RPCs and must not implement the core as `ReceiveTick -> SetActorLocation`.

The runtime/core layer needs to participate in the existing movement ownership/prediction path. A solution that merely overrides rendered transforms would fight collision, saved moves, corrections, floor state and co-op authority.

## PAK-only decision

Current decision:

### PAK-only remains appropriate for

- data/curve tuning;
- semantic event preservation;
- selected Grapple behavior;
- camera/audio/VFX;
- some item/perk integration;
- UI/debug surfaces;
- package-level compatibility patches.

### PAK-only is not sufficient, with currently proven seams, for

- replacing ground acceleration;
- true Source-style air acceleration;
- bhop momentum preservation at the authoritative movement step;
- friction policy;
- shared velocity semantics across jump/landing;
- wallrun physics integrated with native collision;
- prediction-safe high-speed movement.

A minimal runtime/native extension is therefore the leading production architecture unless the native binary probe reveals a previously hidden reflected hook that changes this conclusion.

## Next native research gate

The next handoff intentionally does **not** request the game executable.

`tools/windows/collect-movement-native-handoff.cmd` locally scans `RoboQuest-Win64-Shipping.exe` and emits only:

- executable SHA-256;
- basic PE metadata;
- movement-related ASCII/UTF-16 strings;
- bounded scored string neighborhoods around movement anchors.

No executable bytes are included in the ZIP.

This will help identify whether `RoboquestMovementComponent` native method names survive in the shipping binary, whether Unreal CharacterMovement prediction names are present near Roboquest movement symbols, candidate native hook/reflection seams, and whether a current UE4SS/native-hook probe is justified.

## Architectural rule going forward

Momentum will use one shared velocity model.

The project will not be implemented as independent hacks for bhop, slide, wallrun, Dash and Grapple. Each movement verb must compose with the same velocity state and explicitly define whether it adds velocity, preserves velocity, replaces one component, redirects a component, or clamps only for safety.

That model will be built at the native movement layer first, then cooked Blueprint verbs such as Grapple will be adapted around it.
