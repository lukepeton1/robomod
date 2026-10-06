# Changelog

## 0.1.0-rc1

### Verified foundation

- Built machine-readable catalogs for weapons, skills, affixes, weapon mods and synergy primitives.
- Verified UE4.26 retoc → legacy → UAssetGUI → Zen repacking.
- Verified data-only `DT_WeaponAffix` overrides load in Roboquest.
- Verified cooked Blueprint/Kismet Fragmentation overrides load in Roboquest.
- Added fail-closed DataTable/CDO/Kismet patch tooling and deterministic layout validation.
- Added CI regeneration checks and native networking-contract tests.

### Composition

- Removed selected artificial element/traversal/explosive exclusions.
- Generalized Fragmentation eligibility.
- Added Fragmentation GameplayTag inheritance from the originating skill.
- Confirmed an in-game diagnostic combining Seeker + Fragments + Burn + Explosive + Freewheel + Buckshot.
- Confirmed Freewheel re-fires the complete Buckshot-transformed native skill.
- Confirmed no obvious infinite recursion or severe performance collapse in that diagnostic.
- Enabled Seeker + Bounce and Seeker + Buckshot where native state is compatible.

### Raycast Seeker

- Added non-same-shape cooked-Kismet insertion support.
- Added absolute Kismet flow-offset rebasing.
- Added live `BP_WA_Homing` resolver:
  - `HitType = Projectile`;
  - projectile speed/collision from the shipped Homing custom parameters;
  - zero gravity while applied;
  - vanilla removal restores `BaseHitType`.
- Expanded production Seeker eligibility to all 74 standard Projectile/Raycast chassis.
- Static/round-trip verification passes; final in-game raycast smoke test is pending.

### Native alt-fires

- Broadened 15 resolved native elite secondary-fire/weapon-mod rows across the 74 standard chassis set.
- Kept every secondary fire on Roboquest's native `AddSecondaryFire` / skill-manager path.

### Foundry progression

- Generated transfer policy: 49 ordinary affixes + 15 resolved alt-fires.
- Promoted the successful ordinary-affix merchant probe into production.
- Vanilla Perfumer/affix merchant now acts as the first Foundry surface using native Power Cell/UI/server/multicast behavior.
- Added six-affix purchase guard.
- Added authoritative graft transaction contract for the final donor workflow.

### Packaging

- Added one-command production build/install.
- Added uninstall helpers.
- Added versioned release ZIP packager.
- Added build manifest and SHA-256 container hashes.
- Release source package contains the tooling required to reproduce all production patches without extracted game assets.

### Remaining

- Ground-donor GRAFT row selection / donor consumption.
- Full deterministic Smith/editor UX.
- Save/load persistence validation.
- Host/client multiplayer validation.
- Duplicate spawn/proc modifier-instance provenance.
- Per-alt-fire inheritance validation.
- Final validation of unusual `None`/unresolved weapon chassis.
