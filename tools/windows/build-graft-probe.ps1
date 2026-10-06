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
if (-not $RepoRoot) { $RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $scriptRoot "..\..")) }
if (-not $OutputDir) { $OutputDir = Join-Path $RepoRoot "build\graft-probe" }

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
                "UAssetGUI exception copied to clipboard:" + [Environment]::NewLine + $afterClipboard
        }
        throw "$Label did not create '$ExpectedOutput'.$detail"
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
foreach ($candidate in @((Join-Path $LegacyExtractRoot "RoboQuest\Content"), $LegacyExtractRoot)) {
    if (Test-Path -LiteralPath (Join-Path $candidate "Data\DT_WeaponAffix.uasset")) {
        $contentRoot = [System.IO.Path]::GetFullPath($candidate)
        break
    }
}
if (-not $contentRoot) { throw "Could not locate Roboquest legacy Content root." }

$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$workRoot = Join-Path $OutputDir "work"
$jsonRoot = Join-Path $workRoot "json"
$reportRoot = Join-Path $workRoot "reports"
$cleanRoot = Join-Path $workRoot "clean-roundtrip"
$stageRoot = Join-Path $OutputDir "staging"
$releaseRoot = Join-Path $OutputDir "release"
if (Test-Path -LiteralPath $OutputDir) { Remove-Item -Recurse -Force $OutputDir }
New-Item -ItemType Directory -Force -Path $jsonRoot,$reportRoot,$cleanRoot,$releaseRoot | Out-Null

$affixRelative = "Data\DT_WeaponAffix"
$fragRelative = "Blueprint\Weapon\Affixes\Common\BP_WA_Fragmentation"
$merchantRelative = "Blueprint\Interactive\Merchant\BP_Merchant_UpgradeAffix"

$affixSource = Join-Path $contentRoot ($affixRelative + ".uasset")
$fragSource = Join-Path $contentRoot ($fragRelative + ".uasset")
$merchantSource = Join-Path $contentRoot ($merchantRelative + ".uasset")
foreach ($source in @($affixSource,$fragSource,$merchantSource)) {
    if (-not (Test-Path -LiteralPath $source)) { throw "Required legacy package missing: $source" }
}

$coreSpec = Join-Path $RepoRoot "Source\patches\weapon_foundry_core.json"
$probeSpec = Join-Path $RepoRoot "Source\probes\graft_merchant_probe.json"
$dataPatcher = Join-Path $RepoRoot "tools\patch_uassetapi_datatable.py"
$dataVerifier = Join-Path $RepoRoot "tools\verify_uassetapi_patch.py"
$fragPatcher = Join-Path $RepoRoot "tools\patch_fragmentation_bytecode.py"
$cdoPatcher = Join-Path $RepoRoot "tools\patch_uassetapi_cdo.py"

$affixOriginal = Join-Path $jsonRoot "DT_WeaponAffix.original.json"
$affixPatched = Join-Path $jsonRoot "DT_WeaponAffix.probe.json"
$affixRound = Join-Path $jsonRoot "DT_WeaponAffix.roundtrip.json"
$fragOriginal = Join-Path $jsonRoot "BP_WA_Fragmentation.original.json"
$fragPatched = Join-Path $jsonRoot "BP_WA_Fragmentation.probe.json"
$fragRound = Join-Path $jsonRoot "BP_WA_Fragmentation.roundtrip.json"
$merchantOriginal = Join-Path $jsonRoot "BP_Merchant_UpgradeAffix.original.json"
$merchantPatched = Join-Path $jsonRoot "BP_Merchant_UpgradeAffix.probe.json"
$merchantRound = Join-Path $jsonRoot "BP_Merchant_UpgradeAffix.roundtrip.json"

Write-Host "1/9 Exporting production core + perfumer source packages..."
Export-UAssetJson $affixSource $affixOriginal "UAssetGUI affix tojson"
Export-UAssetJson $fragSource $fragOriginal "UAssetGUI Fragmentation tojson"
Export-UAssetJson $merchantSource $merchantOriginal "UAssetGUI perfumer tojson"

