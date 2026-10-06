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
    $OutputDir = Join-Path $RepoRoot "build\phase2"
}

function Resolve-Existing([string]$Path, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "$Label not found: $Path"
    }
    return [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $Path).Path)
}

function Find-Python {
    $candidates = @(
        @{ File = "python"; Prefix = @() },
        @{ File = "py"; Prefix = @("-3") }
    )
    foreach ($candidate in $candidates) {
        if (Get-Command $candidate.File -ErrorAction SilentlyContinue) {
            return $candidate
        }
    }
    throw "Python 3 was not found. Install Python 3 or make python/py available on PATH."
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
    $args = @(
        "tojson",
        ('"' + $Uasset + '"'),
        ('"' + $Json + '"'),
        "VER_UE4_26"
    )
    Invoke-UAssetGUI $args $Json $Label
}

function Build-UAssetFromJson([string]$Json, [string]$OutputBase, [string]$Label) {
    New-Item -ItemType Directory -Force -Path ([System.IO.Path]::GetDirectoryName($OutputBase)) | Out-Null
    $args = @(
        "fromjson",
        ('"' + $Json + '"'),
        ('"' + $OutputBase + '.uasset' + '"')
    )
    Invoke-UAssetGUI $args ($OutputBase + ".uasset") $Label
}

$LegacyExtractRoot = Resolve-Existing $LegacyExtractRoot "Legacy extraction"
$UAssetGUIPath = Resolve-Existing $UAssetGUIPath "UAssetGUI"
$RetocPath = Resolve-Existing $RetocPath "retoc"
$RepoRoot = Resolve-Existing $RepoRoot "Repository"

