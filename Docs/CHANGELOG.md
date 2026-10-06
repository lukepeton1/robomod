# Changelog

## 0.1.0-dev — in development

### Verified foundation

- Built machine-readable catalog for weapons, skills, affixes, weapon mods and synergy primitives.
- Verified UE4.26 retoc -> legacy -> UAssetGUI -> Zen repacking workflow.
- Verified a data-only `DT_WeaponAffix` override loads in Roboquest.
- Verified a cooked Blueprint/Kismet override of `BP_WA_Fragmentation` loads in Roboquest.
- Added deterministic composition simulator and regression tests.
- Added fail-closed DataTable/UAssetAPI patch tooling.

### Composition

- Removed selected element, traversal and explosive pool exclusions.
- Generalized Fragmentation eligibility.
- Added Fragmentation GameplayTag inheritance from the originating skill.
- Confirmed an in-game diagnostic combining Seeker + Fragments + Burn + Explosive + Freewheel + Buckshot.
- Confirmed Freewheel re-fires the full Buckshot-transformed native skill.
- Confirmed no obvious infinite recursion or severe performance collapse in that diagnostic.

### Production branch

- Added generated safe eligibility policy: 74 standard Projectile/Raycast weapons and 39 projectile Seeker candidates.
- Added generated graft transfer policy.
- Added production build/install/uninstall/release packaging scripts.
- Added documentation and modified-asset tracking.

### In progress

- Native graft transaction and donor consumption.
- Smith/editor interaction.
- Save/load and multiplayer validation.
- Raycast + Seeker resolver.
- Duplicate modifier-instance provenance.
