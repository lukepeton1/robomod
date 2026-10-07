# Roboquest Momentum runtime architecture

## Objective

Momentum must change velocity integration without replacing Roboquest's collision, floor detection, movement states, network ownership or correction path.

The runtime layer is deliberately narrow.

## Production split

### Runtime/native core

Responsible for ground directional acceleration, ground friction, airborne wish-direction acceleration, momentum-preserving jump/landing behavior, high-speed safety damping, wallrun velocity integration, wall-kick impulses, common external-impulse composition, and telemetry from the authoritative movement step.

### Cooked Blueprint / data patches

Responsible where appropriate for Grapple behavior and release semantics, Dash semantic compatibility, Power Slide events and content interactions, camera/FOV/audio/VFX, item/perk event preservation, debug UI, and curves/authored content values.

## Hook rule

Do not hook `AActor::Tick` to set actor transforms. Do not implement movement as a second independent physics loop.

The preferred integration point is the velocity calculation used by the existing `URoboquestMovementComponent`.

The runtime probe must establish whether the component overrides an engine movement virtual such as `CalcVelocity`. If the derived movement component does not override the velocity virtual, the fallback is a base CharacterMovement detour guarded by exact component class, exact owning player class, movement state, and explicit feature enablement.

## Prediction

The cooked player has `bMovementPredict=true` and `bReplicateMovement=false`.

Momentum must therefore be deterministic from the same predicted inputs and state used by the game's movement component. The mod must not add per-frame position RPCs.

## Core implementation

`Source/runtime/momentum_core.*` is dependency-free C++ implementing the same directional acceleration and velocity-composition equations as `tools/simulate_movement.py`.

It intentionally knows nothing about UObject layouts. The eventual adapter will translate Roboquest/Unreal vectors, movement input, and movement state into the core and then write the resulting velocity back through the native movement component.
