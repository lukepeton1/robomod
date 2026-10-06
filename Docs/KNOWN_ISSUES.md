# Known issues / open validation

This file separates actual blockers from features that are simply not finished yet.

## Open implementation work

- Ground-weapon **GRAFT** action is not yet wired to live ordinary affix storage.
- Smith/editor workflow is not yet wired.
- Exact persistence of grafted ordinary multi-affix state through run save/load is not yet proven.
- Full host/client multiplayer validation is pending.
- Raycast + Seeker needs a proper raycast-to-projectile resolver.
- Duplicate copies of spawn/proc affixes need modifier-instance provenance before being generally enabled.
- Alt-fire inheritance needs per-skill-profile validation.

## Compatibility edge cases

The production eligibility generator currently withholds several unusual weapon rows from broad compatibility until their skill representation is resolved/tested individually.

## Visuals

Multi-element gameplay tags can coexist, but a weapon/projectile may still render only one dominant element visual. Visual representation and gameplay semantics must be evaluated separately.

## Fragment homing

The Phase 3 diagnostic clearly showed the parent projectile homing and confirmed fragment/status/explosion behavior. Whether every generated fragment independently acquired homing was difficult to determine visually and remains an isolated test item.

## Updating Roboquest

Weapon Foundry overrides complete cooked packages. If Roboquest updates either modified package, rebuild the mod against the updated files instead of continuing to use an old cooked override.
