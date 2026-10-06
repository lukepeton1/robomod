[CmdletBinding()]
param(
    [string]$ExtractRoot = "",
    [string]$UAssetGUIPath = "",
    [string]$OutputDir = "",
    [switch]$SkipJson,
    [switch]$NoZip
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $scriptRoot "..\.."))
$rqRoot = [System.IO.Path]::GetFullPath((Join-Path $repoRoot ".."))

if (-not $ExtractRoot) {
    $ExtractRoot = Join-Path $rqRoot "LegacyExtract"
}
if (-not $UAssetGUIPath) {
    $UAssetGUIPath = Join-Path $rqRoot "UAssetGUI\UAssetGUI.exe"
}
if (-not $OutputDir) {
    $OutputDir = Join-Path $repoRoot "handoff\movement-assets"
}

$manifestPath = Join-Path $repoRoot "Source\manifests\movement_patch_targets.txt"
$collector = Join-Path $repoRoot "tools\windows\collect-legacy-handoff.ps1"
$analyzer = Join-Path $repoRoot "tools\analyze_movement_seams.py"
$validator = Join-Path $repoRoot "tools\validate_handoff.py"
$vanillaRoot = Join-Path $repoRoot "vanilla-json\RoboQuest\Content"

if (-not (Test-Path -LiteralPath $ExtractRoot)) {
    throw "LegacyExtract was not found at '$ExtractRoot'. Pass -ExtractRoot or place it beside the robomod repository."
}
if (-not $SkipJson -and -not (Test-Path -LiteralPath $UAssetGUIPath)) {
    throw "UAssetGUI.exe was not found at '$UAssetGUIPath'. Pass -UAssetGUIPath or place UAssetGUI beside the robomod repository."
}

$collectorParams = @{
    ExtractRoot = $ExtractRoot
    ManifestPath = $manifestPath
    OutputDir = $OutputDir
    NoZip = $true
}
if ($SkipJson) {
    $collectorParams["SkipJson"] = $true
} else {
    $collectorParams["UAssetGUIPath"] = $UAssetGUIPath
}

Write-Host "=== Roboquest Momentum: collect movement handoff ==="
& $collector @collectorParams
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

function Invoke-Python([string[]]$Arguments) {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        & python @Arguments
        return $LASTEXITCODE
    }
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        & py -3 @Arguments
        return $LASTEXITCODE
    }
    throw "Python 3 was not found on PATH."
}

if (-not $SkipJson) {
    Write-Host ""
    Write-Host "=== Validate hashes / UAssetAPI decode coverage ==="
    $validationCode = Invoke-Python @($validator, $OutputDir)
    if ($validationCode -ne 0) {
        Write-Warning "Generic handoff validation reported raw-bytecode or decode issues. The movement archive will still be produced because those failures are useful reverse-engineering evidence."
    }
}

Write-Host ""
Write-Host "=== Analyze movement seams ==="
$seamsOut = Join-Path $OutputDir "movement-seams.json"
$compatOut = Join-Path $OutputDir "movement-compatibility.json"
$analyzeArgs = @(
    $analyzer,
    "--vanilla-root", $vanillaRoot,
    "--manifest", $manifestPath,
    "--handoff", $OutputDir,
    "--output", $seamsOut,
    "--compat-output", $compatOut
)
$analysisCode = Invoke-Python $analyzeArgs
if ($analysisCode -ne 0) {
    throw "Movement seam analyzer failed with exit code $analysisCode."
}

if (-not $NoZip) {
    $zipPath = "$OutputDir.zip"
    if (Test-Path -LiteralPath $zipPath) {
        Remove-Item -LiteralPath $zipPath -Force
    }
    Compress-Archive -Path (Join-Path $OutputDir "*") -DestinationPath $zipPath -CompressionLevel Optimal
    Write-Host ""
    Write-Host "Movement handoff ZIP:"
    Write-Host "  $zipPath"
}

Write-Host ""
Write-Host "Movement seam analysis:"
Write-Host "  $seamsOut"
Write-Host "Compatibility catalog:"
Write-Host "  $compatOut"
exit 0
