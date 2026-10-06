# Phase 2 — universal Fragmentation prototype

Phase 2 is the first cooked-Blueprint behavior patch.

It includes every Phase 1 compatibility unlock and adds a narrowly targeted modification of `BP_WA_Fragmentation`.

## Goal

Make **Fragments** a broadly available composition primitive without replacing Roboquest's native projectile/network machinery.

## DataTable change

`Fragmentation.Weapons` is replaced with the broad vanilla `Burn.Weapons` pool.

This deliberately uses an existing Roboquest compatibility pool instead of blindly putting Fragments on special/nonstandard weapon rows.

## Kismet changes

All modifications are **same-shape substitutions**. No instruction is inserted or removed, no parameter count changes, and no absolute Kismet flow offset is edited.

### 1. Remove the gameplay-tag gate

Vanilla assigns:

`CheckFlagToBitmask(tag_0, GameplayTags)`

to `CallFunc_CheckFlagToBitmask_ReturnValue`, then branches on that local.

Phase 2 preserves the exact `EX_CallMath(two EX_LocalVariable params)` shape but changes it to:

`LessEqual_IntInt(GameplayTags, GameplayTags)`

which is deterministically true for the same integer value.

This avoids shortening the expression and therefore avoids rebasing every downstream execution-flow offset.

### 2. Make child-tag copying work for raycast-origin attacks

Vanilla checks `IsValid(sourceProjectile)` before copying tags into the spawned fragment. A raycast attack has no source projectile.

Phase 2 changes only the local-variable reference so that the same `IsValid(...)` call checks the **spawned fragment** instead.

### 3. Inherit gameplay tags from the originating skill

Vanilla copies:

`sourceProjectile.GameplayTags -> childProjectile.GameplayTags`

Phase 2 keeps the same Context/property-access expression shape but retargets the source to:

`sourceSkill.GameplayTags -> childProjectile.GameplayTags`

The same class already contains a `GetGameplayTags` function proving that `ASkill.GameplayTags` is the intended fallback when a source projectile does not exist.

## What remains vanilla

- child projectiles are still created with `ASkill.SpawnCustomProjectiles`;
- `NetworkSkillInfo` is still used;
- the child `CustomTag` remains `Fragmentation`;
- the existing `CustomTag != Fragmentation` recursion guard remains intact;
- native Fragmentation damage/radius ratios remain intact;
- native `RandomStream`/Luck behavior remains intact.

## Why this is a useful next milestone

If this Blueprint patch loads successfully, the project has proven that the pipeline can safely:

1. modify DataTables;
2. modify decoded cooked Kismet;
3. rebuild Blueprint `.uasset/.uexp`;
4. repack the result to IoStore;
5. load it in Roboquest.

That opens the path to the generalized provenance/inheritance work without introducing UE4SS solely because Blueprint mutation was inaccessible.

## Build

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\windows\build-phase2-prototype.ps1 `
  -LegacyExtractRoot "C:\path\to\LegacyExtract" `
  -UAssetGUIPath "C:\path\to\UAssetGUI.exe" `
  -RetocPath "C:\path\to\retoc.exe" `
  -Install `
  -GamePaksDir "C:\path\to\RoboQuest\RoboQuest\Content\Paks"
```

The installed triplet intentionally retains the same `WeaponFoundry_P` name, replacing the Phase 1 prototype rather than loading two overlapping copies of `DT_WeaponAffix`.

## First test

The first test is simply that Roboquest boots with the cooked Blueprint override.

After that, test Fragments on one of the weapons that already supports Seeker. That gives us an early signal on whether `SpawnCustomProjectiles` naturally inherits the source skill's native homing fields in addition to the GameplayTags that Phase 2 explicitly propagates.

## Manual load verification

On 2026-10-06 the Phase 2 builder completed through `9/9`, installed its replacement `WeaponFoundry_P.pak/.ucas/.utoc` triplet, and Roboquest launched successfully with both the `DT_WeaponAffix` override and patched cooked `BP_WA_Fragmentation` Blueprint loaded.

This verifies the current end-to-end pipeline for a same-shape cooked Kismet patch: legacy Blueprint -> UAssetAPI JSON -> decoded ScriptBytecode substitution -> cooked package rebuild -> retoc IoStore repack -> game load.
