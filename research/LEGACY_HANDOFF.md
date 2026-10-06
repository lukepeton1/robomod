# Legacy asset handoff

The repository's FModel-style JSON export is enough for architecture research but not enough to build safe cooked Blueprint/DataTable patches.

Weapon Foundry's patch/build tooling targets **legacy-converted** UE4.26 assets produced by `retoc to-legacy`, because those can be parsed and round-tripped with UAssetAPI/UAssetGUI and then converted back to Roboquest's IoStore format.

## Produce a clean legacy extraction

From the directory containing `retoc.exe`:

```powershell
.\retoc.exe to-legacy --version UE4_26 `
  "C:\path\to\RoboQuest\RoboQuest\Content\Paks" `
  "C:\path\to\RQ-Modding\Extract"
```

The output should contain `Extract/RoboQuest/Content/Data` and `Extract/RoboQuest/Content/Blueprint`. Do not edit this clean extraction.

## Collect only Weapon Foundry targets

Use `tools/windows/collect-legacy-handoff.ps1`. The target list is `Source/manifests/legacy_patch_targets.txt`.

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\windows\collect-legacy-handoff.ps1 `
  -ExtractRoot "C:\path\to\RQ-Modding\Extract" `
  -UAssetGUIPath "C:\path\to\UAssetGUI.exe"
```

The script validates the extraction, copies only requested `.uasset`, `.uexp`, and optional `.ubulk` files, exports each requested asset with UAssetGUI `tojson ... 4.26`, computes SHA-256 hashes, writes `handoff-manifest.json`, and creates a ZIP.

**Do not commit `handoff/` or the ZIP to this public repository.** Those files are local analysis/build inputs derived from the user's installed game.

## Why binary plus UAssetAPI JSON?

The UAssetAPI JSON lets the project inspect and patch DataTable fields and, where successfully parsed, cooked Kismet `ScriptBytecode`. The original legacy `.uasset/.uexp` pair is needed to validate binary round-trips and produce final staged assets.

UAssetAPI exposes Kismet bytecode on `FunctionExport`/`StructExport`. If bytecode parsing fails for a specific asset and falls back to raw bytecode, that is an implementation decision point rather than something the project should guess around.
