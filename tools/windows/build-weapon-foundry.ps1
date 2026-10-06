[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [string]$LegacyExtractRoot,

    [Parameter(Mandatory=$true)]
    [string]$UAssetGUIPath,

    [Parameter(Mandatory=$true)]
    [string]$RetocPath,

    [string]$RepoRoot = "",
    [string]$OutputDir = "",
    [switch]$Install,
    [string]$GamePaksDir = ""
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $RepoRoot) {
    $RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $scriptRoot "..\.."))
}
if (-not $OutputDir) {
    $OutputDir = Join-Path $RepoRoot "build\weapon-foundry"
}

function Resolve-Existing([string]$Path, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "$Label not found: $Path"
    }
    return [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $Path).Path)
}

function Find-Python {
    foreach ($candidate in @(
        @{ File = "python"; Prefix = @() },
        @{ File = "py"; Prefix = @("-3") }
    )) {
        if (Get-Command $candidate.File -ErrorAction SilentlyContinue) {
            return $candidate
        }
    }
    throw "Python 3 was not found on PATH."
}

$python = Find-Python

function Invoke-Python([string[]]$Arguments) {
    $allArgs = @()
    $allArgs += $python.Prefix
    $allArgs += $Arguments
    & $python.File @allArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed with exit code $LASTEXITCODE."
    }
}

function Invoke-UAssetGUI(
    [string[]]$Arguments,
    [string]$ExpectedOutput,
    [string]$Label
) {
    $beforeClipboard = $null
    try { $beforeClipboard = Get-Clipboard -Raw -ErrorAction SilentlyContinue } catch {}

    $proc = Start-Process -FilePath $UAssetGUIPath -ArgumentList $Arguments -Wait -PassThru
    if ($proc.ExitCode -ne 0) {
        throw "$Label failed with process exit code $($proc.ExitCode)."
    }

    if ($ExpectedOutput -and -not (Test-Path -LiteralPath $ExpectedOutput)) {
        $afterClipboard = $null
        try { $afterClipboard = Get-Clipboard -Raw -ErrorAction SilentlyContinue } catch {}
        $detail = ""
        if ($afterClipboard -and $afterClipboard -ne $beforeClipboard) {
            $detail = [Environment]::NewLine + [Environment]::NewLine +
                "UAssetGUI exception copied to clipboard:" + [Environment]::NewLine +
                $afterClipboard
        }
        throw "$Label did not create expected output '$ExpectedOutput'.$detail"
    }
}

function Export-UAssetJson([string]$Uasset, [string]$Json, [string]$Label) {
    Invoke-UAssetGUI @(
        "tojson",
        ('"' + $Uasset + '"'),
        ('"' + $Json + '"'),
        "VER_UE4_26"
    ) $Json $Label
}

function Build-UAssetFromJson([string]$Json, [string]$OutputBase, [string]$Label) {
    New-Item -ItemType Directory -Force -Path ([System.IO.Path]::GetDirectoryName($OutputBase)) | Out-Null
    Invoke-UAssetGUI @(
        "fromjson",
        ('"' + $Json + '"'),
        ('"' + $OutputBase + '.uasset' + '"')
    ) ($OutputBase + ".uasset") $Label
}

$LegacyExtractRoot = Resolve-Existing $LegacyExtractRoot "Legacy extraction"
$UAssetGUIPath = Resolve-Existing $UAssetGUIPath "UAssetGUI"
$RetocPath = Resolve-Existing $RetocPath "retoc"
$RepoRoot = Resolve-Existing $RepoRoot "Repository"

$contentRoot = $null
foreach ($candidate in @(
    (Join-Path $LegacyExtractRoot "RoboQuest\Content"),
    $LegacyExtractRoot
)) {
    if (Test-Path -LiteralPath (Join-Path $candidate "Data\DT_WeaponAffix.uasset")) {
        $contentRoot = [System.IO.Path]::GetFullPath($candidate)
        break
    }
}
if (-not $contentRoot) {
    throw "Could not locate the Roboquest legacy Content root."
}

$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$workRoot = Join-Path $OutputDir "work"
$jsonRoot = Join-Path $workRoot "json"
$reportRoot = Join-Path $workRoot "reports"
$cleanRoot = Join-Path $workRoot "clean-roundtrip"
$stageRoot = Join-Path $OutputDir "staging"
$releaseRoot = Join-Path $OutputDir "release"

