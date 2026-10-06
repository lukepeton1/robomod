# Known issues / open validation

## Implemented but awaiting in-game validation

- Production **Raycast + Seeker** resolver: Kismet layout, round-trip and semantic verification pass, but a native Raycast weapon still needs an in-game smoke test.
- Six-affix Foundry purchase guard.
- The widened 15-row native alt-fire compatibility matrix.
- Save/load persistence of ordinary Foundry-added affixes.
- Full host/client convergence.

## Remaining implementation work

- Ground-weapon **GRAFT** row selection and donor consumption.
- Full deterministic Smith/editor interface.
- Duplicate copies of spawn/proc affixes need modifier-instance provenance before being deliberately exposed as a supported build mechanic.
- Per-alt-fire child-effect inheritance needs validation/profile tuning.

## Donor GRAFT blocker

The current cooked handoff exposes dropped-weapon `AffixAmount` / bundle metadata but not an API that enumerates the actual ordinary affix row IDs on the donor.

The existing weapon tooltip clearly renders six affix entries, but its FModel export derives from native `WeaponTooltipWidget` and exposes no Blueprint functions. The legacy handoff manifest has therefore been expanded to collect:

- `WGT_Tooltip_Weapon`;
- `WGT_Tooltip_WeaponAffix`;
- related merchant/tooltips/interactives;
- additional weapon-spawner/player-controller seams.

That next raw handoff is the cleanest route to implementing exact donor-row selection without guessing or adding a runtime framework.

## Compatibility edge cases

The production generator still withholds unusual `None`/unresolved chassis such as Energy Gauntlets, Laser Sword, Panchaku and a few special weapon rows until their skill representation is explicitly handled.

## Visuals

Multi-element gameplay semantics can coexist even if a mesh/projectile chooses one dominant element visual.

## Fragment homing

Parent Seeker and fragment Burn/explosion behavior were confirmed. Independent child-fragment homing remained visually difficult to isolate and is still marked unconfirmed.

## Game updates

Weapon Foundry overrides complete cooked packages. If Roboquest updates a modified package, rebuild against the updated game files instead of continuing to use an old cooked override.
