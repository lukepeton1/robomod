# Building from source

## Requirements

Weapon Foundry does not redistribute extracted Roboquest cooked assets.

Required locally:

1. current Roboquest installation;
2. `retoc`;
3. UAssetGUI v1.1.0;
4. Python 3;
5. UE4.26 legacy extraction from the installed game.

Verified extraction pattern:

```text
retoc to-legacy --version UE4_26 <Roboquest Paks> <LegacyExtract>
```

## Release-candidate build

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\windows\build-weapon-foundry.ps1 `
  -LegacyExtractRoot "C:\path\to\LegacyExtract" `
  -UAssetGUIPath "C:\path\to\UAssetGUI.exe" `
  -RetocPath "C:\path\to\retoc.exe"
```

Add:

```text
-Install -GamePaksDir "C:\path\to\RoboQuest\RoboQuest\Content\Paks"
```

to install after a successful build.

With the development folder layout used during reverse engineering:

```cmd
tools\windows\run-weapon-foundry.cmd
```

builds and installs the full release candidate.

## Build pipeline

The production builder now validates and reconstructs six cooked packages.

It:

1. exports `DT_WeaponAffix`, `DT_WeaponMod`, Fragmentation, Homing and the two Foundry merchant Blueprints;
2. validates clean Kismet layout for every modified Blueprint;
3. applies generated affix compatibility/eligibility policy;
4. applies generated native alt-fire eligibility policy;
5. applies Fragmentation child-inheritance Kismet edits;
6. inserts/rebases the Homing Raycast→Projectile resolver;
7. seeds the native merchant with transferable ordinary affixes;
8. inserts/rebases the six-affix purchase guard;
9. reconstructs all cooked packages;
10. re-exports and semantically verifies all edits;
11. validates final Kismet byte layout;
12. packs `WeaponFoundry_P.pak/.ucas/.utoc`;
13. records hashes and modified-package manifest;
14. optionally installs the release candidate.

The build contains no Phase 3 diagnostic HandGun/skill overrides.

## Release ZIP

After a successful build:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\windows\package-release.ps1 -Version 0.1.0-rc1
```

The ZIP contains:

- installable IoStore triplet;
- install/uninstall helpers;
- manifest and hashes;
- production source patch/generator tooling;
- documentation.

It excludes extracted vanilla game assets.
