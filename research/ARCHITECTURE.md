# Roboquest weapon-system reverse engineering notes

Status: first-pass catalog from the installed-build JSON property exports in `vanilla-json/`.

These notes are intentionally limited to facts visible in the extracted build. Anything that still depends on a missing DataTable row, compiled Blueprint bytecode, or native `/Script/RoboQuest` implementation is marked as unresolved rather than guessed.

## Export inventory

The current dump contains 1,977 JSON assets and parses with zero JSON errors.

| Area | Assets in current export |
| --- | ---: |
| Weapon prefabs (`Blueprint/Weapon/Prefab`) | 92 |
| Weapon affix Blueprints (`Blueprint/Weapon/Affixes`) | 142 |
| Weapon skill Blueprints (`Blueprint/Skill/Weapon`) | 108 |
| Projectile Blueprints (`Blueprint/Projectile`) | 29 |
| Interactive Blueprints (`Blueprint/Interactive`) | 243 |
| Item Blueprints (`Blueprint/Item`) | 484 |
| Upgrade Blueprints (`Blueprint/Upgrade`) | 42 |
| HUD Blueprints (`Blueprint/HUD`) | 334 |

## High-level architecture visible in the build

### Weapon chassis

All 92 exported weapon prefabs derive from `BP_AWeapon_C`, which itself derives from the native `AWeapon` class in `/Script/RoboQuest`.

`BP_AWeapon_C` owns/references both an `AStatManager` (`WeaponStatManager`) and an `ASkillManager` (`WeaponSkillManager`). Its default object also directly references `DT_WeaponAffix` and `DT_WeaponMod`.

This strongly separates the weapon chassis/visual actor from the data-driven skill and affix definitions. A weapon body can therefore remain the identity-preserving chassis while composition work targets the skill/affix layer.

### Weapon skills

The export contains 108 weapon skill Blueprints. Their native parent distribution is:

- 86 `APlayerSkill_Automatic`
- 7 `APlayerSkill_Burst`
- 5 `APlayerSkill_Summon`
- 4 `APlayerSkill`
- 4 `APlayerSkill_Scope`
- 2 `APlayerSkill_Beam`

Many weapon skill assets are intentionally thin Blueprint subclasses. For example, `BP_PF_AssaultRifle_C` exposes essentially no per-weapon firing parameters in its JSON default object. `DA_CommonSkillData` points to `DT_PlayerSkills`, `DT_ModSkills`, `DT_EnemySkill`, and `DT_AllySkill`, so the missing skill DataTables are required to recover the actual damage/fire-rate/hit-mode/projectile rows.

### Affixes are behavior objects, not just scalar stats

The export contains 142 weapon-affix Blueprints. The base is `BP_AWeaponAffix_C`, derived from native `AWeaponAffix`.

Reusable behavior bases already exist for the kinds of event-driven composition the overhaul needs. In particular:

- `BP_AWeaponAffix_TriggerSkillCount_C`
- `BP_AWeaponAffix_TriggerSkillLuck_C`
- `BP_AWeaponAffix_OnHitHitEffect_C`
- `BP_AWeaponAffix_OnDealDamage_C`
- `BP_AWeaponAffix_OnKillEffect_C`
- `BP_AWeaponAffix_PlayerTrigger_C`
- `BP_AWeaponAffix_FirstAmmo_C`
- `BP_AWeaponAffix_LastAmmo_C`
- `BP_AWeaponAffix_AddSecondaryFire_C`

Twenty-two exported weapon-mod affixes directly derive from `BP_AWeaponAffix_AddSecondaryFire_C`. Its class exposes an `InClass` skill-class field. This is a major existing seam for transferable alt-fire behavior rather than a reason to build a detached custom alt-fire system.

### Core compositional affixes already attach to skills

The following findings come directly from compiled Blueprint metadata and temporary/local variable names in the JSON export:

- `BP_WA_Bounce_C` calls `GetSkill`, reads custom float properties, and stores a `BounceAmount`.
- `BP_WA_Pierce_C` applies/removes itself through `GetSkill`.
- `BP_WA_Homing_C` calls `GetSkill`, checks skill classes and hit types, dynamically casts to `APlayerSkill`, and exposes `AffectedHitTypes`.
- `BP_WA_AddRicochet_C` calls `GetSkill` and changes both integer and float values derived from affix custom properties.
- `BP_WA_ProjectileRaycast_C` applies/removes itself through `GetSkill` and has a `GetModifiedSpawnRotationOffset` hook. This is the most obvious existing compatibility seam for raycast/projectile conversion.
- `BP_WA_Burn_C`, `BP_WA_Ice_C`, and `BP_WA_Shock_C` call `GetSkills`, inspect gameplay-tag lists, and register to skill events rather than existing only as weapon-level labels.
- `BP_WA_Explosive_C` derives from `TriggerSkillCount`, examines gameplay tags in `IsSkillConditionValid`, gets the weapon stat manager, and spawns a modifier object on a valid trigger.

This is favorable for composition: the base game already treats many affixes as code that mutates/listens to skills.

## Fragmentation is the strongest existing child-attack seam

`BP_WA_Fragmentation_C` is especially important.

Its exported compiled-function metadata shows that it:

- retrieves the weapon's skills via `GetSkills`;
- binds an event receiving a `Skill`, `RQHitResult`, and `AProjectile`;
- derives gameplay tags for the originating attack;
- checks class/bitmask conditions;
- constructs `NetworkSkillInfo` structs;
- constructs quantized network vectors;
- uses a `RandomStream`;
- invokes `SpawnCustomProjectiles`;
- computes child spawn positions/rotations with deterministic-looking indexed math.

Therefore Roboquest already has a network-aware path for an affix to create child projectiles from a parent skill/hit. The first implementation target for modifier inheritance should be to understand and extend this path rather than inventing an independent projectile framework.

