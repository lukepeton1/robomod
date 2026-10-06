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
    $OutputDir = Join-Path $RepoRoot "build\rc-smoke"
}

function Resolve-Existing([string]$Path, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Path)) { throw "$Label not found: $Path" }
    return [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $Path).Path)
}

function Find-Python {
    foreach ($candidate in @(
        @{ File = "python"; Prefix = @() },
        @{ File = "py"; Prefix = @("-3") }
    )) {
        if (Get-Command $candidate.File -ErrorAction SilentlyContinue) { return $candidate }
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
    if ($LASTEXITCODE -ne 0) { throw "Python command failed with exit code $LASTEXITCODE." }
}

function Invoke-UAssetGUI([string[]]$Arguments, [string]$ExpectedOutput, [string]$Label) {
    $beforeClipboard = $null
    try { $beforeClipboard = Get-Clipboard -Raw -ErrorAction SilentlyContinue } catch {}

    $proc = Start-Process -FilePath $UAssetGUIPath -ArgumentList $Arguments -Wait -PassThru
    if ($proc.ExitCode -ne 0) { throw "$Label failed with exit code $($proc.ExitCode)." }

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

Write-Host "1/8 Building the full production release candidate baseline..."
$prodArgs = @(
    "-ExecutionPolicy", "Bypass",
    "-File", (Join-Path $RepoRoot "tools\windows\build-weapon-foundry.ps1"),
    "-LegacyExtractRoot", $LegacyExtractRoot,
    "-UAssetGUIPath", $UAssetGUIPath,
    "-RetocPath", $RetocPath,
    "-RepoRoot", $RepoRoot,
    "-OutputDir", $OutputDir
)
& powershell @prodArgs
if ($LASTEXITCODE -ne 0) {
    throw "Production RC baseline build failed with exit code $LASTEXITCODE."
}

$contentRoot = $null
foreach ($candidate in @(
    (Join-Path $LegacyExtractRoot "RoboQuest\Content"),
    $LegacyExtractRoot
)) {
    if (Test-Path -LiteralPath (Join-Path $candidate "Data\DT_Weapons.uasset")) {
        $contentRoot = [System.IO.Path]::GetFullPath($candidate)
        break
    }
}
if (-not $contentRoot) { throw "Could not locate Roboquest legacy Content root." }

$stageRoot = Join-Path $OutputDir "staging"
$releaseRoot = Join-Path $OutputDir "release"
$jsonRoot = Join-Path $OutputDir "work\rc-smoke-json"
$reportRoot = Join-Path $OutputDir "work\rc-smoke-reports"
New-Item -ItemType Directory -Force -Path $jsonRoot,$reportRoot | Out-Null

$weaponsSource = Join-Path $contentRoot "Data\DT_Weapons.uasset"
$weaponsStage = Join-Path $stageRoot "RoboQuest\Content\Data\DT_Weapons"
$skillsStage = Join-Path $stageRoot "RoboQuest\Content\Data\DT_PlayerSkills.uasset"
$probeSpec = Join-Path $RepoRoot "Source\probes\rc_smoke_handgun.json"
$dataPatcher = Join-Path $RepoRoot "tools\patch_uassetapi_datatable.py"
$dataVerifier = Join-Path $RepoRoot "tools\verify_uassetapi_patch.py"

Write-Host "2/8 Asserting the production baseline does not override DT_PlayerSkills..."
if (Test-Path -LiteralPath $skillsStage) {
    throw "Production baseline unexpectedly contains DT_PlayerSkills; native Raycast invariant cannot be trusted."
}

Write-Host "3/8 Patching only the starter HandGun preset affixes..."
$weaponsOriginal = Join-Path $jsonRoot "DT_Weapons.original.json"
$weaponsPatched = Join-Path $jsonRoot "DT_Weapons.rc-smoke.json"
$weaponsRound = Join-Path $jsonRoot "DT_Weapons.roundtrip.json"
Export-UAssetJson $weaponsSource $weaponsOriginal "UAssetGUI clean DT_Weapons tojson"
Invoke-Python @(
    $dataPatcher,
    $weaponsOriginal,
    $probeSpec,
    $weaponsPatched,
    "--report",
    (Join-Path $reportRoot "rc-smoke-handgun.json")
)

Write-Host "4/8 Rebuilding the diagnostic-only DT_Weapons package..."
Build-UAssetFromJson $weaponsPatched $weaponsStage "UAssetGUI RC-smoke DT_Weapons fromjson"

Write-Host "5/8 Re-exporting and verifying the smoke weapon..."
Export-UAssetJson ($weaponsStage + ".uasset") $weaponsRound "UAssetGUI RC-smoke DT_Weapons round-trip"
Invoke-Python @($dataVerifier,$weaponsRound,$probeSpec)

Write-Host "6/8 Repacking the complete RC smoke staging tree..."
foreach ($name in @("WeaponFoundry_P.pak","WeaponFoundry_P.ucas","WeaponFoundry_P.utoc")) {
    $existing = Join-Path $releaseRoot $name
    if (Test-Path -LiteralPath $existing) { Remove-Item -Force $existing }
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
    throw "retoc RC-smoke to-zen failed with exit code $($proc.ExitCode)."
}

$pak = Join-Path $releaseRoot "WeaponFoundry_P.pak"
$ucas = Join-Path $releaseRoot "WeaponFoundry_P.ucas"
foreach ($required in @($pak,$ucas,$utoc)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "RC-smoke container missing: $required"
    }
}

Write-Host "7/8 Writing smoke manifest..."
$manifest = [ordered]@{
    build = "weapon-foundry-rc-smoke"
    diagnostic_probe = $true
    generated_utc = [DateTime]::UtcNow.ToString("o")
    production_release_candidate_included = $true
    native_raycast_skill_invariant = "DT_PlayerSkills is not overridden"
    diagnostic_weapon_row = "HandGun"
    diagnostic_affixes = @(
        "Homing",
        "Bounce",
        "Fragmentation",
        "Burn",
        "ExplosiveBlank",
        "FreeShot"
    )
    expected_semantics = @(
        "native PF_Handgun begins as Raycast",
        "production BP_WA_Homing converts the live skill to Projectile",
        "parent projectile homes",
        "Bounce remains active",
        "Fragments spawn",
        "fragment GameplayTags inherit Burn/Explosive semantics",
        "Freewheel repeats the resolved native shot"
    )
    diagnostic_only_package = "RoboQuest/Content/Data/DT_Weapons"
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $releaseRoot "rc-smoke-manifest.json") -Encoding UTF8

Write-Host "8/8 Optionally installing RC smoke build..."
if ($Install) {
    if (-not $GamePaksDir) { throw "-Install requires -GamePaksDir." }
    $GamePaksDir = Resolve-Existing $GamePaksDir "Game Paks directory"
    $mods = Join-Path $GamePaksDir "Mods"
    New-Item -ItemType Directory -Force -Path $mods | Out-Null
    foreach ($file in @($pak,$ucas,$utoc)) {
        Copy-Item -LiteralPath $file -Destination (Join-Path $mods ([System.IO.Path]::GetFileName($file))) -Force
    }
    Write-Host "Installed Weapon Foundry RC smoke build to $mods"
}

Write-Host ""
Write-Host "RC smoke build complete."
Write-Host "The Fox Gun skill table was NOT modified. If its shot becomes a traveling homing projectile, the production resolver is working."
Write-Host "Restore the normal release candidate afterward with tools\windows\run-weapon-foundry.cmd."
