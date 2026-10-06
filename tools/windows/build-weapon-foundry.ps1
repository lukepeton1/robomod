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
$fragRelative = "Blueprint\Weapon\Affixes\Common\BP_WA_Fragmentation"
$merchantRelative = "Blueprint\Interactive\Merchant\BP_Merchant_UpgradeAffix"
$affixSource = Join-Path $contentRoot ($affixRelative + ".uasset")
$fragSource = Join-Path $contentRoot ($fragRelative + ".uasset")
$merchantSource = Join-Path $contentRoot ($merchantRelative + ".uasset")

foreach ($source in @($affixSource, $fragSource, $merchantSource)) {
    if (-not (Test-Path -LiteralPath $source)) {
        throw "Required legacy source package not found: $source"
    }
}

$coreSpec = Join-Path $RepoRoot "Source\patches\weapon_foundry_core.json"
$merchantSpec = Join-Path $RepoRoot "Source\patches\foundry_merchant.json"
$dataPatcher = Join-Path $RepoRoot "tools\patch_uassetapi_datatable.py"
$dataVerifier = Join-Path $RepoRoot "tools\verify_uassetapi_patch.py"
$fragPatcher = Join-Path $RepoRoot "tools\patch_fragmentation_bytecode.py"
$cdoPatcher = Join-Path $RepoRoot "tools\patch_uassetapi_cdo.py"

$affixOriginalJson = Join-Path $jsonRoot "DT_WeaponAffix.original.json"
$affixPatchedJson = Join-Path $jsonRoot "DT_WeaponAffix.weapon-foundry.json"
$affixRoundtripJson = Join-Path $jsonRoot "DT_WeaponAffix.roundtrip.json"
$fragOriginalJson = Join-Path $jsonRoot "BP_WA_Fragmentation.original.json"
$fragCleanJson = Join-Path $jsonRoot "BP_WA_Fragmentation.clean-roundtrip.json"
$fragPatchedJson = Join-Path $jsonRoot "BP_WA_Fragmentation.weapon-foundry.json"
$fragRoundtripJson = Join-Path $jsonRoot "BP_WA_Fragmentation.roundtrip.json"
$merchantOriginalJson = Join-Path $jsonRoot "BP_Merchant_UpgradeAffix.original.json"
$merchantCleanJson = Join-Path $jsonRoot "BP_Merchant_UpgradeAffix.clean-roundtrip.json"
$merchantPatchedJson = Join-Path $jsonRoot "BP_Merchant_UpgradeAffix.weapon-foundry.json"
$merchantRoundtripJson = Join-Path $jsonRoot "BP_Merchant_UpgradeAffix.roundtrip.json"

Write-Host "1/10 Exporting production source packages..."
Export-UAssetJson $affixSource $affixOriginalJson "UAssetGUI DT_WeaponAffix tojson"
Export-UAssetJson $fragSource $fragOriginalJson "UAssetGUI Fragmentation tojson"
Export-UAssetJson $merchantSource $merchantOriginalJson "UAssetGUI Foundry merchant tojson"

