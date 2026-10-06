# Missing game-data exports

The current JSON dump is sufficient to map the Blueprint class graph and identify the implementation seams, but it does **not** include the root DataTables referenced by those Blueprints.

These are not speculative names: they are object paths referenced by the installed-build JSON.

## Tier 1 — required for the weapon/affix catalog

Export the following root assets from `RoboQuest/Content/Data/` as JSON Properties when the research pass reaches the table-resolution step:

- `DT_Weapons.uasset`
- `DT_PlayerSkills.uasset`
- `DT_WeaponAffix.uasset`
- `DT_WeaponMod.uasset`
- `DT_ModSkills.uasset`
- `DT_Items.uasset`

Why:

- `DT_Weapons` is required to map weapon row IDs, names, weapon classes, primary/secondary skill row handles, magazine/resource fields, innate affixes, and per-chassis metadata.
- `DT_PlayerSkills` is required to recover the actual skill data that the thin `BP_PF_*`/`BP_SF_*` subclasses consume.
- `DT_WeaponAffix` is required to map affix row names to the 142 exported affix classes, rarity, custom float properties, pools, compatibility, descriptions/icons, and stacking parameters.
- `DT_WeaponMod` is required for alt-fire/mod assignment and compatibility.
- `DT_ModSkills` is required to resolve secondary/mod skill rows.
- `DT_Items` is required for the systematic item-compatibility pass.

## Tier 2 — progression/economy/loot integration

- `DT_Loot.uasset`
- `DT_LootBundles.uasset`
- `DT_BazarItems.uasset`
- `DT_Artefacts.uasset`

These are referenced by the current dump and are needed to quantify weapon-drop generation and verify the Power Cell / merchant economy against real loot structures.

## Tier 3 — UI/localization support

- `DT_RichText_Affix.uasset`
- `DT_RichText_Skill.uasset`
- `DT_KeywordDescription.uasset`
- `DT_RichText_Interact.uasset`

These help preserve native wording and tooltip formatting.

## Raw cooked assets likely to be needed later

Do **not** export all raw assets yet. Once the table pass is complete, the first raw `.uasset`/sidecar targets are expected to be a small subset around:

- `Blueprint/Weapon/BP_AWeapon`
- `Blueprint/Weapon/Affixes/BP_AWeaponAffix`
- `Blueprint/Weapon/Affixes/BP_AWeaponAffix_AddSecondaryFire`
- `Blueprint/Weapon/Affixes/BP_AWeaponAffix_TriggerSkillCount`
- `Blueprint/Weapon/Affixes/BP_AWeaponAffix_TriggerSkillLuck`
- `Blueprint/Weapon/Affixes/Common/BP_WA_Fragmentation`
- `Blueprint/Weapon/Affixes/Common/BP_WA_Explosive`
- `Blueprint/Weapon/Affixes/Prefab/BP_WA_Bounce`
- `Blueprint/Weapon/Affixes/Prefab/BP_WA_Pierce`
- `Blueprint/Weapon/Affixes/Prefab/BP_WA_Homing`
- `Blueprint/Weapon/Affixes/Prefab/BP_WA_ProjectileRaycast`
- `Blueprint/Interactive/Merchant/BP_Interactive_Merchant_AddEnchantedAffix`
- `Blueprint/Interactive/Merchant/BP_Interactive_Merchant_RerollAffix`
- `Blueprint/Interactive/Merchant/BP_Interactive_Merchant_UpgradeWeaponQuality`
- `Blueprint/Interactive/Merchant/BP_Merchant_UpgradeAffix`
- `Blueprint/Interactive/Reward/BP_Interactive_Weapon`
- relevant tooltip widgets under `Blueprint/HUD/Tooltip/Weapon/`

The exact raw-asset request should be narrowed after resolving the DataTables. The purpose of this file is to avoid another broad export dump.
