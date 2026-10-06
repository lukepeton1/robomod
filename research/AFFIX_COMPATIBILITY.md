# Affix compatibility: installed-build findings and resolver policy

This document separates **current vanilla eligibility** from **technical compatibility**. The overhaul is allowed to relax vanilla pool restrictions only where the underlying skill/affix code has a coherent behavior.

All counts below are generated from the installed-build `DT_Weapons`, `DT_PlayerSkills`, and `DT_WeaponAffix` exports.

## Current skill population

The current catalog resolves every weapon action and every weapon-mod secondary skill row with no unresolved links.

Among player skill rows that specify a skill class:

- 74 use `EHitType::Projectile`
- 49 use `EHitType::Raycast`
- 34 use `EHitType::None`
- 1 uses `EHitType::AIM`

There are 92 real weapon chassis rows, of which 86 are shipping-lootable.

## Restrictions that are demonstrably design restrictions

Several affixes already operate across both raycast and projectile weapons. Their current pool exclusions therefore must not be treated as engine laws.

| Affix | Current eligible weapon rows | Projectile primaries | Raycast primaries | Key observation |
| --- | ---: | ---: | ---: | --- |
| Bounce | 40 | 10 | 28 | Native behavior already spans both hit models. |
| Pierce | 48 | 17 | 29 | Native behavior already spans both hit models. |
| Ricochet | 69 | 33 | 32 | Native behavior already spans both hit models. |
| Freewheel | 49 | 30 | 15 | Trigger-based duplication is not projectile-only. |
| Buckshot | 34 | 14 | 18 | The affix modifies hit amount/shot geometry on both models. |
| Explosive | 9 | 5 | 4 | The blank explosive behavior is already cross-model. |
| Megaboom | 19 | 16 | 2 | Explosion enhancement is not strictly projectile-only. |
| Burn | 80 | 39 | 35 | Also supports several `None`/melee-like skills. |
| Cryo | 80 | 39 | 35 | Same broad skill coverage as Burn. |
| Shock | 80 | 39 | 35 | Same broad skill coverage as Burn. |

The remaining counts in these rows are special/secondary/no-primary cases rather than contradictory hit types.

### Immediate resolver consequence

The overhaul should **not** preserve a blanket incompatibility such as Bounce vs Ricochet merely because vanilla `RemovedPool` entries currently exclude one another. The installed build proves that each mechanic independently supports the same broad classes of skills.

Instead, compatibility should be resolved at the actual skill/event level.

## Seeker / Homing

The `Homing` affix currently has only seven compatible weapon rows, all projectile primaries.

However, `BP_WA_Homing_C` itself has:

`AffectedHitTypes = { Projectile, Raycast }`

and its graph explicitly checks skill classes/hit types and mutates the player skill. This is evidence that its implementation was written with more than one hit model in mind even though the shipped affix row restricts its pool.

A raycast has no flight path to steer, so the overhaul still needs a **raycast -> projectile compatibility conversion** before homing can have meaningful physical behavior.

The shipped `ProjectileRaycast` affix is the inverse operation: it is named **Hitscan**, is currently offered only to projectile weapons, and changes projectile-style behavior toward raycast behavior. Its existence proves that hit-model conversion is already a normal affix concept.

The Roboquest-specific modding tutorial also demonstrates the other direction manually by changing `TargetDetection` from Raycast to Projectile and assigning projectile speed/VFX in `DT_PlayerSkills`.

### Resolver policy

For `Raycast + Seeker`:

1. resolve the source skill row;
2. create/use a projectile-compatible derivative of that row;
3. preserve damage, fire rate, recoil, muzzle behavior, sound and effective range;
4. select an existing projectile/trail visual appropriate to the source weapon;
5. assign a high projectile speed appropriate to the source gunfeel;
6. apply the native Homing affix to the converted skill;
7. keep the conversion semantic internal—the player should still see the normal weapon/affix vocabulary.

This conversion must be generated deterministically from installed data rather than hand-maintaining a list of specific guns.

## Bounce + Pierce

Vanilla `Pierce` removes the `Explosive2..5` pool, while `Bounce` removes `Ricochet`. Those are shipped generation restrictions, not proof that traversal states are mutually exclusive.

For composed projectile attacks:

- enemy collisions consume pierce budget;
- surface collisions consume bounce budget;
- neither budget should silently erase the other;
- after a bounce, homing may reacquire when Seeker is active;
- the same projectile retains its elemental/status payload.

For raycast attacks, preserve the game's native raycast implementation of the relevant affix rather than unnecessarily forcing a projectile conversion.

## Pierce + Explosive

Vanilla pool rules currently prevent several explosive variants from coexisting with Pierce. The overhaul intentionally relaxes this.

Resolver behavior:

- each eligible enemy collision can generate the native explosive payload;
- the projectile/raycast continues while pierce budget remains;
- the explosion is a child damage event and inherits compatible elemental/status semantics;
- the same Explosive modifier instance is marked as consumed for that explosion branch so explosion-generated damage cannot recursively regenerate itself forever.

