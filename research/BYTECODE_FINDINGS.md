# Cooked Blueprint bytecode findings

Status: verified against the targeted **UE4.26 legacy-converted** packages supplied from the installed Roboquest build.

The handoff contains 39/39 requested packages, zero missing files, and valid UAssetAPI JSON for every target. Across those targets UAssetAPI parsed **788 FunctionExport objects with decoded ScriptBytecode**, with no non-empty `ScriptBytecodeRaw` fallbacks. That means the implementation can reason from actual cooked Kismet rather than only class/property metadata.

## Fragmentation is a native network child-projectile path

`BP_WA_Fragmentation` binds every weapon skill's trigger-result delegate on apply and removes those bindings on removal.

Its custom event receives:

- the originating `ASkill`;
- an `RQHitResult`;
- the originating `AProjectile` when one exists.

The proc path constructs `NetworkSkillInfo[]` through `GetFragNetworkInfo` and calls the originating skill's native `SpawnCustomProjectiles` method.

After spawn, the vanilla graph modifies each child projectile using the configured Fragmentation values, including damage/impact-force ratio, explosion radius ratio, generic explosion VFX and inherited gameplay tags.

This is the preferred first seam for generalized child-attack inheritance because it already uses Roboquest's native projectile/network representation.

### Existing recursion guard

When the source projectile is valid, vanilla checks:

`Projectile.CustomTag != "Fragmentation"`

before executing the Fragmentation proc.

So Roboquest already has a same-family recursion guard for generated fragments. Weapon Foundry should preserve that behavior while extending provenance to distinguish multiple modifier instances.

### Existing gameplay-tag gate

Fragmentation also obtains the active gameplay-tag bitmask from the source projectile when present, otherwise from the source skill, and passes it through `CheckFlagToBitmask` using enum byte value `0`.

The same enum value is used by `BP_WA_Explosive` and `BP_WA_ExplosiveBlank` to reject a skill that already has the corresponding gameplay tag, while those affixes initialize/remove the native explosive tag.

**Inference:** gameplay-tag enum value 0 is the explosive/explosion semantic. The enum name itself is not serialized as text in the relevant bytecode, so this should remain labeled as an inference until the enum definition is recovered.

Implementation consequence: shipped Fragmentation is not a completely generic “any impact may fragment” behavior. Its tag gate must be understood/relaxed before Fragments can safely be made universal.

## Bounce is a native skill state

`BP_WA_Bounce` gets the weapon's primary skill and calls:

`InitBounceState(FTrunc(BounceAmount), Bounciness, Friction)`

On removal it calls:

`RemoveBounceState()`

There is no parallel mod projectile implementation. Bounce is therefore a high-confidence native composition primitive.

## Pierce is a native skill state

`BP_WA_Pierce` gets the primary skill and calls:

`InitPierceState(0)`

On removal it calls:

`RemovePierceState()`

Like Bounce, Pierce is a native skill mutation and is suitable for pool-unlock experiments before deeper Blueprint surgery.

## Ricochet uses native skill fields

`BP_WA_Ricochet` derives from the trigger-luck affix base. On a qualifying skill trigger it sets the skill's native:

- `RicochetAmount`;
- `RicochetDamageRatio`.

At the end of the trigger it removes the amount it added.

`BP_WA_AddRicochet` (“Echo”) independently increments/decrements the same native ricochet state and adjusts its damage ratio.

This is direct evidence that Ricochet stacking should be expressed through native skill state rather than a new damage system.

## Freewheel reuses the complete native skill

`BP_WA_FreeShot` does not create a stripped duplicate bullet.

On a successful proc it waits for the configured delay, validates that the weapon is current/local and the character is not already performing an action, gets the primary `APlayerSkill`, then:

1. sets `bNoCostForNextShot = true`;
2. calls the native `UseSkill()`.

This strongly validates the desired **Freewheel + Buckshot** model: the duplicate is the complete already-configured weapon skill and therefore naturally sees the weapon's current skill mutations.

The composition engine should preserve this seam instead of replacing it with custom projectile spawning.

## Buckshot is a native shot-shape/stat transformation

`BP_WA_AutoShotgun`:

- observes the active skill and newly registered skills;
- derives deterministic spawn-rotation offsets;
- creates native stat modifiers;
- modifies hit count and damage according to the existing custom parameters.

It is currently used on both projectile and raycast weapons.

Treat Buckshot as a shot-shape transformation of the native skill. Freewheel's native `UseSkill()` duplication should therefore duplicate the transformed shot.

## Explosive affixes use native explosive-tag semantics

