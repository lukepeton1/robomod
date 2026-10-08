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
    $OutputDir = Join-Path $RepoRoot "build\ground-graft-ping-probe"
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
    if (Test-Path -LiteralPath (Join-Path $candidate "Blueprint\Player\BP_APlayer.uasset")) {
        $contentRoot = [System.IO.Path]::GetFullPath($candidate)
        break
    }
}
if (-not $contentRoot) {
    throw "Could not locate the Roboquest legacy Content root containing BP_APlayer."
}

$relative = "Blueprint\Player\BP_APlayer"
$source = Join-Path $contentRoot ($relative + ".uasset")
$stageRoot = Join-Path $OutputDir "staging"
$probeStageRoot = Join-Path $OutputDir "probe-staging"
$releaseRoot = Join-Path $OutputDir "release"
$jsonRoot = Join-Path $OutputDir "work\ground-graft-ping-json"
$reportRoot = Join-Path $OutputDir "work\ground-graft-ping-reports"
if (Test-Path -LiteralPath $probeStageRoot) {
    Remove-Item -Recurse -Force $probeStageRoot
}
New-Item -ItemType Directory -Force -Path $jsonRoot,$reportRoot,$probeStageRoot | Out-Null

$originalJson = Join-Path $jsonRoot "BP_APlayer.original.json"
$patchedJson = Join-Path $jsonRoot "BP_APlayer.ground-graft-ping-probe.json"
$roundtripJson = Join-Path $jsonRoot "BP_APlayer.roundtrip.json"
$stageBase = Join-Path $probeStageRoot ("RoboQuest\Content\" + $relative)
$patcher = Join-Path $RepoRoot "tools\patch_ground_graft_ping_probe.py"
$spec = Join-Path $RepoRoot "Source\probes\ground_graft_ping_probe.json"
$kismetLayout = Join-Path $RepoRoot "tools\kismet_layout.py"

Write-Host "2/8 Exporting BP_APlayer..."
Export-UAssetJson $source $originalJson "UAssetGUI BP_APlayer tojson"
Invoke-Python @($kismetLayout, $originalJson, "--validate")

Write-Host "3/8 Injecting server-authoritative ping GRAFT transaction..."
Invoke-Python @(
    $patcher,
    $originalJson,
    $spec,
    $patchedJson,
    "--report",
    (Join-Path $reportRoot "ground-graft-ping-probe.json")
)

Write-Host "4/8 Rebuilding and round-trip verifying BP_APlayer..."
Build-UAssetFromJson $patchedJson $stageBase "UAssetGUI ground GRAFT ping probe fromjson"
Export-UAssetJson ($stageBase + ".uasset") $roundtripJson "UAssetGUI ground GRAFT ping probe round-trip"
Invoke-Python @($patcher, $roundtripJson, $spec, "--verify-only")
Invoke-Python @($kismetLayout, $roundtripJson, "--validate")

Write-Host "5/8 Packing BP_APlayer as a separate ground GRAFT overlay..."
$probeNames = @(
    "WeaponFoundry_GraftProbe_P.pak",
    "WeaponFoundry_GraftProbe_P.ucas",
    "WeaponFoundry_GraftProbe_P.utoc"
)
foreach ($name in $probeNames) {
    $existing = Join-Path $releaseRoot $name
    if (Test-Path -LiteralPath $existing) {
        Remove-Item -Force $existing
    }
}

$probeUtoc = Join-Path $releaseRoot "WeaponFoundry_GraftProbe_P.utoc"
$retocLog = Join-Path $reportRoot "retoc-ground-graft-to-zen.log"
$retocArgs = @(
    "to-zen",
    "--version",
    "UE4_26",
    $probeStageRoot,
    $probeUtoc
)

$retocOutput = & $RetocPath @retocArgs 2>&1
$retocExit = $LASTEXITCODE
$retocOutput | Tee-Object -FilePath $retocLog
if ($retocExit -ne 0) {
    throw "retoc ground GRAFT overlay to-zen failed with exit code $retocExit. Full output: $retocLog"
}

$probePak = Join-Path $releaseRoot "WeaponFoundry_GraftProbe_P.pak"
$probeUcas = Join-Path $releaseRoot "WeaponFoundry_GraftProbe_P.ucas"
foreach ($required in @($probePak,$probeUcas,$probeUtoc)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Ground GRAFT overlay container missing: $required"
    }
}