$contentCandidates = @(
    (Join-Path $LegacyExtractRoot "RoboQuest\Content"),
    $LegacyExtractRoot
)
$contentRoot = $null
foreach ($candidate in $contentCandidates) {
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

$affixSource = Join-Path $contentRoot ($affixRelative + ".uasset")
$fragSource = Join-Path $contentRoot ($fragRelative + ".uasset")
$affixSourceUexp = Join-Path $contentRoot ($affixRelative + ".uexp")
$fragSourceUexp = Join-Path $contentRoot ($fragRelative + ".uexp")

foreach ($source in @($affixSource, $fragSource)) {
    if (-not (Test-Path -LiteralPath $source)) {
        throw "Required legacy source package not found: $source"
    }
}

$affixOriginalJson = Join-Path $jsonRoot "DT_WeaponAffix.original.json"
$affixPhase1Json = Join-Path $jsonRoot "DT_WeaponAffix.phase1.json"
$affixPatchedJson = Join-Path $jsonRoot "DT_WeaponAffix.phase2.json"
$affixRoundtripJson = Join-Path $jsonRoot "DT_WeaponAffix.roundtrip.json"

$fragOriginalJson = Join-Path $jsonRoot "BP_WA_Fragmentation.original.json"
$fragCleanJson = Join-Path $jsonRoot "BP_WA_Fragmentation.clean-roundtrip.json"
$fragPatchedJson = Join-Path $jsonRoot "BP_WA_Fragmentation.phase2.json"
$fragRoundtripJson = Join-Path $jsonRoot "BP_WA_Fragmentation.roundtrip.json"

$phase1Spec = Join-Path $RepoRoot "Source\patches\phase1_affix_unlocks.json"
$phase2Spec = Join-Path $RepoRoot "Source\patches\phase2_fragmentation_eligibility.json"
$dataPatcher = Join-Path $RepoRoot "tools\patch_uassetapi_datatable.py"
$dataVerifier = Join-Path $RepoRoot "tools\verify_uassetapi_patch.py"
$fragPatcher = Join-Path $RepoRoot "tools\patch_fragmentation_bytecode.py"

Write-Host "1/9 Exporting clean Phase 2 source packages..."
Export-UAssetJson $affixSource $affixOriginalJson "UAssetGUI DT_WeaponAffix tojson"
Export-UAssetJson $fragSource $fragOriginalJson "UAssetGUI Fragmentation tojson"

Write-Host "2/9 Proving clean Fragmentation Blueprint JSON round-trip..."
$fragCleanBase = Join-Path $cleanRoot ("RoboQuest\Content\" + $fragRelative)
Build-UAssetFromJson $fragOriginalJson $fragCleanBase "UAssetGUI clean Fragmentation fromjson"
if ((Test-Path -LiteralPath $fragSourceUexp) -and -not (Test-Path -LiteralPath ($fragCleanBase + ".uexp"))) {
    throw "Clean Fragmentation source has .uexp but UAssetGUI did not recreate it."
}
Export-UAssetJson ($fragCleanBase + ".uasset") $fragCleanJson "UAssetGUI clean Fragmentation round-trip tojson"

Write-Host "3/9 Applying Phase 1 compatibility unlocks..."
Invoke-Python @(
    $dataPatcher,
    $affixOriginalJson,
    $phase1Spec,
    $affixPhase1Json,
    "--report",
    (Join-Path $reportRoot "phase1-affix-unlocks.json")
)

Write-Host "4/9 Expanding Fragmentation eligibility..."
Invoke-Python @(
    $dataPatcher,
    $affixPhase1Json,
    $phase2Spec,
    $affixPatchedJson,
    "--report",
    (Join-Path $reportRoot "phase2-fragmentation-eligibility.json")
)

Write-Host "5/9 Patching Fragmentation cooked Kismet with same-shape substitutions..."
Invoke-Python @(
    $fragPatcher,
    $fragOriginalJson,
    $fragPatchedJson,
    "--report",
    (Join-Path $reportRoot "phase2-fragmentation-bytecode.json")
)

Write-Host "6/9 Rebuilding patched cooked packages..."
$affixStageBase = Join-Path $stageRoot ("RoboQuest\Content\" + $affixRelative)
$fragStageBase = Join-Path $stageRoot ("RoboQuest\Content\" + $fragRelative)

Build-UAssetFromJson $affixPatchedJson $affixStageBase "UAssetGUI patched DT_WeaponAffix fromjson"
Build-UAssetFromJson $fragPatchedJson $fragStageBase "UAssetGUI patched Fragmentation fromjson"

if ((Test-Path -LiteralPath $affixSourceUexp) -and -not (Test-Path -LiteralPath ($affixStageBase + ".uexp"))) {
    throw "Patched DT_WeaponAffix .uexp was not created."
}
if ((Test-Path -LiteralPath $fragSourceUexp) -and -not (Test-Path -LiteralPath ($fragStageBase + ".uexp"))) {
    throw "Patched Fragmentation .uexp was not created."
}

Write-Host "7/9 Re-exporting and verifying both patched packages..."
Export-UAssetJson ($affixStageBase + ".uasset") $affixRoundtripJson "UAssetGUI patched DT_WeaponAffix round-trip"
Export-UAssetJson ($fragStageBase + ".uasset") $fragRoundtripJson "UAssetGUI patched Fragmentation round-trip"

Invoke-Python @($dataVerifier, $affixRoundtripJson, $phase1Spec)
Invoke-Python @($dataVerifier, $affixRoundtripJson, $phase2Spec)
Invoke-Python @($fragPatcher, $fragRoundtripJson, "--verify-only")

Write-Host "8/9 Packing Phase 2 UE4.26 IoStore containers..."
$utoc = Join-Path $releaseRoot "WeaponFoundry_P.utoc"
$retocArgs = @(
    "to-zen",
    "--version",
    "UE4_26",
    ('"' + $stageRoot + '"'),
    ('"' + $utoc + '"')
)
$proc = Start-Process -FilePath $RetocPath -ArgumentList $retocArgs -Wait -PassThru
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

Write-Host "9/9 Writing manifest and optionally installing..."
$manifest = [ordered]@{
    build = "phase2-universal-fragmentation"
    generated_utc = [DateTime]::UtcNow.ToString("o")
    source_content_root = $contentRoot
    phase1_compatibility_unlocks_included = $true
    same_shape_kismet_patch = $true
    modified_packages = @(
        "RoboQuest/Content/Data/DT_WeaponAffix",
        "RoboQuest/Content/Blueprint/Weapon/Affixes/Common/BP_WA_Fragmentation"
    )
    containers = @(
        [ordered]@{
            name = "WeaponFoundry_P.pak"
            sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $pak).Hash.ToLowerInvariant()
        },
        [ordered]@{
            name = "WeaponFoundry_P.ucas"
            sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $ucas).Hash.ToLowerInvariant()
        },
        [ordered]@{
            name = "WeaponFoundry_P.utoc"
            sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $utoc).Hash.ToLowerInvariant()
        }
    )
}
$manifestPath = Join-Path $releaseRoot "prototype-manifest.json"
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

if ($Install) {
    if (-not $GamePaksDir) {
        throw "-Install requires -GamePaksDir pointing to RoboQuest\RoboQuest\Content\Paks."
    }
    $GamePaksDir = Resolve-Existing $GamePaksDir "Game Paks directory"
    $mods = Join-Path $GamePaksDir "Mods"
    New-Item -ItemType Directory -Force -Path $mods | Out-Null
    foreach ($file in @($pak, $ucas, $utoc)) {
        Copy-Item -LiteralPath $file -Destination (Join-Path $mods ([System.IO.Path]::GetFileName($file))) -Force
    }
    Write-Host "Installed Phase 2 over the existing WeaponFoundry_P triplet in $mods"
}

Write-Host ""
Write-Host "Phase 2 prototype build complete:"
Write-Host "  $releaseRoot"
Write-Host ""
Write-Host "Phase 2 includes Phase 1 plus universal Fragmentation eligibility/gate removal and skill GameplayTag inheritance."
