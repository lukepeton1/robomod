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
    $OutputDir = Join-Path $RepoRoot "build\phase3-diagnostic"
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
$weaponsRelative = "Data\DT_Weapons"
$skillsRelative = "Data\DT_PlayerSkills"
$fragRelative = "Blueprint\Weapon\Affixes\Common\BP_WA_Fragmentation"

$affixSource = Join-Path $contentRoot ($affixRelative + ".uasset")
$weaponsSource = Join-Path $contentRoot ($weaponsRelative + ".uasset")
$skillsSource = Join-Path $contentRoot ($skillsRelative + ".uasset")
$fragSource = Join-Path $contentRoot ($fragRelative + ".uasset")

foreach ($source in @($affixSource, $weaponsSource, $skillsSource, $fragSource)) {
    if (-not (Test-Path -LiteralPath $source)) {
        throw "Required legacy source package not found: $source"
    }
}

$affixOriginalJson = Join-Path $jsonRoot "DT_WeaponAffix.original.json"
$affixPhase1Json = Join-Path $jsonRoot "DT_WeaponAffix.phase1.json"
$affixPatchedJson = Join-Path $jsonRoot "DT_WeaponAffix.phase2.json"
$affixRoundtripJson = Join-Path $jsonRoot "DT_WeaponAffix.roundtrip.json"

$weaponsOriginalJson = Join-Path $jsonRoot "DT_Weapons.original.json"
$weaponsPatchedJson = Join-Path $jsonRoot "DT_Weapons.diagnostic.json"
$weaponsRoundtripJson = Join-Path $jsonRoot "DT_Weapons.roundtrip.json"

$skillsOriginalJson = Join-Path $jsonRoot "DT_PlayerSkills.original.json"
$skillsPatchedJson = Join-Path $jsonRoot "DT_PlayerSkills.diagnostic.json"
$skillsRoundtripJson = Join-Path $jsonRoot "DT_PlayerSkills.roundtrip.json"

$fragOriginalJson = Join-Path $jsonRoot "BP_WA_Fragmentation.original.json"
$fragCleanJson = Join-Path $jsonRoot "BP_WA_Fragmentation.clean-roundtrip.json"
$fragPatchedJson = Join-Path $jsonRoot "BP_WA_Fragmentation.phase2.json"
$fragRoundtripJson = Join-Path $jsonRoot "BP_WA_Fragmentation.roundtrip.json"

$phase1Spec = Join-Path $RepoRoot "Source\patches\phase1_affix_unlocks.json"
$phase2Spec = Join-Path $RepoRoot "Source\patches\phase2_fragmentation_eligibility.json"
$weaponDiagnosticSpec = Join-Path $RepoRoot "Source\patches\phase3_diagnostic_weapon.json"
$skillDiagnosticSpec = Join-Path $RepoRoot "Source\patches\phase3_diagnostic_skill.json"
$dataPatcher = Join-Path $RepoRoot "tools\patch_uassetapi_datatable.py"
$dataVerifier = Join-Path $RepoRoot "tools\verify_uassetapi_patch.py"
$fragPatcher = Join-Path $RepoRoot "tools\patch_fragmentation_bytecode.py"

Write-Host "1/10 Exporting clean Phase 3 diagnostic source packages..."
Export-UAssetJson $affixSource $affixOriginalJson "UAssetGUI DT_WeaponAffix tojson"
Export-UAssetJson $weaponsSource $weaponsOriginalJson "UAssetGUI DT_Weapons tojson"
Export-UAssetJson $skillsSource $skillsOriginalJson "UAssetGUI DT_PlayerSkills tojson"
Export-UAssetJson $fragSource $fragOriginalJson "UAssetGUI Fragmentation tojson"