`BP_WA_ExplosiveBlank` applies an explosive state to the weapon skill through the native explosive-tag functions and removes it through the corresponding native removal path.

Its compatibility condition checks the skill's gameplay-tag list and rejects a skill already carrying enum value 0.

`BP_WA_Explosive` uses the same gameplay-tag condition for its trigger-based variant.

This is why the current Fragmentation enum-0 check is strongly associated with explosive semantics.

## Burn, Cryo and Shock are independent native tags

The elemental affixes independently iterate/register weapon skills and call the native element-tag functions:

- Burn: `InitBurnTag` / `RemoveBurnTag`;
- Cryo: `InitIceTag` / `RemoveIceTag`;
- Shock: `InitShockTag` / `RemoveShockTag`.

They subscribe to newly registered skills so an added secondary skill can inherit the element semantics.

Their gameplay-tag tests use distinct enum values:

- Burn: 2;
- Shock: 3;
- Cryo/Ice: 4.

Each affix also calls the weapon's element-specific `SetWeaponElement` / `RemoveWeaponElement` path.

### Multi-element conclusion

Vanilla DataTable rows mutually exclude Burn, Cryo and Shock, but the cooked behavior exposes independent element tags and element-specific add/remove calls.

Removing the **element-vs-element RemovedPool restrictions** is therefore a high-confidence Phase 1 data-only experiment.

This does not yet prove that every visual component renders several simultaneous elements perfectly. Gameplay semantics and visual representation should be validated separately in-game.

## Seeker / Homing still needs a hit-model resolver

`BP_WA_Homing`:

- gets the primary player skill;
- excludes scope/summon skill classes;
- has `AffectedHitTypes = { Projectile, Raycast }`;
- sets `bHomingProjectile = true`;
- writes native homing acceleration/range/dot-tolerance parameters;
- restores `HitType = BaseHitType` on removal.

Critically, the cooked graph does **not** visibly convert a raycast skill to a projectile skill, and it does not use the row's `ProjectileSpeed` / `ProjectileCollisionSize` values in this Blueprint.

Therefore the first prototype must keep **Hitscan vs Seeker** constrained and must not claim raycast homing works just because `AffectedHitTypes` contains Raycast.

A real raycast-to-projectile resolver remains a runtime/bytecode milestone.

## Hitscan is already a hit-model transformation

`BP_WA_ProjectileRaycast` (“Hitscan”) modifies the primary skill toward raycast behavior and restores the original skill state on removal.

Its existence supports the broader architecture in which hit model is a resolvable skill property rather than immutable chassis identity, but Seeker/Hitscan coexistence should stay blocked until the conversion semantics are implemented and tested.

## Native replicated affix transaction

Cooked `BP_APlayer` confirms the full call chain.

Local `AddEnchantedAffix(RowName)` calls the current weapon's native `AddEnchantedAffix(RowName)`, then:

- on the server, calls `OnMulticastAddEnchantedAffix(RowName, Weapon)`;
- on a client, calls reliable server RPC `OnServerAddEnchantedAffix(RowName, Weapon)`;
- the server RPC invokes the reliable multicast;
- non-local multicast recipients call `Weapon.AddEnchantedAffix(RowName)`.

The same server -> multicast pattern exists for affix reroll and weapon-quality upgrade.

This is a verified replicated transaction seam for a future graft/editor action.

### Important limitation

The existing perfume merchant compares against `GetCurrentEnchantedAffixRowName()`, singular, and its pool is built from rows with both:

- `bEnchantedAffix == true`;
- `bActivate == true`.

So the native enchanted-affix path is proof of replicated mutation, **not yet proof of arbitrary multi-affix stacking**. Grafting should reuse its authority/network pattern without assuming the perfume slot is the final storage model.

## Native save seam

`BP_SaveGame_Profile` stores a native `PlayerRunSaveGame` with a `Weapons` array whose element struct type is `WeaponRunSaveGame`.

The default array is empty, so this handoff does not expose the inner fields of `WeaponRunSaveGame`.

The implementation should keep composed state on native weapon structures wherever possible so the existing run-save generator can serialize it. Exact persistence of additional regular affixes remains an in-game validation item.

## Safe implementation order

1. Data-only unlocks where cooked bytecode already supports both mechanics.
2. Round-trip patched DataTable through UAssetGUI and validate the produced package.
3. Game smoke-test multi-element and traversal combinations.
4. Only then patch Kismet for behaviors that are genuinely gated, beginning with Fragmentation.
5. Retarget Kismet jump offsets whenever a bytecode edit changes serialized instruction size; do not perform blind JSON surgery on functions containing absolute offsets.
