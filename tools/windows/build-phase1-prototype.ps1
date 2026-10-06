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
    $OutputDir = Join-Path $RepoRoot "build\phase1"
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
        $cmd = Get-Command $candidate.File -ErrorAction SilentlyContinue
        if ($cmd) {
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
    try {
        $beforeClipboard = Get-Clipboard -Raw -ErrorAction SilentlyContinue
    } catch {}

    $proc = Start-Process -FilePath $UAssetGUIPath -ArgumentList $Arguments -Wait -PassThru

    if ($proc.ExitCode -ne 0) {
        throw "$Label failed with process exit code $($proc.ExitCode)."
    }

    if ($ExpectedOutput -and -not (Test-Path -LiteralPath $ExpectedOutput)) {
        $afterClipboard = $null
        try {
            $afterClipboard = Get-Clipboard -Raw -ErrorAction SilentlyContinue
        } catch {}

        $detail = ""
        if ($afterClipboard -and $afterClipboard -ne $beforeClipboard) {
            $detail = [Environment]::NewLine + [Environment]::NewLine +
                "UAssetGUI exception copied to clipboard:" + [Environment]::NewLine +
                $afterClipboard
        } else {
            $detail = [Environment]::NewLine + [Environment]::NewLine +
                "UAssetGUI v1.1.0 returned exit code 0 but did not expose an exception through the clipboard."
        }

        throw "$Label did not create expected output '$ExpectedOutput'.$detail"
    }

    return $proc
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
    throw "Could not locate RoboQuest\Content\Data\DT_WeaponAffix.uasset under the legacy extraction."
}

$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$workRoot = Join-Path $OutputDir "work"
$stageRoot = Join-Path $OutputDir "staging"
$releaseRoot = Join-Path $OutputDir "release"
$jsonRoot = Join-Path $workRoot "json"
$reportRoot = Join-Path $workRoot "reports"

if (Test-Path -LiteralPath $OutputDir) {
    Remove-Item -Recurse -Force $OutputDir
}
New-Item -ItemType Directory -Force -Path $jsonRoot, $reportRoot, $releaseRoot | Out-Null

$targetRelative = "Data\DT_WeaponAffix"
$sourceUasset = Join-Path $contentRoot ($targetRelative + ".uasset")
$sourceUexp = Join-Path $contentRoot ($targetRelative + ".uexp")

$stageBase = Join-Path $stageRoot ("RoboQuest\Content\" + $targetRelative)
New-Item -ItemType Directory -Force -Path ([System.IO.Path]::GetDirectoryName($stageBase)) | Out-Null

$cleanRoundtripBase = Join-Path $workRoot "clean-roundtrip\RoboQuest\Content\Data\DT_WeaponAffix"
New-Item -ItemType Directory -Force -Path ([System.IO.Path]::GetDirectoryName($cleanRoundtripBase)) | Out-Null

$sourceJson = Join-Path $jsonRoot "DT_WeaponAffix.original.json"
$cleanRoundtripJson = Join-Path $jsonRoot "DT_WeaponAffix.clean-roundtrip.json"
$patchedJson = Join-Path $jsonRoot "DT_WeaponAffix.patched.json"
$roundtripJson = Join-Path $jsonRoot "DT_WeaponAffix.roundtrip.json"

$patchReport = Join-Path $reportRoot "phase1-affix-unlocks.json"
$patchSpec = Join-Path $RepoRoot "Source\patches\phase1_affix_unlocks.json"
$patcher = Join-Path $RepoRoot "tools\patch_uassetapi_datatable.py"
$verifier = Join-Path $RepoRoot "tools\verify_uassetapi_patch.py"

Write-Host "1/7 Exporting clean DT_WeaponAffix through UAssetGUI..."
$toJsonArgs = @(
    "tojson",
    ('"' + $sourceUasset + '"'),
    ('"' + $sourceJson + '"'),
    "VER_UE4_26"
)
Invoke-UAssetGUI $toJsonArgs $sourceJson "UAssetGUI clean tojson" | Out-Null

Write-Host "2/7 Proving an unmodified JSON -> cooked package round-trip..."
$cleanFromJsonArgs = @(
    "fromjson",
    ('"' + $sourceJson + '"'),
    ('"' + $cleanRoundtripBase + '.uasset' + '"')
)
Invoke-UAssetGUI $cleanFromJsonArgs ($cleanRoundtripBase + ".uasset") "UAssetGUI clean fromjson" | Out-Null

if ((Test-Path -LiteralPath $sourceUexp) -and -not (Test-Path -LiteralPath ($cleanRoundtripBase + ".uexp"))) {
    throw "Clean source package has a .uexp but UAssetGUI clean round-trip did not create a .uexp."
}

$cleanToJsonArgs = @(
    "tojson",
    ('"' + $cleanRoundtripBase + '.uasset' + '"'),
    ('"' + $cleanRoundtripJson + '"'),
    "VER_UE4_26"
)
Invoke-UAssetGUI $cleanToJsonArgs $cleanRoundtripJson "UAssetGUI clean round-trip tojson" | Out-Null

Write-Host "3/7 Applying Phase 1 declarative patch..."
Invoke-Python @($patcher, $sourceJson, $patchSpec, $patchedJson, "--report", $patchReport)

Write-Host "4/7 Rebuilding patched cooked package..."
$fromJsonArgs = @(
    "fromjson",
    ('"' + $patchedJson + '"'),
    ('"' + $stageBase + '.uasset' + '"')
)
Invoke-UAssetGUI $fromJsonArgs ($stageBase + ".uasset") "UAssetGUI patched fromjson" | Out-Null

if ((Test-Path -LiteralPath $sourceUexp) -and -not (Test-Path -LiteralPath ($stageBase + ".uexp"))) {
    throw "Source package has a .uexp but UAssetGUI did not create a staged .uexp."
}

Write-Host "5/7 Re-exporting staged package for logical round-trip validation..."
$roundtripArgs = @(
    "tojson",
    ('"' + $stageBase + '.uasset' + '"'),
    ('"' + $roundtripJson + '"'),
    "VER_UE4_26"
)
Invoke-UAssetGUI $roundtripArgs $roundtripJson "UAssetGUI patched round-trip tojson" | Out-Null
Invoke-Python @($verifier, $roundtripJson, $patchSpec)

Write-Host "6/7 Packing UE4.26 IoStore containers..."
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

Write-Host "7/7 Writing prototype manifest..."
$manifest = [ordered]@{
    build = "phase1-native-affix-composition"
    generated_utc = [DateTime]::UtcNow.ToString("o")
    source_content_root = $contentRoot
    patch_spec = $patchSpec
    modified_packages = @("RoboQuest/Content/Data/DT_WeaponAffix")
    clean_roundtrip_verified = $true
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
    Write-Host "Installed prototype to $mods"
}

Write-Host ""
Write-Host "Phase 1 prototype build complete:"
Write-Host "  $releaseRoot"
Write-Host ""
Write-Host "This build intentionally does NOT yet make Fragmentation universal or enable raycast Seeker."
