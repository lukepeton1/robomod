# Modified assets

## Release-candidate production packages

### `/Game/Data/DT_WeaponAffix`

- removes selected artificial compatibility exclusions;
- broadens safe composition eligibility across 74 standard chassis;
- expands Seeker to those 74 chassis now that a live hit-model resolver exists.

Source: `Source/patches/weapon_foundry_core.json`

### `/Game/Data/DT_WeaponMod`

- broadens 15 resolved transferable native secondary-fire rows across the standard 74 chassis set.

Source: `Source/patches/weapon_foundry_mods.json`

### `/Game/Blueprint/Weapon/Affixes/Common/BP_WA_Fragmentation`

- removes the restrictive gameplay-tag gate;
- validates the spawned child for tag propagation;
- copies GameplayTags from the originating `ASkill`;
- preserves the vanilla `CustomTag = Fragmentation` recursion guard.

Source: `tools/patch_fragmentation_bytecode.py`

### `/Game/Blueprint/Weapon/Affixes/Prefab/BP_WA_Homing`

- inserts live Raycast → Projectile conversion while Seeker is applied;
- applies shipped `ProjectileSpeed` / `ProjectileCollisionSize` values;
- zeros gravity while converted;
- relies on vanilla `OnRemove` to restore `BaseHitType`;
- rebases absolute Kismet flow targets after insertion.

Source: `tools/patch_homing_resolver.py`

### `/Game/Blueprint/Interactive/Merchant/BP_Merchant_UpgradeAffix`

- seeds native `AffixRows : Array<Name>` with the 15 globally safe, pairwise conflict-free ordinary-affix pool;
- leaves native random offer generation, UI and transaction logic intact.

Source: `Source/patches/foundry_merchant.json`

### `/Game/Blueprint/Interactive/Merchant/BP_Interactive_Merchant_AddEnchantedAffix`

- inserts a six-affix `CanInteract` guard using native `AWeapon.AffixAmount`;
- preserves existing vanilla validity / current-row checks and purchase event.

Source: `tools/patch_foundry_interactive.py`

## Diagnostic-only assets

Phase 3 additionally overrode:

- `/Game/Data/DT_Weapons`;
- `/Game/Data/DT_PlayerSkills`.

Those starter-HandGun overrides are not present in the production release candidate.

## Planned donor assets

The expanded raw-handoff target list includes the weapon-tooltip, weapon-spawner, player-controller and related interaction assets needed to finish donor-row selection. They are not production overrides yet.

## Vanilla assets

Release packages do not contain the user's extracted vanilla `.uasset/.uexp` files.