if (Test-Path -LiteralPath $OutputDir) {
    Remove-Item -Recurse -Force $OutputDir
}
New-Item -ItemType Directory -Force -Path $jsonRoot, $reportRoot, $cleanRoot, $releaseRoot | Out-Null

$affixRelative = "Data\DT_WeaponAffix"
$modRelative = "Data\DT_WeaponMod"
$fragRelative = "Blueprint\Weapon\Affixes\Common\BP_WA_Fragmentation"
$homingRelative = "Blueprint\Weapon\Affixes\Prefab\BP_WA_Homing"
$merchantRelative = "Blueprint\Interactive\Merchant\BP_Merchant_UpgradeAffix"
$interactiveRelative = "Blueprint\Interactive\Merchant\BP_Interactive_Merchant_AddEnchantedAffix"

$affixSource = Join-Path $contentRoot ($affixRelative + ".uasset")
$modSource = Join-Path $contentRoot ($modRelative + ".uasset")
$fragSource = Join-Path $contentRoot ($fragRelative + ".uasset")
$homingSource = Join-Path $contentRoot ($homingRelative + ".uasset")
$merchantSource = Join-Path $contentRoot ($merchantRelative + ".uasset")
$interactiveSource = Join-Path $contentRoot ($interactiveRelative + ".uasset")

foreach ($source in @(
    $affixSource,
    $modSource,
    $fragSource,
    $homingSource,
    $merchantSource,
    $interactiveSource
)) {
    if (-not (Test-Path -LiteralPath $source)) {
        throw "Required legacy source package not found: $source"
    }
}

$coreSpec = Join-Path $RepoRoot "Source\patches\weapon_foundry_core.json"
$modSpec = Join-Path $RepoRoot "Source\patches\weapon_foundry_mods.json"
$merchantSpec = Join-Path $RepoRoot "Source\patches\foundry_merchant.json"
$progressionPolicyPath = Join-Path $RepoRoot "Source\grafting\progression_policy.json"
$progressionPolicy = Get-Content -LiteralPath $progressionPolicyPath -Raw | ConvertFrom-Json
$baseFoundryAffixes = [int]$progressionPolicy.power_cell_economy.free_complexity_affixes
$maxFoundryAffixes = [int]$progressionPolicy.quality_color_caps.'4'

$dataPatcher = Join-Path $RepoRoot "tools\patch_uassetapi_datatable.py"
$dataVerifier = Join-Path $RepoRoot "tools\verify_uassetapi_patch.py"
$fragPatcher = Join-Path $RepoRoot "tools\patch_fragmentation_bytecode.py"
$homingPatcher = Join-Path $RepoRoot "tools\patch_homing_resolver.py"
$foundryGuard = Join-Path $RepoRoot "tools\patch_foundry_interactive.py"
$cdoPatcher = Join-Path $RepoRoot "tools\patch_uassetapi_cdo.py"
$kismetLayout = Join-Path $RepoRoot "tools\kismet_layout.py"

$affixOriginalJson = Join-Path $jsonRoot "DT_WeaponAffix.original.json"
$affixPatchedJson = Join-Path $jsonRoot "DT_WeaponAffix.weapon-foundry.json"
$affixRoundtripJson = Join-Path $jsonRoot "DT_WeaponAffix.roundtrip.json"

$modOriginalJson = Join-Path $jsonRoot "DT_WeaponMod.original.json"
$modPatchedJson = Join-Path $jsonRoot "DT_WeaponMod.weapon-foundry.json"
$modRoundtripJson = Join-Path $jsonRoot "DT_WeaponMod.roundtrip.json"

$fragOriginalJson = Join-Path $jsonRoot "BP_WA_Fragmentation.original.json"
$fragCleanJson = Join-Path $jsonRoot "BP_WA_Fragmentation.clean-roundtrip.json"
$fragPatchedJson = Join-Path $jsonRoot "BP_WA_Fragmentation.weapon-foundry.json"
$fragRoundtripJson = Join-Path $jsonRoot "BP_WA_Fragmentation.roundtrip.json"

$homingOriginalJson = Join-Path $jsonRoot "BP_WA_Homing.original.json"
$homingCleanJson = Join-Path $jsonRoot "BP_WA_Homing.clean-roundtrip.json"
$homingPatchedJson = Join-Path $jsonRoot "BP_WA_Homing.weapon-foundry.json"
$homingRoundtripJson = Join-Path $jsonRoot "BP_WA_Homing.roundtrip.json"