Write-Host "2/9 Proving clean perfumer Blueprint round-trip..."
$merchantCleanBase = Join-Path $cleanRoot ("RoboQuest\Content\" + $merchantRelative)
Build-UAssetFromJson $merchantOriginal $merchantCleanBase "UAssetGUI clean perfumer fromjson"
Export-UAssetJson ($merchantCleanBase + ".uasset") (Join-Path $jsonRoot "BP_Merchant_UpgradeAffix.clean-roundtrip.json") "UAssetGUI clean perfumer round-trip"

Write-Host "3/9 Applying production compatibility core..."
Invoke-Python @($dataPatcher,$affixOriginal,$coreSpec,$affixPatched,"--report",(Join-Path $reportRoot "weapon-foundry-core.json"))

Write-Host "4/9 Applying verified Fragmentation patch..."
Invoke-Python @($fragPatcher,$fragOriginal,$fragPatched,"--report",(Join-Path $reportRoot "fragmentation-bytecode.json"))

Write-Host "5/9 Seeding native perfumer AffixRows with ordinary graft candidates..."
Invoke-Python @($cdoPatcher,$merchantOriginal,$probeSpec,$merchantPatched,"--report",(Join-Path $reportRoot "graft-merchant-probe.json"))

Write-Host "6/9 Rebuilding three cooked packages..."
$affixStage = Join-Path $stageRoot ("RoboQuest\Content\" + $affixRelative)
$fragStage = Join-Path $stageRoot ("RoboQuest\Content\" + $fragRelative)
$merchantStage = Join-Path $stageRoot ("RoboQuest\Content\" + $merchantRelative)
Build-UAssetFromJson $affixPatched $affixStage "UAssetGUI probe DT_WeaponAffix fromjson"
Build-UAssetFromJson $fragPatched $fragStage "UAssetGUI probe Fragmentation fromjson"
Build-UAssetFromJson $merchantPatched $merchantStage "UAssetGUI probe perfumer fromjson"

Write-Host "7/9 Re-exporting and verifying every probe package..."
Export-UAssetJson ($affixStage + ".uasset") $affixRound "UAssetGUI probe affix round-trip"
Export-UAssetJson ($fragStage + ".uasset") $fragRound "UAssetGUI probe Fragmentation round-trip"
Export-UAssetJson ($merchantStage + ".uasset") $merchantRound "UAssetGUI probe perfumer round-trip"
Invoke-Python @($dataVerifier,$affixRound,$coreSpec)
Invoke-Python @($fragPatcher,$fragRound,"--verify-only")
Invoke-Python @($cdoPatcher,$merchantRound,$probeSpec,"--verify-only")

Write-Host "8/9 Packing native graft-transaction probe..."
$utoc = Join-Path $releaseRoot "WeaponFoundry_P.utoc"
$proc = Start-Process -FilePath $RetocPath -ArgumentList @(
    "to-zen","--version","UE4_26",
    ('"' + $stageRoot + '"'),
    ('"' + $utoc + '"')
) -Wait -PassThru
if ($proc.ExitCode -ne 0) { throw "retoc to-zen failed with exit code $($proc.ExitCode)." }
$pak = Join-Path $releaseRoot "WeaponFoundry_P.pak"
$ucas = Join-Path $releaseRoot "WeaponFoundry_P.ucas"
foreach ($required in @($pak,$ucas,$utoc)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Missing probe container: $required" }
}

Write-Host "9/9 Writing probe manifest and optionally installing..."
$manifest = [ordered]@{
    build = "weapon-foundry-native-graft-transaction-probe"
    diagnostic_probe = $true
    generated_utc = [DateTime]::UtcNow.ToString("o")
    purpose = "Determine how native AddEnchantedAffix behaves when the perfumer supplies ordinary active affix rows."
    modified_packages = @(
        "RoboQuest/Content/Data/DT_WeaponAffix",
        "RoboQuest/Content/Blueprint/Weapon/Affixes/Common/BP_WA_Fragmentation",
        "RoboQuest/Content/Blueprint/Interactive/Merchant/BP_Merchant_UpgradeAffix"
    )
}
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $releaseRoot "graft-probe-manifest.json") -Encoding UTF8

if ($Install) {
    if (-not $GamePaksDir) { throw "-Install requires -GamePaksDir." }
    $GamePaksDir = Resolve-Existing $GamePaksDir "Game Paks directory"
    $mods = Join-Path $GamePaksDir "Mods"
    New-Item -ItemType Directory -Force -Path $mods | Out-Null
    foreach ($file in @($pak,$ucas,$utoc)) {
        Copy-Item -LiteralPath $file -Destination (Join-Path $mods ([System.IO.Path]::GetFileName($file))) -Force
    }
    Write-Host "Installed native graft probe to $mods"
}

Write-Host ""
Write-Host "Native graft transaction probe build complete."
Write-Host "Find a perfumer and inspect its two offers. Ordinary non-perfumed affix names should now appear frequently."
Write-Host "Run tools\windows\run-weapon-foundry.cmd afterward to restore the production core."
