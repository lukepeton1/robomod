# Building from source

## Required local inputs

Weapon Foundry intentionally does not redistribute extracted Roboquest assets.

You need:

1. A current Roboquest installation.
2. `retoc`.
3. UAssetGUI v1.1.0.
4. Python 3.
5. A UE4.26 legacy extraction generated with retoc.

Verified research workflow:

```text
retoc to-legacy --version UE4_26 <Roboquest Paks> <LegacyExtract>
```

UAssetGUI v1.1.0 is invoked with `VER_UE4_26`.

## Production build

From the repository:

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

The current developer folder layout also supports:

```cmd
tools\windows\run-weapon-foundry.cmd
```

## What the build does

The production core:

1. exports clean `DT_WeaponAffix` and `BP_WA_Fragmentation`;
2. applies the generated compatibility/eligibility policy;
3. applies the verified same-shape Fragmentation Kismet substitutions;
4. reconstructs cooked UE4.26 assets;
5. re-exports them and verifies the intended edits survived round-trip;
6. packs `WeaponFoundry_P.pak/.ucas/.utoc` with retoc;
7. writes SHA-256 hashes to a manifest.

The production build contains no Phase 3 diagnostic HandGun edits.

## Release ZIP

After a successful production build:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\windows\package-release.ps1 -Version 0.1.0-dev
```

This creates a self-contained ZIP under `dist/` while excluding extracted vanilla assets.
