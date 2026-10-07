# Roboquest Momentum — native binary findings

Date: 2026-10-06

Source handoff SHA-256:

`46db10761160b0334209a178179e95b5419905aff90bca13579f4bf096c4bb6b`

The handoff contains no game executable. It contains only the local scanner output and metadata.

## Shipping executable

The corrected native probe analyzed:

- file: `RoboQuest-Win64-Shipping.exe`
- size: `93,293,056` bytes
- SHA-256: `158487e80be71d5570ca0a1e1a1208ab1c0842daf181f4cb6c98920bc4b4dc1f`
- PE machine: x86-64
- PE section count: 9
- COFF timestamp: 2026-02-25T14:03:28Z

The scanner extracted 1,117,667 ASCII/UTF-16 strings, 814 movement-target hits and 172 movement-anchor neighborhoods.

## Native player movement methods visible in the shipping binary

The executable contains explicit native method names including:

- `ACharacter_Player::Tick`
- `ACharacter_Player::OnTickDash`
- `ACharacter_Player::OnStartDash`
- `ACharacter_Player::PressedJump`
- `ACharacter_Player::ReleasedJump`
- `ACharacter_Player::OnStartPowerSlide`
- `ACharacter_Player::OnTakeJumpad`
- `ACharacter_Player::SetJetpackActivate`
- `ACharacter_Player::OnStartJetpack`
- `ACharacter_Player::StopJetpack`
- `ACharacter_Player::OnStopJetpack`
- `ACharacter_Player::UpdateJetpackFuelDuration`

The reflected/native name table also exposes:

- `OnEndPowerSlide`
- `UpdatePowerSlideTimeline`
- `PowerSlideValue`
- `OnServerSetMaxAcceleration`
- `OnServerSetMaxAcceleration_Validate`
- `ResetJump`
- `OnStartGrapple`
- `OnStopGrapple`
- `OnTriggerRocketJump`
- `OnTakeJumpad`

This confirms that the cooked Blueprint event surfaces observed in the first handoff are backed by a substantial native movement state machine.

## Hidden native tuning vocabulary

The most useful discovery is the contiguous native property-name region around the player movement configuration.

It contains:

### Base locomotion

- `RunMoveSpeed`
- `CrouchMoveSpeed`
- `SprintMoveSpeed`
- `GroundAcceleration`
- `AerialAcceleration`
- `LandAcceleration`
- `BaseGravity`
- `GravityIncreasePerSecond`
- `AirControl`

### Jump

- `FirstJumpHoldTime`
- `SecondJumpVelocity`
- `SecondJumpHoldTime`
- `MinJumpDelayWithMouseWheel`
- `BunnyJumpSpeedPercentModifier`
- `MaxJumpCount`
- `OnLandedTime`
- `OnFallingTime`

### Dash

- `DashRecordTime`
- `DashZSnapOffset`
- `DashSpeed`
- `DashCooldown`
- `EndDashRunSpeed`
- `EndDashSprintSpeed`

### Power Slide

- `PowerSlideCooldown`
- `PowerSlideZOffset`
- `PowerSlideMinimalDurationForJump`
- `PowerSlideMinimalDuration`

### Rocket Jump / Jetpack

- `RocketJumpLockedActions`
- `RocketJumpLockedActionsDelay`
- `bRocketJumpAddJump`
- `bRocketJumpXYOverride`
- `bRocketJumpZOverride`
- `RocketJumpCooldown`
- `CurveGravity`
- `MinJetpackThreshold`
- `FuelDuration`
- `FuelConsumeOnUse`
- `AddFuelDurationOnJump`
- `AutoTriggerVelocityZ`

These names explain why the stock Unreal CharacterMovement CDO looked zeroed: Roboquest carries its own authored locomotion parameters in the native player layer.

## Unreal movement surface in the same executable

The shipping binary also retains the generic Unreal movement names needed for a clean integration strategy:

- `CalcVelocity`
- `GetMaxAcceleration`
- `K2_GetModifiedMaxAcceleration`
- `GroundFriction`
- `BrakingFriction`
- `BrakingDecelerationWalking`
- `BrakingDecelerationFalling`
- `MaxWalkSpeed`
- `MaxAcceleration`
- `AirControlBoostVelocityThreshold`
- `AddInputVector`
- `ConsumeInputVector`
- `INetworkPredictionInterface::GetPredictionData_Client`
- `INetworkPredictionInterface::GetPredictionData_Server`

The class name `URoboquestMovementComponent` is present as well.

## Revised implementation strategy

The target is now a hybrid native/cooked design:

1. keep Roboquest's native movement state machine and collision pipeline;
2. preserve its action semantics (Dash, Power Slide, jump, Grapple, Jetpack, Rocket Jump, jump pads);
3. inject the Momentum directional-acceleration/friction model at the velocity-integration seam;
4. avoid replacing actor position or floor/collision resolution;
5. allow the existing CharacterMovement/network prediction machinery to continue moving the capsule;
6. patch cooked Blueprint verbs such as Grapple only where their own implementation destroys or replaces useful momentum.

The preferred hook decision after runtime reflection is:

- if `URoboquestMovementComponent` overrides the relevant velocity virtual, hook that derived slot;
- otherwise hook the engine `UCharacterMovementComponent` velocity function and guard strictly on `URoboquestMovementComponent` / player ownership.

The runtime probe must resolve this instead of guessing a vtable index.
