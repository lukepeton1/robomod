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
    $OutputDir = Join-Path $RepoRoot "build\ground-graft-gate-probe"
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

$RepoRoot = Resolve-Existing $RepoRoot "Repository"
$LegacyExtractRoot = Resolve-Existing $LegacyExtractRoot "Legacy extraction"
$UAssetGUIPath = Resolve-Existing $UAssetGUIPath "UAssetGUI"
$RetocPath = Resolve-Existing $RetocPath "retoc"
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
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

Write-Host "1/8 Building the normal Weapon Foundry release-candidate baseline..."
& powershell -ExecutionPolicy Bypass -File (Join-Path $RepoRoot "tools\windows\build-weapon-foundry.ps1") `
    -LegacyExtractRoot $LegacyExtractRoot `
    -UAssetGUIPath $UAssetGUIPath `
    -RetocPath $RetocPath `
    -RepoRoot $RepoRoot `
    -OutputDir $OutputDir
if ($LASTEXITCODE -ne 0) {
    throw "Production baseline build failed with exit code $LASTEXITCODE."
}

$contentRoot = $null
foreach ($candidate in @(
    (Join-Path $LegacyExtractRoot "RoboQuest\Content"),
    $LegacyExtractRoot
)) {
    if (Test-Path -LiteralPath (Join-Path $candidate "Blueprint\Interactive\Reward\BP_Interactive_Weapon.uasset")) {
        $contentRoot = [System.IO.Path]::GetFullPath($candidate)
        break
    }
}
if (-not $contentRoot) {
    throw "Could not locate the Roboquest legacy Content root containing BP_Interactive_Weapon."
}

$relative = "Blueprint\Interactive\Reward\BP_Interactive_Weapon"
$source = Join-Path $contentRoot ($relative + ".uasset")
$probeStageRoot = Join-Path $OutputDir "probe-staging"
$releaseRoot = Join-Path $OutputDir "release"
$jsonRoot = Join-Path $OutputDir "work\ground-graft-gate-json"
$reportRoot = Join-Path $OutputDir "work\ground-graft-gate-reports"

if (Test-Path -LiteralPath $probeStageRoot) {
    Remove-Item -Recurse -Force $probeStageRoot
}
New-Item -ItemType Directory -Force -Path $probeStageRoot,$jsonRoot,$reportRoot | Out-Null

$originalJson = Join-Path $jsonRoot "BP_Interactive_Weapon.original.json"
$patchedJson = Join-Path $jsonRoot "BP_Interactive_Weapon.graft-gate.json"
$roundtripJson = Join-Path $jsonRoot "BP_Interactive_Weapon.roundtrip.json"
$stageBase = Join-Path $probeStageRoot ("RoboQuest\Content\" + $relative)
$patcher = Join-Path $RepoRoot "tools\patch_ground_graft_gate_probe.py"
$spec = Join-Path $RepoRoot "Source\probes\ground_graft_ping_probe.json"
$kismetLayout = Join-Path $RepoRoot "tools\kismet_layout.py"

Write-Host "2/8 Exporting BP_Interactive_Weapon..."
Export-UAssetJson $source $originalJson "UAssetGUI BP_Interactive_Weapon tojson"
Invoke-Python @($kismetLayout, $originalJson, "--validate")

Write-Host "3/8 Injecting read-only GRAFT eligibility diagnostic..."
Invoke-Python @(
    $patcher,
    $originalJson,
    $spec,
    $patchedJson,
    "--report",
    (Join-Path $reportRoot "ground-graft-gate-probe.json")
)

Write-Host "4/8 Rebuilding and round-trip verifying GRAFT gate..."
Build-UAssetFromJson $patchedJson $stageBase "UAssetGUI read-only GRAFT gate probe fromjson"
Export-UAssetJson ($stageBase + ".uasset") $roundtripJson "UAssetGUI read-only GRAFT gate probe round-trip"
Invoke-Python @($patcher, $roundtripJson, $spec, "--verify-only")
Invoke-Python @($kismetLayout, $roundtripJson, "--validate")

Write-Host "5/8 Packing read-only GRAFT gate overlay..."
$overlayNames = @(
    "WeaponFoundry_GraftGate_P.pak",
    "WeaponFoundry_GraftGate_P.ucas",
    "WeaponFoundry_GraftGate_P.utoc"
)
foreach ($name in $overlayNames) {
    $existing = Join-Path $releaseRoot $name
    if (Test-Path -LiteralPath $existing) {
        Remove-Item -Force $existing
    }
}

$overlayUtoc = Join-Path $releaseRoot "WeaponFoundry_GraftGate_P.utoc"
$retocLog = Join-Path $reportRoot "retoc-ground-graft-gate.log"
$retocArgs = @(
    "to-zen",
    "--version",
    "UE4_26",
    $probeStageRoot,
    $overlayUtoc
)
$retocOutput = & $RetocPath @retocArgs 2>&1
$retocExit = $LASTEXITCODE
$retocOutput | Tee-Object -FilePath $retocLog
if ($retocExit -ne 0) {
    throw "retoc read-only GRAFT gate overlay failed with exit code $retocExit. Full output: $retocLog"
}

$overlayPak = Join-Path $releaseRoot "WeaponFoundry_GraftGate_P.pak"
$overlayUcas = Join-Path $releaseRoot "WeaponFoundry_GraftGate_P.ucas"
foreach ($required in @($overlayPak,$overlayUcas,$overlayUtoc)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "read-only GRAFT gate overlay container missing: $required"
    }
}

$pak = Join-Path $releaseRoot "WeaponFoundry_P.pak"
$ucas = Join-Path $releaseRoot "WeaponFoundry_P.ucas"
$utoc = Join-Path $releaseRoot "WeaponFoundry_P.utoc"
foreach ($required in @($pak,$ucas,$utoc)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Production baseline container missing after GRAFT gate overlay build: $required"
    }
}

Write-Host "6/8 Writing diagnostic manifest..."
$probeSpec = Get-Content -LiteralPath $spec -Raw | ConvertFrom-Json
$candidateRows = @($probeSpec.selection.candidates | ForEach-Object { $_.row })
$manifest = [ordered]@{
    build = "weapon-foundry-ground-graft-gate-probe"
    diagnostic_probe = $true
    generated_utc = [DateTime]::UtcNow.ToString("o")
    production_release_candidate_included = $true
    purpose = "Display exact read-only GRAFT eligibility and duplicate status on native dropped-weapon interaction UI."
    modified_probe_package = "RoboQuest/Content/Blueprint/Interactive/Reward/BP_Interactive_Weapon"
    explicitly_not_modified = "RoboQuest/Content/Blueprint/Player/BP_APlayer"
    trigger = "press E on a dropped weapon; CanInteract=false and GetErrorText shows a native visible diagnostic"
    authoritative_donor_rows = "SpawnedWeapon.GetAffixRowNames()"
    mutation = "none: diagnostic is read-only"
    candidate_rows = $candidateRows
    expected_behavior = @(
        "normal E pickup is temporarily blocked",
        "WF READY: <row> means donor has a supported affix and target does not",
        "WF BLOCKED: target already has <row> means duplicate",
        "WF GATE: donor has no supported affix means no candidate row matched",
        "WF GATE: current target missing means target could not be read",
        "Power Cells and all weapon state remain unchanged"
    )
    restore = "tools\windows\run-weapon-foundry.cmd"
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $releaseRoot "ground-graft-gate-probe-manifest.json") -Encoding UTF8

Write-Host "7/8 Optionally installing baseline + GRAFT gate overlay..."
if ($Install) {
    if (-not $GamePaksDir) {
        throw "-Install requires -GamePaksDir."
    }
    $GamePaksDir = Resolve-Existing $GamePaksDir "Game Paks directory"
    $mods = Join-Path $GamePaksDir "Mods"
    New-Item -ItemType Directory -Force -Path $mods | Out-Null

    # Exactly one dropped-weapon diagnostic can win the cooked override.
    foreach ($legacy in @(
        "WeaponFoundry_GraftProbe_P.pak",
        "WeaponFoundry_GraftProbe_P.ucas",
        "WeaponFoundry_GraftProbe_P.utoc",
        "WeaponFoundry_GraftSafeHost_P.pak",
        "WeaponFoundry_GraftSafeHost_P.ucas",
        "WeaponFoundry_GraftSafeHost_P.utoc"
    )) {
        $legacyPath = Join-Path $mods $legacy
        if (Test-Path -LiteralPath $legacyPath) {
            Remove-Item -Force $legacyPath
        }
    }

    foreach ($file in @($pak,$ucas,$utoc,$overlayPak,$overlayUcas,$overlayUtoc)) {
        Copy-Item -LiteralPath $file -Destination (Join-Path $mods ([System.IO.Path]::GetFileName($file))) -Force
    }
    Write-Host "Installed Weapon Foundry baseline + read-only GRAFT gate overlay to $mods"
}

Write-Host "8/8 Read-only GRAFT gate probe build complete."
Write-Host ""
Write-Host "TEST:"
Write-Host "  1. Equip any weapon you intend to graft onto."
Write-Host "  2. Find a dropped donor with one or more affixes."
Write-Host "  3. Press E on the donor (normal swap is temporarily blocked)."
Write-Host "  4. Record the red WF GATE / WF READY / WF BLOCKED message."
Write-Host ""
Write-Host "This read-only diagnostic does not transfer affixes, debit cells or consume weapons."
Write-Host "Restore normal gameplay afterward with tools\windows\run-weapon-foundry.cmd."