$merchantOriginalJson = Join-Path $jsonRoot "BP_Merchant_UpgradeAffix.original.json"
$merchantCleanJson = Join-Path $jsonRoot "BP_Merchant_UpgradeAffix.clean-roundtrip.json"
$merchantPatchedJson = Join-Path $jsonRoot "BP_Merchant_UpgradeAffix.weapon-foundry.json"
$merchantRoundtripJson = Join-Path $jsonRoot "BP_Merchant_UpgradeAffix.roundtrip.json"

$interactiveOriginalJson = Join-Path $jsonRoot "BP_Interactive_Merchant_AddEnchantedAffix.original.json"
$interactiveCleanJson = Join-Path $jsonRoot "BP_Interactive_Merchant_AddEnchantedAffix.clean-roundtrip.json"
$interactivePatchedJson = Join-Path $jsonRoot "BP_Interactive_Merchant_AddEnchantedAffix.weapon-foundry.json"
$interactiveRoundtripJson = Join-Path $jsonRoot "BP_Interactive_Merchant_AddEnchantedAffix.roundtrip.json"

Write-Host "1/14 Exporting production source packages..."
Export-UAssetJson $affixSource $affixOriginalJson "UAssetGUI DT_WeaponAffix tojson"
Export-UAssetJson $modSource $modOriginalJson "UAssetGUI DT_WeaponMod tojson"
Export-UAssetJson $fragSource $fragOriginalJson "UAssetGUI Fragmentation tojson"
Export-UAssetJson $homingSource $homingOriginalJson "UAssetGUI Homing tojson"
Export-UAssetJson $merchantSource $merchantOriginalJson "UAssetGUI Foundry merchant tojson"
Export-UAssetJson $interactiveSource $interactiveOriginalJson "UAssetGUI Foundry purchase interactive tojson"

Write-Host "2/14 Validating and proving clean Blueprint round-trips..."
foreach ($json in @(
    $fragOriginalJson,
    $homingOriginalJson,
    $merchantOriginalJson,
    $interactiveOriginalJson
)) {
    Invoke-Python @($kismetLayout, $json, "--validate")
}

