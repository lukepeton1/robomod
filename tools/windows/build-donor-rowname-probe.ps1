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
    $OutputDir = Join-Path $RepoRoot "build\donor-rowname-probe"
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
$jsonRoot = Join-Path $OutputDir "work\donor-rowname-json"
$reportRoot = Join-Path $OutputDir "work\donor-rowname-reports"
New-Item -ItemType Directory -Force -Path $jsonRoot,$reportRoot | Out-Null

$originalJson = Join-Path $jsonRoot "BP_Interactive_Weapon.original.json"
$patchedJson = Join-Path $jsonRoot "BP_Interactive_Weapon.donor-rowname-probe.json"
$roundtripJson = Join-Path $jsonRoot "BP_Interactive_Weapon.roundtrip.json"
$stageBase = Join-Path $stageRoot ("RoboQuest\Content\" + $relative)
$patcher = Join-Path $RepoRoot "tools\patch_donor_rowname_probe.py"
$kismetLayout = Join-Path $RepoRoot "tools\kismet_layout.py"

Write-Host "2/8 Exporting dropped-weapon Blueprint..."
Export-UAssetJson $source $originalJson "UAssetGUI BP_Interactive_Weapon tojson"
Invoke-Python @($kismetLayout, $originalJson, "--validate")

Write-Host "3/8 Injecting native AAWeapon.GetAffixRowNames diagnostic..."
Invoke-Python @(
    $patcher,
    $originalJson,
    $patchedJson,
    "--report",
    (Join-Path $reportRoot "donor-rowname-probe.json")
)

Write-Host "4/8 Rebuilding and round-trip verifying diagnostic Blueprint..."
Build-UAssetFromJson $patchedJson $stageBase "UAssetGUI donor row-name probe fromjson"
Export-UAssetJson ($stageBase + ".uasset") $roundtripJson "UAssetGUI donor row-name probe round-trip"
Invoke-Python @($patcher, $roundtripJson, "--verify-only")
Invoke-Python @($kismetLayout, $roundtripJson, "--validate")

Write-Host "5/8 Repacking the full RC plus native row-name probe..."
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
    throw "retoc donor-rowname probe to-zen failed with exit code $($proc.ExitCode)."
}

$pak = Join-Path $releaseRoot "WeaponFoundry_P.pak"
$ucas = Join-Path $releaseRoot "WeaponFoundry_P.ucas"
foreach ($required in @($pak,$ucas,$utoc)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Donor row-name probe container missing: $required"
    }
}

Write-Host "6/8 Writing diagnostic manifest..."
$manifest = [ordered]@{
    build = "weapon-foundry-donor-rowname-probe"
    diagnostic_probe = $true
    generated_utc = [DateTime]::UtcNow.ToString("o")
    production_release_candidate_included = $true
    purpose = "Validate AAWeapon.GetAffixRowNames() as the authoritative donor-row enumeration seam."
    evidence = @(
        "shipping metadata exposes AAWeapon reflected property Affixes",
        "shipping metadata exposes native GetAffixRow and GetAffixRowNames beside GetCurrentEnchantedAffixRowName/GetDataRowName"
    )
    modified_probe_package = "RoboQuest/Content/Blueprint/Interactive/Reward/BP_Interactive_Weapon"
    native_call = "SpawnedWeapon.GetAffixRowNames()"
    expected_return_model = "TArray<FName>"
    trigger = "press the normal interaction key on an affixed dropped weapon; diagnostic CanInteract=false causes GetErrorText to render"
    expected_screen_output = @(
        "WF ROW PROBE: GetAffixRowNames returned rows",
        "or",
        "WF ROW PROBE: GetAffixRowNames returned 0 rows"
    )
    interaction_temporarily_disabled = $true
    interpretation = [ordered]@{
        positive = "Native AAWeapon row-name enumeration is viable; promote GetAffixRowNames into GRAFT donor discovery."
        zero = "Getter executed but returned no row names for a visibly affixed weapon; inspect getter semantics/signature before production use."
        crash_or_load_failure = "Treat the synthesized getter call as invalid; restore normal RC and do not promote it."
    }
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $releaseRoot "donor-rowname-probe-manifest.json") -Encoding UTF8

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
    Write-Host "Installed donor row-name probe to $mods"
}

Write-Host "8/8 Donor row-name probe build complete."
Write-Host ""
Write-Host "In Roboquest, find a dropped weapon whose tooltip visibly lists at least one affix."
Write-Host "Press the normal interaction key (E by default)."
Write-Host "The diagnostic intentionally blocks the swap and should display one of:"
Write-Host "  WF ROW PROBE: GetAffixRowNames returned rows"
Write-Host "  WF ROW PROBE: GetAffixRowNames returned 0 rows"
Write-Host ""
Write-Host "Restore the normal RC afterward with tools\windows\run-weapon-foundry.cmd."
