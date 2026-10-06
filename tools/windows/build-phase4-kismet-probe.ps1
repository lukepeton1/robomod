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
    $OutputDir = Join-Path $RepoRoot "build\phase4-kismet-probe"
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
    if ($proc.ExitCode -ne 0) { throw "$Label failed with process exit code $($proc.ExitCode)." }
    if ($ExpectedOutput -and -not (Test-Path -LiteralPath $ExpectedOutput)) {
        $afterClipboard = $null
        try { $afterClipboard = Get-Clipboard -Raw -ErrorAction SilentlyContinue } catch {}
        $detail = ""
        if ($afterClipboard -and $afterClipboard -ne $beforeClipboard) {
            $detail = [Environment]::NewLine + [Environment]::NewLine +
                "UAssetGUI exception copied to clipboard:" + [Environment]::NewLine + $afterClipboard
        }
        throw "$Label did not create expected output '$ExpectedOutput'.$detail"
    }
}

function Export-UAssetJson([string]$Uasset, [string]$Json, [string]$Label) {
    Invoke-UAssetGUI @(
        "tojson", ('"' + $Uasset + '"'), ('"' + $Json + '"'), "VER_UE4_26"
    ) $Json $Label
}

function Build-UAssetFromJson([string]$Json, [string]$OutputBase, [string]$Label) {
    New-Item -ItemType Directory -Force -Path ([System.IO.Path]::GetDirectoryName($OutputBase)) | Out-Null
    Invoke-UAssetGUI @(
        "fromjson", ('"' + $Json + '"'), ('"' + $OutputBase + '.uasset' + '"')
    ) ($OutputBase + ".uasset") $Label
}

Write-Host "1/11 Building the verified production baseline..."
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
    throw "Production baseline build failed with exit code $LASTEXITCODE."
}

$contentRoot = $null
foreach ($candidate in @((Join-Path $LegacyExtractRoot "RoboQuest\Content"), $LegacyExtractRoot)) {
    if (Test-Path -LiteralPath (Join-Path $candidate "Data\DT_WeaponAffix.uasset")) {
        $contentRoot = [System.IO.Path]::GetFullPath($candidate)
        break
    }
}
if (-not $contentRoot) { throw "Could not locate Roboquest legacy Content root." }

$workRoot = Join-Path $OutputDir "work"
$jsonRoot = Join-Path $workRoot "phase4-json"
$reportRoot = Join-Path $workRoot "phase4-reports"
$stageRoot = Join-Path $OutputDir "staging"
$releaseRoot = Join-Path $OutputDir "release"
New-Item -ItemType Directory -Force -Path $jsonRoot,$reportRoot | Out-Null

$dataPatcher = Join-Path $RepoRoot "tools\patch_uassetapi_datatable.py"
$dataVerifier = Join-Path $RepoRoot "tools\verify_uassetapi_patch.py"
$homingPatcher = Join-Path $RepoRoot "tools\patch_homing_resolver.py"
$foundryGuard = Join-Path $RepoRoot "tools\patch_foundry_interactive.py"
$kismetLayout = Join-Path $RepoRoot "tools\kismet_layout.py"
$seekerSpec = Join-Path $RepoRoot "Source\probes\raycast_seeker_eligibility.json"