$fragCleanBase = Join-Path $cleanRoot ("RoboQuest\Content\" + $fragRelative)
$homingCleanBase = Join-Path $cleanRoot ("RoboQuest\Content\" + $homingRelative)
$merchantCleanBase = Join-Path $cleanRoot ("RoboQuest\Content\" + $merchantRelative)
$interactiveCleanBase = Join-Path $cleanRoot ("RoboQuest\Content\" + $interactiveRelative)

Build-UAssetFromJson $fragOriginalJson $fragCleanBase "UAssetGUI clean Fragmentation fromjson"
Build-UAssetFromJson $homingOriginalJson $homingCleanBase "UAssetGUI clean Homing fromjson"
Build-UAssetFromJson $merchantOriginalJson $merchantCleanBase "UAssetGUI clean Foundry merchant fromjson"
Build-UAssetFromJson $interactiveOriginalJson $interactiveCleanBase "UAssetGUI clean Foundry interactive fromjson"

Export-UAssetJson ($fragCleanBase + ".uasset") $fragCleanJson "UAssetGUI clean Fragmentation round-trip"
Export-UAssetJson ($homingCleanBase + ".uasset") $homingCleanJson "UAssetGUI clean Homing round-trip"
Export-UAssetJson ($merchantCleanBase + ".uasset") $merchantCleanJson "UAssetGUI clean Foundry merchant round-trip"
Export-UAssetJson ($interactiveCleanBase + ".uasset") $interactiveCleanJson "UAssetGUI clean Foundry interactive round-trip"

Write-Host "3/14 Applying production affix compatibility / eligibility policy..."
Invoke-Python @(
    $dataPatcher,
    $affixOriginalJson,
    $coreSpec,
    $affixPatchedJson,
    "--report",
    (Join-Path $reportRoot "weapon-foundry-core.json")
)

Write-Host "4/14 Broadening resolved native alt-fire eligibility..."
Invoke-Python @(
    $dataPatcher,
    $modOriginalJson,
    $modSpec,
    $modPatchedJson,
    "--report",
    (Join-Path $reportRoot "weapon-foundry-mods.json")
)

Write-Host "5/14 Applying Fragmentation inheritance patch..."
Invoke-Python @(
    $fragPatcher,
    $fragOriginalJson,
    $fragPatchedJson,
    "--report",
    (Join-Path $reportRoot "fragmentation-bytecode.json")
)

Write-Host "6/14 Seeker safety rollback: BP_WA_Homing is not included in mod containers."\n\nWrite-Host "7/14 Seeding the native merchant with Foundry affix candidates..."
Invoke-Python @(
    $cdoPatcher,
    $merchantOriginalJson,
    $merchantSpec,
    $merchantPatchedJson,
    "--report",
    (Join-Path $reportRoot "foundry-merchant.json")
)

Write-Host "8/14 Applying six-affix Foundry purchase guard..."
Invoke-Python @(
    $foundryGuard,
    $interactiveOriginalJson,
    $interactivePatchedJson,
    "--max-affixes",
    "$maxFoundryAffixes",
    "--base-affixes",
    "$baseFoundryAffixes",
    "--report",
    (Join-Path $reportRoot "foundry-affix-cap.json")
)

Write-Host "9/14 Rebuilding production cooked packages..."
$affixStageBase = Join-Path $stageRoot ("RoboQuest\Content\" + $affixRelative)
$modStageBase = Join-Path $stageRoot ("RoboQuest\Content\" + $modRelative)
$fragStageBase = Join-Path $stageRoot ("RoboQuest\Content\" + $fragRelative)
$homingStageBase = Join-Path $stageRoot ("RoboQuest\Content\" + $homingRelative)
$merchantStageBase = Join-Path $stageRoot ("RoboQuest\Content\" + $merchantRelative)
$interactiveStageBase = Join-Path $stageRoot ("RoboQuest\Content\" + $interactiveRelative)

Build-UAssetFromJson $affixPatchedJson $affixStageBase "UAssetGUI production DT_WeaponAffix fromjson"
Build-UAssetFromJson $modPatchedJson $modStageBase "UAssetGUI production DT_WeaponMod fromjson"
Build-UAssetFromJson $fragPatchedJson $fragStageBase "UAssetGUI production Fragmentation fromjson"
Build-UAssetFromJson $homingPatchedJson $homingStageBase "UAssetGUI production Homing fromjson"
Build-UAssetFromJson $merchantPatchedJson $merchantStageBase "UAssetGUI production Foundry merchant fromjson"
Build-UAssetFromJson $interactivePatchedJson $interactiveStageBase "UAssetGUI production Foundry interactive fromjson"

Write-Host "10/14 Re-exporting and verifying all production packages..."
Export-UAssetJson ($affixStageBase + ".uasset") $affixRoundtripJson "UAssetGUI production DT_WeaponAffix round-trip"
Export-UAssetJson ($modStageBase + ".uasset") $modRoundtripJson "UAssetGUI production DT_WeaponMod round-trip"
Export-UAssetJson ($fragStageBase + ".uasset") $fragRoundtripJson "UAssetGUI production Fragmentation round-trip"
Export-UAssetJson ($homingStageBase + ".uasset") $homingRoundtripJson "UAssetGUI production Homing round-trip"
Export-UAssetJson ($merchantStageBase + ".uasset") $merchantRoundtripJson "UAssetGUI production Foundry merchant round-trip"
Export-UAssetJson ($interactiveStageBase + ".uasset") $interactiveRoundtripJson "UAssetGUI production Foundry interactive round-trip"

Invoke-Python @($dataVerifier, $affixRoundtripJson, $coreSpec)
Invoke-Python @($dataVerifier, $modRoundtripJson, $modSpec)
Invoke-Python @($fragPatcher, $fragRoundtripJson, "--verify-only")
Invoke-Python @($homingPatcher, $homingRoundtripJson, "--verify-only")
Invoke-Python @($cdoPatcher, $merchantRoundtripJson, $merchantSpec, "--verify-only")
Invoke-Python @(
    $foundryGuard,
    $interactiveRoundtripJson,
    "--max-affixes",
    "$maxFoundryAffixes",
    "--base-affixes",
    "$baseFoundryAffixes",
    "--verify-only"
)

foreach ($json in @(
    $fragRoundtripJson,
    $homingRoundtripJson,
    $merchantRoundtripJson,
    $interactiveRoundtripJson
)) {
    Invoke-Python @($kismetLayout, $json, "--validate")
}

Write-Host "11/14 Packing WeaponFoundry_P UE4.26 IoStore containers..."
$utoc = Join-Path $releaseRoot "WeaponFoundry_P.utoc"
$proc = Start-Process -FilePath $RetocPath -ArgumentList @(
    "to-zen",
    "--version",
    "UE4_26",
    ('"' + $stageRoot + '"'),
    ('"' + $utoc + '"')
) -Wait -PassThru
if ($proc.ExitCode -ne 0) {
    throw "retoc to-zen failed with exit code $($proc.ExitCode)."
}

$pak = Join-Path $releaseRoot "WeaponFoundry_P.pak"
$ucas = Join-Path $releaseRoot "WeaponFoundry_P.ucas"
foreach ($required in @($pak, $ucas, $utoc)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Expected output container missing: $required"
    }
}

Write-Host "12/14 Writing production manifest..."
$manifest = [ordered]@{
    build = "weapon-foundry-release-candidate"
    generated_utc = [DateTime]::UtcNow.ToString("o")
    source_content_root = $contentRoot
    diagnostic_weapon_edits = $false
    max_foundry_affixes = $maxFoundryAffixes
    foundry_free_complexity_affixes = $baseFoundryAffixes
    modified_packages = @(
        "RoboQuest/Content/Data/DT_WeaponAffix",
        "RoboQuest/Content/Data/DT_WeaponMod",
        "RoboQuest/Content/Blueprint/Weapon/Affixes/Common/BP_WA_Fragmentation",
        "RoboQuest/Content/Blueprint/Weapon/Affixes/Prefab/BP_WA_Homing",
        "RoboQuest/Content/Blueprint/Interactive/Merchant/BP_Merchant_UpgradeAffix",
        "RoboQuest/Content/Blueprint/Interactive/Merchant/BP_Interactive_Merchant_AddEnchantedAffix"
    )
    policy = [ordered]@{
        affix_patch_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $coreSpec).Hash.ToLowerInvariant()
        transfer_policy = "Source/grafting/transfer_policy.json"
        foundry_merchant = "Source/patches/foundry_merchant.json"
        weapon_mod_patch = "Source/patches/weapon_foundry_mods.json"
        raycast_seeker_resolver = "tools/patch_homing_resolver.py"
        foundry_purchase_guard = "tools/patch_foundry_interactive.py"
        progression_policy = "Source/grafting/progression_policy.json"
        progression = [ordered]@{
            quality_color_caps = $progressionPolicy.quality_color_caps
            free_complexity_affixes = $baseFoundryAffixes
            max_foundry_affixes = $maxFoundryAffixes
            merchant_cost_formula = $progressionPolicy.power_cell_economy.merchant_formula
            graft_complexity_formula = $progressionPolicy.power_cell_economy.graft_complexity_formula
            native_alt_fire_slots = [int]$progressionPolicy.native_alt_fire_slots
        }
    }
    containers = @(
        [ordered]@{ name = "WeaponFoundry_P.pak"; sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $pak).Hash.ToLowerInvariant() },
        [ordered]@{ name = "WeaponFoundry_P.ucas"; sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $ucas).Hash.ToLowerInvariant() },
        [ordered]@{ name = "WeaponFoundry_P.utoc"; sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $utoc).Hash.ToLowerInvariant() }
    )
}
$manifestPath = Join-Path $releaseRoot "weapon-foundry-manifest.json"
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

Write-Host "13/14 Optionally installing release candidate..."
if ($Install) {
    if (-not $GamePaksDir) {
        throw "-Install requires -GamePaksDir."
    }
    $GamePaksDir = Resolve-Existing $GamePaksDir "Game Paks directory"
    $mods = Join-Path $GamePaksDir "Mods"
    New-Item -ItemType Directory -Force -Path $mods | Out-Null
    foreach ($file in @($pak, $ucas, $utoc)) {
        Copy-Item -LiteralPath $file -Destination (Join-Path $mods ([System.IO.Path]::GetFileName($file))) -Force
    }
    Write-Host "Installed Weapon Foundry release candidate to $mods"
}

Write-Host "14/14 Weapon Foundry release-candidate build complete."
Write-Host ""
Write-Host "Release candidate:"
Write-Host "  $releaseRoot"
Write-Host ""
Write-Host "Includes:"
Write-Host "  - broad affix composition"
Write-Host "  - 15 widened native alt-fires"
Write-Host "  - Fragmentation child GameplayTag inheritance"
Write-Host "  - live Raycast -> Projectile Seeker resolver"
Write-Host "  - native Foundry merchant surface"
Write-Host "  - six-affix purchase guard"
Write-Host "  - no Phase 3 diagnostic HandGun/skill overrides"
