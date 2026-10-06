# Phase 1 prototype

The first installable prototype is intentionally limited to **data-only compatibility unlocks already supported by the decoded native Blueprint behavior**.

It changes only `DT_WeaponAffix`.

## Unlocked combinations

- Burn + Cryo
- Burn + Shock
- Cryo + Shock
- Burn + Cryo + Shock
- Bounce + Ricochet
- Pierce + Volatile/Explosive
- Bounce + Volatile/Explosive

The patch removes only the corresponding `RemovedPool` entries. It does not change damage numbers, proc chances, rarity, affix classes, weapon stats or effect implementations.

## Deliberately unchanged

- Fragmentation remains constrained until its cooked gameplay-tag gate is patched safely.
- Hitscan and Seeker remain mutually constrained until a real raycast-to-projectile resolver is implemented.
- Seeker + Buckshot/TripleShot restrictions remain unchanged for the first smoke test.
- Weapon grafting/editor UI is not part of this first binary prototype.

## Build

On Windows, after creating a clean retoc legacy extraction:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\windows\build-phase1-prototype.ps1 `
  -LegacyExtractRoot "C:\path\to\LegacyExtract" `
  -UAssetGUIPath "C:\path\to\UAssetGUI.exe" `
  -RetocPath "C:\path\to\retoc.exe"
```

The script:

1. exports the clean `DT_WeaponAffix.uasset` to UAssetAPI JSON;
2. applies `Source/patches/phase1_affix_unlocks.json`;
3. rebuilds the cooked package with UAssetGUI;
4. re-exports the rebuilt package as a structural sanity check;
5. packs `WeaponFoundry_P.pak/.ucas/.utoc` with retoc;
6. writes hashes and a build manifest.

Use `-Install -GamePaksDir "...\RoboQuest\Content\Paks"` only when you intentionally want the generated triplet copied into the game's `Paks\Mods` directory.

## Smoke-test matrix

Test a fresh run with no other mods installed first.

- acquire two different elemental affixes and verify both status behaviors remain active;
- test all three elements together if the loot/editor path permits acquiring them;
- test Bounce + Ricochet on a projectile weapon and a raycast weapon;
- test Pierce + Explosive on a projectile weapon and a raycast weapon;
- test Bounce + Explosive;
- save/quit/reload after obtaining a composed weapon;
- if available, repeat one combination as host and one as client.

Visual ambiguity is not automatically a gameplay failure: the weapon mesh may still choose one dominant element visual even if independent skill tags remain active. Record gameplay/status behavior separately from weapon VFX.

If the game fails at startup, remove only the three `WeaponFoundry_P.*` files from `Paks\Mods` and report the log/crash point. The script never edits the clean legacy extraction or vanilla game containers in place.

## Manual load verification

On 2026-10-06 the Windows build script completed through its final `7/7` step, installed the generated `WeaponFoundry_P.pak/.ucas/.utoc` triplet into Roboquest's `Paks\\Mods` directory, and Roboquest launched successfully with the prototype installed.

This verifies the current end-to-end path for a DataTable-only patch: legacy extraction -> UAssetAPI JSON patch -> cooked package rebuild -> retoc IoStore repack -> game load.