Write-Host "2/10 Proving clean Fragmentation Blueprint round-trip..."
$fragCleanBase = Join-Path $cleanRoot ("RoboQuest\Content\" + $fragRelative)
Build-UAssetFromJson $fragOriginalJson $fragCleanBase "UAssetGUI clean Fragmentation fromjson"
Export-UAssetJson ($fragCleanBase + ".uasset") $fragCleanJson "UAssetGUI clean Fragmentation round-trip"

Write-Host "3/10 Applying normal Weapon Foundry affix-pool patches..."
Invoke-Python @(
    $dataPatcher, $affixOriginalJson, $phase1Spec, $affixPhase1Json,
    "--report", (Join-Path $reportRoot "phase1-affix-unlocks.json")
)
Invoke-Python @(
    $dataPatcher, $affixPhase1Json, $phase2Spec, $affixPatchedJson,
    "--report", (Join-Path $reportRoot "phase2-fragmentation-eligibility.json")
)

Write-Host "4/10 Patching Fragmentation cooked Kismet..."
Invoke-Python @(
    $fragPatcher, $fragOriginalJson, $fragPatchedJson,
    "--report", (Join-Path $reportRoot "phase2-fragmentation-bytecode.json")
)

Write-Host "5/10 Installing deterministic six-affix starter diagnostic loadout..."
Invoke-Python @(
    $dataPatcher, $weaponsOriginalJson, $weaponDiagnosticSpec, $weaponsPatchedJson,
    "--report", (Join-Path $reportRoot "phase3-diagnostic-weapon.json")
)

Write-Host "6/10 Converting the diagnostic HandGun skill to the generic projectile path..."
Invoke-Python @(
    $dataPatcher, $skillsOriginalJson, $skillDiagnosticSpec, $skillsPatchedJson,
    "--report", (Join-Path $reportRoot "phase3-diagnostic-skill.json")
)

Write-Host "7/10 Rebuilding four patched cooked packages..."
$affixStageBase = Join-Path $stageRoot ("RoboQuest\Content\" + $affixRelative)
$weaponsStageBase = Join-Path $stageRoot ("RoboQuest\Content\" + $weaponsRelative)
$skillsStageBase = Join-Path $stageRoot ("RoboQuest\Content\" + $skillsRelative)
$fragStageBase = Join-Path $stageRoot ("RoboQuest\Content\" + $fragRelative)

Build-UAssetFromJson $affixPatchedJson $affixStageBase "UAssetGUI patched DT_WeaponAffix fromjson"
Build-UAssetFromJson $weaponsPatchedJson $weaponsStageBase "UAssetGUI diagnostic DT_Weapons fromjson"
Build-UAssetFromJson $skillsPatchedJson $skillsStageBase "UAssetGUI diagnostic DT_PlayerSkills fromjson"
Build-UAssetFromJson $fragPatchedJson $fragStageBase "UAssetGUI patched Fragmentation fromjson"

Write-Host "8/10 Re-exporting and verifying every patch..."
Export-UAssetJson ($affixStageBase + ".uasset") $affixRoundtripJson "UAssetGUI DT_WeaponAffix round-trip"
Export-UAssetJson ($weaponsStageBase + ".uasset") $weaponsRoundtripJson "UAssetGUI DT_Weapons round-trip"
Export-UAssetJson ($skillsStageBase + ".uasset") $skillsRoundtripJson "UAssetGUI DT_PlayerSkills round-trip"
Export-UAssetJson ($fragStageBase + ".uasset") $fragRoundtripJson "UAssetGUI Fragmentation round-trip"

Invoke-Python @($dataVerifier, $affixRoundtripJson, $phase1Spec)
Invoke-Python @($dataVerifier, $affixRoundtripJson, $phase2Spec)
Invoke-Python @($dataVerifier, $weaponsRoundtripJson, $weaponDiagnosticSpec)
Invoke-Python @($dataVerifier, $skillsRoundtripJson, $skillDiagnosticSpec)
Invoke-Python @($fragPatcher, $fragRoundtripJson, "--verify-only")

Write-Host "9/10 Packing Phase 3 diagnostic IoStore containers..."
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

Write-Host "10/10 Writing diagnostic manifest and optionally installing..."
$manifest = [ordered]@{
    build = "phase3-diagnostic-composition"
    diagnostic_only = $true
    generated_utc = [DateTime]::UtcNow.ToString("o")
    source_content_root = $contentRoot
    starter_weapon_row = "HandGun"
    starter_skill_row = "PF_Handgun"
    diagnostic_affixes = @(
        "Fragmentation",
        "Homing",
        "Burn",
        "ExplosiveBlank",
        "FreeShot",
        "AutoShotgun"
    )
    diagnostic_hit_type = "EHitType::Projectile"
    modified_packages = @(
        "RoboQuest/Content/Data/DT_WeaponAffix",
        "RoboQuest/Content/Data/DT_Weapons",
        "RoboQuest/Content/Data/DT_PlayerSkills",
        "RoboQuest/Content/Blueprint/Weapon/Affixes/Common/BP_WA_Fragmentation"
    )
    containers = @(
        [ordered]@{ name = "WeaponFoundry_P.pak"; sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $pak).Hash.ToLowerInvariant() },
        [ordered]@{ name = "WeaponFoundry_P.ucas"; sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $ucas).Hash.ToLowerInvariant() },
        [ordered]@{ name = "WeaponFoundry_P.utoc"; sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $utoc).Hash.ToLowerInvariant() }
    )
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $releaseRoot "diagnostic-manifest.json") -Encoding UTF8

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
    Write-Host "Installed Phase 3 diagnostic build over WeaponFoundry_P in $mods"
}

Write-Host ""
Write-Host "Phase 3 diagnostic build complete:"
Write-Host "  $releaseRoot"
Write-Host ""
Write-Host "DIAGNOSTIC ONLY: starter HandGun is temporarily converted to projectile and forced to Fragments + Seeker + Burn + Explosive + Freewheel + Buckshot."
