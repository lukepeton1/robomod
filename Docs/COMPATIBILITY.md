# Compatibility

## Game / engine

Current target:

- Roboquest installed build used for the 2026-10-06 reverse-engineering pass;
- Unreal Engine serialization target: UE4.26;
- retoc legacy/Zen conversion: `UE4_26`;
- UAssetGUI v1.1.0 with `VER_UE4_26`.

Any Roboquest update touching a modified cooked package is a compatibility event and should trigger a rebuild/retest.

## Weapon policy

Release-candidate policy:

- broad composition primitives: 74 standard Projectile/Raycast chassis;
- Seeker/Homing: 74 standard chassis through the live hit-model resolver;
- native elite secondary fires: 15 resolved rows widened across the 74 standard chassis;
- held back: unusual `None`/unresolved edge cases.

The Seeker resolver is implemented and statically verified, but its Raycast path still needs final in-game validation.

## Verified composition

The Phase 3 diagnostic confirmed:

- Seeker;
- Fragments;
- Burn;
- Explosive;
- Freewheel;
- Buckshot;

on one weapon at the same time, including Freewheel repeating the complete Buckshot shot and fragment/status/explosion behavior without obvious recursion/performance collapse.

## Package conflicts

The release candidate overrides:

- `/Game/Data/DT_WeaponAffix`;
- `/Game/Data/DT_WeaponMod`;
- `/Game/Blueprint/Weapon/Affixes/Common/BP_WA_Fragmentation`;
- `/Game/Blueprint/Weapon/Affixes/Prefab/BP_WA_Homing`;
- `/Game/Blueprint/Interactive/Merchant/BP_Merchant_UpgradeAffix`;
- `/Game/Blueprint/Interactive/Merchant/BP_Interactive_Merchant_AddEnchantedAffix`.

Another mod overriding one of the same complete cooked packages will conflict unless the changes are composed before packing.

## Multiplayer

The production Foundry transaction intentionally preserves Roboquest's reliable server + multicast affix path. CI asserts those RPC signatures remain present. Full host/client behavior still requires an in-game validation pass; unmodded-client compatibility is not claimed.