## Rarity already is a composition budget

`DA_CommonWeaponData` directly exposes the game's affix-generation structure. It contains:

- `AffixRangeByWeaponLevel`
- `AffixBundleByLevel`
- `AffixLevelForWeaponQuality[1..4]`
- common/rare/elite affix luck tables
- separate base/starter/max/merchant/special generation luck
- upgrade luck and special-upgrade luck

`AffixBundleByLevel` already combines `EWeaponAffixRarity::Common` and `EWeaponAffixRarity::Rare` into `EWeaponColor::{Base,Common,Rare,Epic,Legendary}` packages. The visible quality breakpoints are 2, 4, 6, and 10.

This supports the design requirement to use vanilla rarity/quality as the complexity budget instead of creating a parallel slot progression system.

## Existing merchant/smith flows can host grafting

The extracted interactive assets expose several native upgrade surfaces:

- `BP_Interactive_Merchant_RerollAffix_C`
- `BP_Interactive_Merchant_UpgradeWeaponQuality_C`
- `BP_Interactive_Merchant_AddEnchantedAffix_C`
- `BP_Merchant_UpgradeAffix_C`
- shooting-range equivalents
- `BP_Quest_SmithingTed_C`

`BP_Interactive_Merchant_AddEnchantedAffix_C` is particularly useful. Its `AffixData` structure contains the affix class, custom float properties, rarity, pool additions/removals, compatible weapons, icon/description data, and activation state. Its Blueprint calls `GetDataTableRowFromName` during initialization.

`BP_Merchant_UpgradeAffix_C` already gets DataTable row names, reads affix rows, chooses affixes, and exposes two add-affix interactives plus a weapon-quality upgrade interactive.

`BP_Interactive_Merchant_RerollAffix_C` calls `IsServer` in its event graph and the merchant weapon spawner is also server-aware. This makes the existing merchant path the current preferred grafting surface because it already has currency, validation, weapon-state, and multiplayer plumbing.

The dropped-weapon actor `BP_Interactive_Weapon_C` is replicated and uses server validation, so a direct ground-drop `GRAFT` action remains plausible, but it should be attempted only after the native merchant/add-affix path is understood.

## Element system: current evidence warns against assuming true multi-element state

The game has strong centralized elemental support:

- `DA_CommonSkillData` maps Fire/Ice/Shock to explosion, trail, projectile, and bash VFX.
- Element-specific affixes operate on skill gameplay tags.
- Element-specific item/perk logic is widespread in the dump.

However several visible structures are singular:

- `BP_AWeapon.SetWeaponElement(Element: EElement)` takes one `EElement`.
- `BP_AWeapon.RemoveWeaponElement(Element: EElement)` takes one `EElement`.
- `BP_Proj_ElementalMissile_C` has one `CurrentElement`.
- `BP_Proj_ElementalRocket_C` has one `CurrentElement`.
- `DMod_Elements_C` has one `CurrentElement`.
- `BP_WA_RandomElemental_C` chooses one element at a time.

Gameplay tags may still permit more than one elemental semantic to participate in an attack, but true simultaneous Burn + Ice + Shock cannot be claimed until `DT_PlayerSkills`, `DT_WeaponAffix`, and the relevant native/compiled paths are inspected. A safe implementation may ultimately represent multi-element composition as multiple native status/damage contributions rather than one impossible multi-valued `EElement` field.

## Multiplayer implications discovered so far

The JSON metadata is encouraging but not sufficient for a replication guarantee:

- dropped weapons use replicated/server-validated interactive actors;
- merchant mutation flows include `IsServer` checks;
- fragmentation constructs `NetworkSkillInfo` and quantized network vectors;
- many generated Blueprint classes have replication data set up.

The overhaul should preserve those native authority paths. Child-attack composition should preferentially extend the same `NetworkSkillInfo`/skill-manager model instead of spawning client-only actors.

## Current implementation direction

The working architecture is therefore:

1. **Weapon chassis remains vanilla.** Preserve each weapon actor, animation, recoil, sound, resource model, and innate behavior.
2. **Resolved weapon composition is represented through the native affix/skill system.** Avoid a second parallel damage system.
3. **Grafting reuses existing affix-row structures and merchant/server-authoritative transactions.** A donor weapon supplies a row/affix instance; the target weapon receives it through the same underlying structures used by normal affix assignment.
4. **Composition work starts at the existing child-attack seams.** Fragmentation, trigger-skill affixes, secondary-fire affixes, and projectile/raycast conversion are first-class targets.
5. **Inheritance is expressed by propagating native gameplay tags, skill/stat modifiers, and compatible affix semantics into child `NetworkSkillInfo`/spawned skills.** Exact fields remain unresolved until the missing DataTables/raw cooked assets are available.
6. **Recursion protection must be attached to modifier provenance, not a global DPS cap.** This likely requires runtime state beyond static DataTable edits, so it remains an implementation-risk item rather than being hand-waved as solved.

## Data-only versus runtime conclusion (provisional)

The export proves that substantial parts of the requested design can use native cooked assets and existing Blueprint behavior. It does **not** prove that arbitrary recursive modifier inheritance can be implemented by DataTable edits alone.

Specifically, the requested generalized child-event ancestry, per-modifier recursion suppression, and propagation of an arbitrary affix package into newly spawned child attacks appear to require changes to Blueprint behavior or native runtime logic. The JSON export exposes Blueprint signatures and call sites but not editable Kismet bytecode.

Accordingly, the next technical gate is to obtain the exact DataTable rows and then the raw cooked assets for the small set of Blueprints that actually need patching. The goal remains `PAK-only` if those Blueprint assets can be safely modified/repacked; a runtime loader is not justified yet.
