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
    $OutputDir = Join-Path $RepoRoot "build\donor-identity-probe"
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
    throw "Could not locate the Roboquest legacy Content root."
}

$relative = "Blueprint\Interactive\Reward\BP_Interactive_Weapon"
$source = Join-Path $contentRoot ($relative + ".uasset")
$stageRoot = Join-Path $OutputDir "staging"
$releaseRoot = Join-Path $OutputDir "release"
$jsonRoot = Join-Path $OutputDir "work\donor-identity-json"
$reportRoot = Join-Path $OutputDir "work\donor-identity-reports"
New-Item -ItemType Directory -Force -Path $jsonRoot,$reportRoot | Out-Null

$originalJson = Join-Path $jsonRoot "BP_Interactive_Weapon.original.json"
$patchedJson = Join-Path $jsonRoot "BP_Interactive_Weapon.donor-identity-probe.json"
$roundtripJson = Join-Path $jsonRoot "BP_Interactive_Weapon.roundtrip.json"
$stageBase = Join-Path $stageRoot ("RoboQuest\Content\" + $relative)
$patcher = Join-Path $RepoRoot "tools\patch_donor_identity_probe.py"
$kismetLayout = Join-Path $RepoRoot "tools\kismet_layout.py"

Write-Host "2/8 Exporting dropped-weapon Blueprint..."
Export-UAssetJson $source $originalJson "UAssetGUI BP_Interactive_Weapon tojson"
Invoke-Python @($kismetLayout, $originalJson, "--validate")

Write-Host "3/8 Injecting AWeaponAffix actor-enumeration diagnostic..."
Invoke-Python @(
    $patcher,
    $originalJson,
    $patchedJson,
    "--report",
    (Join-Path $reportRoot "donor-identity-probe.json")
)

Write-Host "4/8 Rebuilding and round-trip verifying diagnostic Blueprint..."
Build-UAssetFromJson $patchedJson $stageBase "UAssetGUI donor identity probe fromjson"
Export-UAssetJson ($stageBase + ".uasset") $roundtripJson "UAssetGUI donor identity probe round-trip"
Invoke-Python @($patcher, $roundtripJson, "--verify-only")
Invoke-Python @($kismetLayout, $roundtripJson, "--validate")

Write-Host "5/8 Repacking the full RC plus donor-enumeration probe..."
foreach ($name in @("WeaponFoundry_P.pak","WeaponFoundry_P.ucas","WeaponFoundry_P.utoc")) {
    $existing = Join-Path $releaseRoot $name
    if (Test-Path -LiteralPath $existing) {
        Remove-Item -Force $existing
    }
}
$utoc = Join-Path $releaseRoot "WeaponFoundry_P.utoc"
$proc = Start-Process -FilePath $RetocPath -ArgumentList @(
    "to-zen",
    "--version",
    "UE4_26",
    ('"' + $stageRoot + '"'),
    ('"' + $utoc + '"')
) -Wait -PassThru
if ($proc.ExitCode -ne 0) {
    throw "retoc donor-identity probe to-zen failed with exit code $($proc.ExitCode)."
}

$pak = Join-Path $releaseRoot "WeaponFoundry_P.pak"
$ucas = Join-Path $releaseRoot "WeaponFoundry_P.ucas"
foreach ($required in @($pak,$ucas,$utoc)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Donor-identity probe container missing: $required"
    }
}

Write-Host "6/8 Writing diagnostic manifest..."
$manifest = [ordered]@{
    build = "weapon-foundry-donor-identity-probe"
    diagnostic_probe = $true
    generated_utc = [DateTime]::UtcNow.ToString("o")
    production_release_candidate_included = $true
    purpose = "Validate that live AWeaponAffix instances can be enumerated as actors from cooked Blueprint."
    modified_probe_package = "RoboQuest/Content/Blueprint/Interactive/Reward/BP_Interactive_Weapon"
    trigger = "BP_Interactive_Weapon.GetInteractSound"
    expected_screen_output = @(
        "Weapon Foundry AWeaponAffix count:",
        "<integer count>"
    )
    interpretation = [ordered]@{
        positive = "A count greater than zero proves the native actor-enumeration primitive needed for donor row identity."
        zero = "Zero while weapons with affixes are live disproves or narrows the actor-enumeration hypothesis."
        crash_or_load_failure = "Treat as a failed probe; restore the normal RC and keep the runtime enumeration seam unproven."
    }
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $releaseRoot "donor-identity-probe-manifest.json") -Encoding UTF8

Write-Host "7/8 Optionally installing diagnostic containers..."
if ($Install) {
    if (-not $GamePaksDir) {
        throw "-Install requires -GamePaksDir."
    }
    $GamePaksDir = Resolve-Existing $GamePaksDir "Game Paks directory"
    $mods = Join-Path $GamePaksDir "Mods"
    New-Item -ItemType Directory -Force -Path $mods | Out-Null
    foreach ($file in @($pak,$ucas,$utoc)) {
        Copy-Item -LiteralPath $file -Destination (Join-Path $mods ([System.IO.Path]::GetFileName($file))) -Force
    }
    Write-Host "Installed donor-identity probe to $mods"
}

Write-Host "8/8 Donor identity probe build complete."
Write-Host ""
Write-Host "In Roboquest, keep at least one affixed weapon alive and interact with/focus a dropped weapon."
Write-Host "Look for:"
Write-Host "  Weapon Foundry AWeaponAffix count:"
Write-Host "  <integer count>"
Write-Host ""
Write-Host "Restore the normal RC afterward with tools\windows\run-weapon-foundry.cmd."