$affixStage = Join-Path $stageRoot "RoboQuest\Content\Data\DT_WeaponAffix"
$homingRelative = "Blueprint\Weapon\Affixes\Prefab\BP_WA_Homing"
$homingSource = Join-Path $contentRoot ($homingRelative + ".uasset")
$homingStage = Join-Path $stageRoot ("RoboQuest\Content\" + $homingRelative)
$interactiveRelative = "Blueprint\Interactive\Merchant\BP_Interactive_Merchant_AddEnchantedAffix"
$interactiveSource = Join-Path $contentRoot ($interactiveRelative + ".uasset")
$interactiveStage = Join-Path $stageRoot ("RoboQuest\Content\" + $interactiveRelative)

foreach ($source in @($homingSource,$interactiveSource,($affixStage + ".uasset"))) {
    if (-not (Test-Path -LiteralPath $source)) { throw "Phase 4 source missing: $source" }
}

Write-Host "2/11 Expanding Seeker eligibility to native Raycast + Projectile chassis..."
$affixProductionJson = Join-Path $jsonRoot "DT_WeaponAffix.production.json"
$affixProbeJson = Join-Path $jsonRoot "DT_WeaponAffix.phase4.json"
$affixRoundJson = Join-Path $jsonRoot "DT_WeaponAffix.roundtrip.json"
Export-UAssetJson ($affixStage + ".uasset") $affixProductionJson "UAssetGUI production affix tojson"
Invoke-Python @(
    $dataPatcher,$affixProductionJson,$seekerSpec,$affixProbeJson,
    "--report",(Join-Path $reportRoot "raycast-seeker-eligibility.json")
)
Build-UAssetFromJson $affixProbeJson $affixStage "UAssetGUI Phase 4 affix fromjson"

Write-Host "3/11 Exporting and validating clean Homing Blueprint..."
$homingOriginalJson = Join-Path $jsonRoot "BP_WA_Homing.original.json"
$homingPatchedJson = Join-Path $jsonRoot "BP_WA_Homing.phase4.json"
$homingRoundJson = Join-Path $jsonRoot "BP_WA_Homing.roundtrip.json"
Export-UAssetJson $homingSource $homingOriginalJson "UAssetGUI Homing tojson"
Invoke-Python @($kismetLayout,$homingOriginalJson,"--validate")

Write-Host "4/11 Inserting the live Raycast -> Projectile Seeker resolver..."
Invoke-Python @(
    $homingPatcher,$homingOriginalJson,$homingPatchedJson,
    "--report",(Join-Path $reportRoot "homing-resolver.json")
)
Build-UAssetFromJson $homingPatchedJson $homingStage "UAssetGUI Phase 4 Homing fromjson"

Write-Host "5/11 Exporting and validating clean Foundry purchase interactive..."
$interactiveOriginalJson = Join-Path $jsonRoot "BP_Interactive_Merchant_AddEnchantedAffix.original.json"
$interactivePatchedJson = Join-Path $jsonRoot "BP_Interactive_Merchant_AddEnchantedAffix.phase4.json"
$interactiveRoundJson = Join-Path $jsonRoot "BP_Interactive_Merchant_AddEnchantedAffix.roundtrip.json"
Export-UAssetJson $interactiveSource $interactiveOriginalJson "UAssetGUI Foundry interactive tojson"
Invoke-Python @($kismetLayout,$interactiveOriginalJson,"--validate")

Write-Host "6/11 Inserting the six-affix Foundry transaction guard..."
Invoke-Python @(
    $foundryGuard,$interactiveOriginalJson,$interactivePatchedJson,
    "--max-affixes","6",
    "--report",(Join-Path $reportRoot "foundry-affix-cap.json")
)
Build-UAssetFromJson $interactivePatchedJson $interactiveStage "UAssetGUI Phase 4 Foundry interactive fromjson"

Write-Host "7/11 Re-exporting Phase 4 cooked packages..."
Export-UAssetJson ($affixStage + ".uasset") $affixRoundJson "UAssetGUI Phase 4 affix round-trip"
Export-UAssetJson ($homingStage + ".uasset") $homingRoundJson "UAssetGUI Phase 4 Homing round-trip"
Export-UAssetJson ($interactiveStage + ".uasset") $interactiveRoundJson "UAssetGUI Phase 4 Foundry interactive round-trip"

Write-Host "8/11 Verifying semantic patches and exact Kismet byte layout..."
Invoke-Python @($dataVerifier,$affixRoundJson,$seekerSpec)
Invoke-Python @($homingPatcher,$homingRoundJson,"--verify-only")
Invoke-Python @($foundryGuard,$interactiveRoundJson,"--max-affixes","6","--verify-only")
Invoke-Python @($kismetLayout,$homingRoundJson,"--validate")
Invoke-Python @($kismetLayout,$interactiveRoundJson,"--validate")

Write-Host "9/11 Repacking the complete Phase 4 staging tree..."
foreach ($name in @("WeaponFoundry_P.pak","WeaponFoundry_P.ucas","WeaponFoundry_P.utoc")) {
    $existing = Join-Path $releaseRoot $name
    if (Test-Path -LiteralPath $existing) { Remove-Item -Force $existing }
}
$utoc = Join-Path $releaseRoot "WeaponFoundry_P.utoc"
$proc = Start-Process -FilePath $RetocPath -ArgumentList @(
    "to-zen","--version","UE4_26",
    ('"' + $stageRoot + '"'),
    ('"' + $utoc + '"')
) -Wait -PassThru
if ($proc.ExitCode -ne 0) { throw "retoc Phase 4 to-zen failed with exit code $($proc.ExitCode)." }

$pak = Join-Path $releaseRoot "WeaponFoundry_P.pak"
$ucas = Join-Path $releaseRoot "WeaponFoundry_P.ucas"
foreach ($required in @($pak,$ucas,$utoc)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Phase 4 container missing: $required" }
}

Write-Host "10/11 Writing Phase 4 manifest..."
$manifest = [ordered]@{
    build = "phase4-kismet-probe"
    diagnostic_probe = $true
    generated_utc = [DateTime]::UtcNow.ToString("o")
    production_baseline_included = $true
    probe_changes = @(
        "Homing eligibility expanded to 74 standard Projectile/Raycast chassis",
        "BP_WA_Homing live HitType/Speed/CollisionSize/Gravity resolver",
        "BP_Interactive_Merchant_AddEnchantedAffix six-affix CanInteract guard"
    )
    modified_packages_added_to_production = @(
        "RoboQuest/Content/Blueprint/Weapon/Affixes/Prefab/BP_WA_Homing",
        "RoboQuest/Content/Blueprint/Interactive/Merchant/BP_Interactive_Merchant_AddEnchantedAffix"
    )
}
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $releaseRoot "phase4-manifest.json") -Encoding UTF8

Write-Host "11/11 Optionally installing Phase 4 probe..."
if ($Install) {
    if (-not $GamePaksDir) { throw "-Install requires -GamePaksDir." }
    $GamePaksDir = Resolve-Existing $GamePaksDir "Game Paks directory"
    $mods = Join-Path $GamePaksDir "Mods"
    New-Item -ItemType Directory -Force -Path $mods | Out-Null
    foreach ($file in @($pak,$ucas,$utoc)) {
        Copy-Item -LiteralPath $file -Destination (Join-Path $mods ([System.IO.Path]::GetFileName($file))) -Force
    }
    Write-Host "Installed Phase 4 Kismet probe to $mods"
}

Write-Host ""
Write-Host "Phase 4 Kismet probe complete."
Write-Host "Use tools\windows\run-weapon-foundry.cmd to restore the production baseline."
