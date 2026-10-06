# Roboquest Momentum — movement model

Status: reference physics model only; not yet wired into the game.

The project now has an engine-independent simulator in `tools/simulate_movement.py` and authored tuning in `Source/movement/movement_config.json`.

The simulator is deliberately separate from Roboquest. Its job is to define the velocity semantics that the eventual native movement layer must reproduce and to catch tuning/regression mistakes before they are encoded in a cooked or runtime patch.

## Core rule

Movement uses directional acceleration, not a total-speed clamp.

For horizontal velocity **v**, normalized requested movement direction **d**, wish speed **s**, acceleration **a**, and timestep **dt**:

`current = dot(v, d)`

`add = s - current`

If `add > 0`:

`v = v + d * min(add, a * s * dt)`

This is the foundation for Source-style air strafing.

The important consequence is that the requested directional component is limited while total horizontal speed may exceed ordinary run speed when the player earns it by changing directions, using terrain, or combining movement impulses.

## Ground

Ground movement applies authored friction and then strong directional acceleration.

The reference friction model integrates:

`ds/dt = -friction * max(speed, stop_speed)`

This produces responsive stopping without simply overwriting the velocity vector.

A high-speed 180-degree reversal therefore decelerates/reaccelerates through the actual velocity state instead of instantly flipping direction.

## Air

Air movement uses the same directional projection model with a lower directional wish cap.

The simulator intentionally demonstrates both:

- holding forward in the air does not create free speed once that directional component is saturated;
- a coordinated changing strafe direction can increase total horizontal speed.

There is no ordinary hard clamp on total airborne speed.

A soft high-speed damping region and a much higher absolute emergency cap exist only as stability controls.

## Slide

Slide begins from actual incoming velocity.

The reference model uses much lower friction than ordinary ground movement, limited directional steering, no canned speed grant, and full remaining horizontal momentum into a slide jump.

This makes `speed -> slide -> jump -> air strafe` compositional rather than scripted.

## Wallrun / wall kick

The reference wallrun projects horizontal velocity onto the wall tangent, accelerates only along that tangent, applies reduced gravity, preserves vertical state except for authored gravity, and adds outward/upward wall-kick impulses on exit.

Collision/contact eligibility and same-wall abuse prevention are intentionally not simulated here because those require the real engine geometry layer.

## External impulse policy

The config explicitly separates normal desired speed from movement impulses.

Dash, Grapple release, Rocket Jump, jump pads and wall kicks must be implemented as documented velocity operations rather than hidden replacements.

The default policy is:

- preserve existing horizontal velocity;
- add the authored horizontal impulse;
- explicitly decide whether the vertical component is additive or replaced;
- never multiply accumulated current velocity every frame;
- apply the absolute safety cap only if physics/network stability is threatened.

## Frame-rate validation

The simulator runs the same scenarios at 60, 120, 144 and 240 Hz.

The current reference suite requires the 60 Hz result to stay within 1.5% of the 240 Hz reference for both position and velocity on every modeled scenario.

The scenarios currently cover forward acceleration, braking, 180-degree reversal, forward-only air input, coordinated air strafe, slide, slide hop, wallrun + wall kick, Dash impulse, Grapple release impulse and Rocket Jump impulse.

These tests do not prove Roboquest runtime frame invariance. Once the native layer is implemented, equivalent in-game telemetry must validate the real movement pipeline.

## Tuning status

The checked-in values are a simulation baseline, not final release tuning.

The ordinary 1050 cm/s reference target is anchored to the tail of vanilla `CU_PowerSlide`, not asserted to be the exact native walk/run speed.

Vertical, acceleration, wallrun, lurch and impulse constants remain provisional until the native movement probe exposes enough of the live integrator to measure/validate them.

The architecture is intentional even where the constants are not final.