## Ricochet

Ricochet already spans raycast and projectile skills.

A ricochet child hit inherits compatible passive semantics such as:

- elements/status application;
- damage-type semantics;
- compatible explosive payload;
- critical eligibility as defined by the originating skill;
- other traversal modifiers where physically meaningful.

The **same Ricochet modifier instance** does not recursively create another ricochet from its own child. Separate Ricochet instances may each participate.

The shipped `AddRicochet`/“Echo” affix is evidence for natural stacking: it adds ricochet count and ricochet damage rather than introducing a separate arbitrary effect.

## Freewheel

`BP_WA_FreeShot_C` is a skill-trigger behavior and currently supports both projectile and raycast weapons.

Composition semantics:

**Freewheel duplicates the complete shot operation, not a naked base bullet.**

The duplicate receives a copy of the resolved attack context after weapon construction, including Buckshot/multihit shape, elements, compatible projectile conversion, traversal behavior and payload semantics. The Freewheel modifier instance that created the duplicate is marked consumed in that branch.

This gives the desired `Freewheel + Buckshot` behavior without a special-case synergy implementation.

## Buckshot

`BP_WA_AutoShotgun_C` already:

- modifies hit amount;
- creates damage modifiers through the weapon stat manager;
- supplies a deterministic set of spawn-rotation offsets;
- observes newly added skills.

It already applies to both raycast and projectile weapons.

Composition semantics should therefore treat Buckshot as a **shot-shape transformer**. Pellets are descendants of one trigger pull and inherit the resolved shot context. A duplicate shot generated by Freewheel receives the Buckshot-transformed operation.

## Fragmentation

Fragmentation is the strongest existing child-attack seam.

`BP_WA_Fragmentation_C` receives:

- the originating `ASkill`;
- an `RQHitResult`;
- the originating `AProjectile`.

It constructs arrays of native `NetworkSkillInfo` and calls `SpawnCustomProjectiles`.

That means Fragmentation is the first implementation target for generalized inheritance.

Fragment children should receive a resolved child context containing compatible:

- Seeker/Homing;
- element/status semantics;
- Bounce;
- Pierce;
- explosive payload;
- Ricochet;
- damage/critical metadata where the native skill representation supports it.

The Fragmentation modifier instance that created those fragments is consumed for that ancestry branch. A second distinct Fragmentation instance can still participate.

## Elements

Burn, Cryo and Shock have near-identical broad weapon compatibility and their Blueprints enumerate/register the weapon's skills. They are therefore already much closer to **skill semantics** than a simple weapon-color field.

However, vanilla affix rows mutually remove the other element rows, and other game structures expose singular `EElement` fields. The overhaul must not fake simultaneous elements by letting the last one overwrite the others.

### Multi-element policy

The implementation target is:

- preserve each elemental affix as an independent native status/damage contribution on eligible skills/child events;
- do not rely on writing multiple values into one singular `EElement` field;
- use native Burn/Cryo/Shock tags/status pathways so class and item callbacks still recognize them;
- if a visual component can display only one element, choose a deterministic visual representation without dropping the other gameplay semantics.

This remains a **runtime patch target** until the raw cooked Blueprint packages prove how the existing element delegates mutate skill state.

## Hitscan

The current `ProjectileRaycast` row is named Hitscan and is offered to ten projectile weapons. It already represents a compatibility transformation rather than a damage bonus.

For composition purposes, hit model is therefore a resolver concern, not a permanent weapon identity constraint.

The resolver may convert in either direction only when another requested effect requires it. Otherwise the native source hit model remains untouched.

## Alt-fire

`DT_WeaponMod` plus `DT_ModSkills` resolve all current weapon-mod secondary skills. The existing mod ecosystem includes projectile attacks, explosions, mines, missiles, shotgun volleys, scopes, barriers, boosters and summons.

Alt-fire inheritance must be profile-driven:

- projectile alt-fire: projectile/traversal/element payloads may inherit;
- explosive alt-fire: element/explosion modifiers may inherit;
- summon alt-fire: only semantics supported by the summoned actor/skill manager inherit;
- scope/booster/barrier: operate as state modifiers, not fake projectiles;
- melee/marking actions: receive only compatible damage/status semantics.

No “apply every affix to every alt-fire” rule is acceptable.

## Stacking policy

Duplicate transferable affixes are represented as separate **modifier instances** even when they share the same row ID.

That distinction is required for safe recursion.

Initial natural mappings:

- Bounce: add native bounce amount;
- Pierce: add native pierce budget/flag count where exposed;
- Ricochet/Echo: add ricochet count and use native ricochet damage parameters;
- Buckshot: increase native hit-count transformation within its existing parameter model;
- Freewheel: each instance receives its own deterministic proc opportunity;
- Seeker: scale native homing parameters only where the actual row/Blueprint exposes a meaningful parameter;
- Loaded/secondary-charge effects: stack native secondary charge/cooldown mechanisms.

A duplicate is never represented as two identical tooltip lines with undefined behavior.