Write-Host "2/10 Proving clean Blueprint round-trips..."
$fragCleanBase = Join-Path $cleanRoot ("RoboQuest\Content\" + $fragRelative)
Build-UAssetFromJson $fragOriginalJson $fragCleanBase "UAssetGUI clean Fragmentation fromjson"
Export-UAssetJson ($fragCleanBase + ".uasset") $fragCleanJson "UAssetGUI clean Fragmentation round-trip"
$merchantCleanBase = Join-Path $cleanRoot ("RoboQuest\Content\" + $merchantRelative)
Build-UAssetFromJson $merchantOriginalJson $merchantCleanBase "UAssetGUI clean Foundry merchant fromjson"
Export-UAssetJson ($merchantCleanBase + ".uasset") $merchantCleanJson "UAssetGUI clean Foundry merchant round-trip"

Write-Host "3/10 Applying production Weapon Foundry compatibility/eligibility policy..."
Invoke-Python @(
    $dataPatcher,
    $affixOriginalJson,
    $coreSpec,
    $affixPatchedJson,
    "--report",
    (Join-Path $reportRoot "weapon-foundry-core.json")
)

Write-Host "4/10 Applying verified Fragmentation cooked-Kismet patch..."
Invoke-Python @(
    $fragPatcher,
    $fragOriginalJson,
    $fragPatchedJson,
    "--report",
    (Join-Path $reportRoot "fragmentation-bytecode.json")
)

Write-Host "5/10 Seeding the native affix merchant with Foundry graft candidates..."
Invoke-Python @(
    $cdoPatcher,
    $merchantOriginalJson,
    $merchantSpec,
    $merchantPatchedJson,
    "--report",
    (Join-Path $reportRoot "foundry-merchant.json")
)

Write-Host "6/10 Rebuilding production cooked packages..."
$affixStageBase = Join-Path $stageRoot ("RoboQuest\Content\" + $affixRelative)
$fragStageBase = Join-Path $stageRoot ("RoboQuest\Content\" + $fragRelative)
$merchantStageBase = Join-Path $stageRoot ("RoboQuest\Content\" + $merchantRelative)
Build-UAssetFromJson $affixPatchedJson $affixStageBase "UAssetGUI production DT_WeaponAffix fromjson"
Build-UAssetFromJson $fragPatchedJson $fragStageBase "UAssetGUI production Fragmentation fromjson"
Build-UAssetFromJson $merchantPatchedJson $merchantStageBase "UAssetGUI production Foundry merchant fromjson"

Write-Host "7/10 Re-exporting and verifying production packages..."
Export-UAssetJson ($affixStageBase + ".uasset") $affixRoundtripJson "UAssetGUI production DT_WeaponAffix round-trip"
Export-UAssetJson ($fragStageBase + ".uasset") $fragRoundtripJson "UAssetGUI production Fragmentation round-trip"
Export-UAssetJson ($merchantStageBase + ".uasset") $merchantRoundtripJson "UAssetGUI production Foundry merchant round-trip"
Invoke-Python @($dataVerifier, $affixRoundtripJson, $coreSpec)
Invoke-Python @($fragPatcher, $fragRoundtripJson, "--verify-only")
Invoke-Python @($cdoPatcher, $merchantRoundtripJson, $merchantSpec, "--verify-only")

Write-Host "8/10 Packing WeaponFoundry_P UE4.26 IoStore containers..."
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

Write-Host "9/10 Writing production manifest..."
$manifest = [ordered]@{
    build = "weapon-foundry-production"
    generated_utc = [DateTime]::UtcNow.ToString("o")
    source_content_root = $contentRoot
    diagnostic_weapon_edits = $false
    modified_packages = @(
        "RoboQuest/Content/Data/DT_WeaponAffix",
        "RoboQuest/Content/Blueprint/Weapon/Affixes/Common/BP_WA_Fragmentation",
        "RoboQuest/Content/Blueprint/Interactive/Merchant/BP_Merchant_UpgradeAffix"
    )
    policy = [ordered]@{
        affix_patch_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $coreSpec).Hash.ToLowerInvariant()
        transfer_policy = "Source/grafting/transfer_policy.json"
        foundry_merchant = "Source/patches/foundry_merchant.json"
    }
    containers = @(
        [ordered]@{ name = "WeaponFoundry_P.pak"; sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $pak).Hash.ToLowerInvariant() },
        [ordered]@{ name = "WeaponFoundry_P.ucas"; sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $ucas).Hash.ToLowerInvariant() },
        [ordered]@{ name = "WeaponFoundry_P.utoc"; sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $utoc).Hash.ToLowerInvariant() }
    )
}
$manifestPath = Join-Path $releaseRoot "weapon-foundry-manifest.json"
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

Write-Host "10/10 Optionally installing production build..."
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
    Write-Host "Installed production Weapon Foundry core to $mods"
}

Write-Host ""
Write-Host "Weapon Foundry production build complete:"
Write-Host "  $releaseRoot"
Write-Host ""
Write-Host "This build contains the native Foundry merchant surface and no Phase 3 diagnostic HandGun/skill overrides."
