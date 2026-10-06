# Roboquest Momentum — movement research

Status: initial static reverse-engineering pass complete; raw cooked handoff required next.

## Repository / branch decision

Momentum development lives on feature/movement-overhaul.

The branch was created from the mature feature/weapon-foundry head because that branch contains the reusable retoc/UAssetAPI/Kismet tooling. Momentum uses its own manifest, collector output, analyzer and eventual package identity. Weapon Foundry assets are not part of the Momentum release.

At branch creation, main was f27a23b2b911600e04779879d7bfc84e8c097503 and feature/weapon-foundry was 451edac5bb255b7744a7d40dab5e339dc6688d87. Weapon Foundry was 266 commits ahead and one commit behind main.

## Static player architecture

The committed FModel JSON establishes the following facts:

- Blueprint/Player/BP_APlayer derives from native RoboQuest Character_Player behavior.
- BP_APlayer owns a RoboquestMovementComponent named CharMoveComp.
- The cooked CharMoveComp has GravityScale=0, JumpZVelocity=0, MaxWalkSpeed=0, MaxAcceleration=0 and AirControl=0.
- MaxCustomMovementSpeed is 5000.
- BrakingDecelerationFalling is 200.
- WalkableFloorAngle is 36 degrees and MaxStepHeight is 102.
- bMaintainHorizontalGroundVelocity is false.
- BP_APlayer has bMovementPredict=true and bReplicateMovement=false.
- BP_APlayer exposes Blueprint-visible movement-adjacent events/functions including OnJumped, OnBlueprintLanded, DelegateOnTakeJumpad, SetDebugMovementActivate, GetDashTarget, GetDashLocation, GetDashGroundLocation, SetSprintEnabled and crouch/jump audiovisual hooks.
- BP_APlayer CDO Dash anchors include DashDuration=0.15, DashInputReactivationDelay=0.04, DashMinimalRange=300, DashOffset=200 and DashHeightOffset=60.
- BP_APlayer has JumpMaxCount=10000.

These values are not consistent with a normal Unreal CharacterMovement configuration driving gameplay. The strongest current inference is that Roboquest's real walking/jumping/falling integration is implemented in native Character_Player / RoboquestMovementComponent code, with Blueprints handling events, presentation and selected movement verbs.

That inference must now be validated against raw UAssetAPI bytecode and native reflected imports before implementation.

## Existing movement verbs

Static JSON confirms the following first-order seams:

### Dash

Blueprint/Skill/Ability/BP_PS_Dash derives from native APlayerSkill_Summon and binds an end-dash event. BP_APlayer owns the target/location collision-selection helpers and Dash tuning.

Dash must remain a semantic game event because existing items bind to it. The current research catalog includes Dash explosion, armor, speed, ammo, mark, heal, decoy and combo families.

### Power Slide

Blueprint/Item/Common/BP_PowerSlideSkill binds a Power Slide event back to BP_APlayer. Vanilla ships both CU_PowerSlide and CU_PowerSlide_Superbot.

The overhaul should replace or extend the physical behavior while preserving the native semantic Power Slide event.

### Grapple

Blueprint/Upgrade/Artefact/BP_Grapple is heavily Blueprint-authored. Relevant functions include StartAttract / StopAttract, StopLaunch, OnTickGrapple, CancelGrapple, UpdateGrappleRatio, CanUseGrapple, SetGrappleCollision and DealGrappleDamage.

This is a promising cooked-asset seam for preserving tangential velocity and implementing slingshot behavior without replacing the artifact identity.

### Jetpack

Blueprint/Upgrade/Artefact/BP_Jetpack is a thin Blueprint shell around player/native behavior. The player owns Jetpack VFX/audio, and vanilla ships CU_Jetpack plus CU_Jetpack_Gravity.

Horizontal-momentum preservation likely needs to occur in the player/movement layer rather than only in BP_Jetpack.

### Rocket Jump

BP_WS_RocketJump and BP_PS_RocketJump exist, together with CU_RocketJump and CU_RocketJump_DistanceRatio. The final system should treat the launch as an external impulse instead of a horizontal-velocity reset.

### Jump pads

BP_Jumpad derives from native AJumpad. It exposes GetImpulse, IsTubeEffect and IsSpecialExitingJumpad. Its cooked CDO has Impulse=2750.

Normal and tube/special jump-pad behavior therefore need separate validation before changing velocity composition.

## Class pass

The current class Blueprints all inherit BP_APlayer.

Commando, Engineer, Guardian, Magus and Sentinel show no class-local movement functions in the FModel pass. Recon exposes GetDashParticle, which is presentation rather than a locomotion integrator. Superbot exposes its own visual/status behavior and is the only class included in the first raw movement handoff because vanilla also ships CU_PowerSlide_Superbot.

All classes remain mandatory game-test targets even though their raw packages are not all requested in phase zero.

## Compatibility evidence already in the generated research catalog

The existing generated item catalog contains movement-sensitive rows including:

- ReloadSpeedAndMoveSpeed / Dexterity
- LineBreaker_FirerateMoveSpeed / Speed Freak
- AttackSpeedAndMoveSpeed / Turbo Boost
- DashExplosion and its elemental variants
- DashBonusSpeed / Relentless Pursuit
- DashBonusInfiniteAmmo / Locked and Loaded
- DashMark / Field Analysis
- DashDecoyCombat / Combat Decoy
- DashHeal / Tactical Rush
- DashArmor / Kevlar Pad
- DashCombo / Combo Dynamo
- GrappleBashDamage / Captain's Greetings
- GrappleRangeAndCooldown / Fine-Tuned Gadgets
- Hero Landing damage / armor / range families

The movement analyzer now scans the full committed vanilla-json tree and emits research/generated/movement_compatibility.json, so compatibility work does not depend on discovering these one crash at a time.

## Why raw assets are now required

The FModel corpus exposes classes, properties, references and signatures, but it does not provide enough compiled call-graph detail to prove where the native RoboquestMovementComponent integrates velocity each movement step.

The first raw handoff is intentionally narrow and is defined by Source/manifests/movement_patch_targets.txt.

Run:

    tools\windows\collect-movement-handoff.cmd

The collector:

1. reuses the proven selective legacy-asset collector;
2. copies only the movement manifest's uasset/uexp/ubulk files;
3. exports UAssetAPI JSON;
4. hashes every collected file;
5. runs movement seam analysis;
6. emits a movement compatibility catalog;
7. packages the result as handoff/movement-assets.zip.

Raw-bytecode fallback does not destroy the handoff. It is preserved as evidence because a failure to decode a critical native-facing function is itself an implementation decision point.

## Decision gate after handoff

The next implementation decision is:

1. identify native reflected RoboquestMovementComponent calls/properties available to cooked Blueprints;
2. map BP_APlayer / controller / Dash / slide / Grapple / Jetpack / rocket-jump / jump-pad compiled seams;
3. determine who owns movement authority and what is client-predicted;
4. prove whether a deterministic Source-style wish-direction integrator can live in cooked Blueprint/native-exposed movement hooks;
5. if not, define the smallest verified runtime extension that plugs into the existing movement/prediction pipeline.

Do not implement Momentum as ReceiveTick plus SetActorLocation and do not fake the overhaul with curve-only speed multipliers.
