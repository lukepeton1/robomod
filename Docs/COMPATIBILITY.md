# Compatibility

## Game / engine

Current verified target:

- Roboquest installed build used for the 2026-10-06 reverse-engineering pass.
- Unreal Engine serialization target: UE4.26.
- retoc legacy/Zen conversion: `UE4_26`.

A game update that changes `DT_WeaponAffix` or the patched Fragmentation Blueprint must be treated as a compatibility event and rebuilt from the new game assets.

## Weapon compatibility policy

The production core is generated from the extracted weapon/skill tables.

Current policy:

- broad composition primitives: 74 weapons whose primary skill is natively Projectile or Raycast and which are inside the game's broad elemental compatibility baseline;
- Seeker/Homing: 39 weapons whose primary skill is already Projectile;
- resolved transferable elite secondary fires: 15 native weapon-mod rows widened across the 74 standard chassis set;
- held back pending dedicated handling: Energy Gauntlets, Dual Colts, Boltgun, Superbot Weapon 2, Laser Sword, Panchaku.

Raycast + Seeker is not silently enabled yet. It requires a proper hit-model resolver.

## Verified combinations

The Phase 3 diagnostic confirmed one six-effect weapon executing:

- Seeker/Homing;
- Fragments;
- Burn;
- Explosive;
- Freewheel;
- Buckshot.

Observed behavior included fragment creation, Burn/explosion behavior, and Freewheel repeating the transformed Buckshot shot without obvious recursion or performance failure. Child-fragment homing remained visually difficult to isolate, so it is not listed as separately proven.

The cooked Fragmentation override and data-only compatibility changes both successfully load in-game.

## Other mods

Any mod replacing the same cooked packages can conflict:

- `/Game/Data/DT_WeaponAffix`
- `/Game/Blueprint/Weapon/Affixes/Common/BP_WA_Fragmentation`

IoStore load order determines which complete package wins when two mods override the same asset. Weapon Foundry does not attempt binary package merging at runtime.

## Multiplayer

Native Roboquest server/multicast seams are being preserved, but full modded-client multiplayer behavior has not yet completed its validation matrix. Do not claim unmodded-client compatibility.