$pak = Join-Path $releaseRoot "WeaponFoundry_P.pak"
$ucas = Join-Path $releaseRoot "WeaponFoundry_P.ucas"
$utoc = Join-Path $releaseRoot "WeaponFoundry_P.utoc"
foreach ($required in @($pak,$ucas,$utoc)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Production baseline container missing after overlay build: $required"
    }
}

Write-Host "6/8 Writing diagnostic manifest..."
$probeSpec = Get-Content -LiteralPath $spec -Raw | ConvertFrom-Json
$candidateRows = @($probeSpec.selection.candidates | ForEach-Object { $_.row })
$manifest = [ordered]@{
    build = "weapon-foundry-ground-graft-ping-probe"
    diagnostic_probe = $true
    generated_utc = [DateTime]::UtcNow.ToString("o")
    production_release_candidate_included = $true
    purpose = "Validate the complete server-side donor GRAFT commit order using Roboquest native row IDs, Power Cells, mutation, verification and donor destruction."
    modified_probe_package = "RoboQuest/Content/Blueprint/Player/BP_APlayer"
    packaging = "separate WeaponFoundry_GraftProbe_P overlay layered on the already-built WeaponFoundry_P baseline"
    retoc_log = "work/ground-graft-ping-reports/retoc-ground-graft-to-zen.log"
    trigger = "existing ping action on a dropped weapon; normal E equip/swap remains untouched"
    authoritative_donor_rows = "AInteractiveWeapon.SpawnedWeapon.GetAffixRowNames()"
    candidate_rows = $candidateRows
    candidate_count = $candidateRows.Count
    success_effects = @(
        "target current weapon gains the selected donor affix",
        "Power Cells debit exactly once",
        "donor dropped weapon disappears only after target row verification",
        "vanilla ping is suppressed on successful GRAFT"
    )
    failure_behavior = "validation failure or no supported donor row falls through to vanilla ping; donor and Power Cells remain unchanged"
    restore = "tools\windows\run-weapon-foundry.cmd"
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $releaseRoot "ground-graft-ping-probe-manifest.json") -Encoding UTF8

Write-Host "7/8 Optionally installing diagnostic containers..."
if ($Install) {
    if (-not $GamePaksDir) {
        throw "-Install requires -GamePaksDir."
    }
    $GamePaksDir = Resolve-Existing $GamePaksDir "Game Paks directory"
    $mods = Join-Path $GamePaksDir "Mods"
    New-Item -ItemType Directory -Force -Path $mods | Out-Null
    foreach ($file in @($pak,$ucas,$utoc,$probePak,$probeUcas,$probeUtoc)) {
        Copy-Item -LiteralPath $file -Destination (Join-Path $mods ([System.IO.Path]::GetFileName($file))) -Force
    }
    Write-Host "Installed Weapon Foundry baseline + ground GRAFT overlay to $mods"
}

Write-Host "8/8 Ground GRAFT ping probe build complete."
Write-Host ""
Write-Host "TEST:"
Write-Host "  1. Use an Uncommon-or-better current weapon."
Write-Host "  2. Keep enough Power Cells for a 2-4 cell base cost plus any complexity surcharge."
Write-Host "  3. Find a dropped weapon with one of these supported donor affixes:"
Write-Host ("     " + ($candidateRows -join ", "))
Write-Host "  4. Aim at the dropped weapon and use the normal PING action -- do NOT press E."
Write-Host ""
Write-Host "SUCCESS should:"
Write-Host "  - add one donor affix to your current weapon"
Write-Host "  - debit Power Cells once"
Write-Host "  - remove the donor only after verification"
Write-Host ""
Write-Host "If validation fails, it should behave like a normal ping and change nothing."
Write-Host "Restore normal production afterward with tools\windows\run-weapon-foundry.cmd."
