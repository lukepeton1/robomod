[CmdletBinding()]
param(
    [string]$GameExePath = "",
    [string]$JmapPath = "",
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $scriptRoot "..\.."))
. (Join-Path $scriptRoot "momentum-runtime-probe-common.ps1")

if (-not $OutputDir) {
    $OutputDir = Join-Path $repoRoot "handoff\movement-thunk"
}

if (-not $GameExePath) {
    $GameExePath = Get-CachedRoboquestShippingExe $repoRoot
}
if (-not $GameExePath) {
    $GameExePath = Find-RoboquestShippingExe
}
if (-not $GameExePath) {
    throw "Could not resolve the cached RoboQuest-Win64-Shipping.exe path. Rerun the runtime probe once."
}
$GameExePath = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $GameExePath).Path)

if (-not $JmapPath) {
    $runtimeDir = Join-Path $repoRoot "handoff\movement-runtime"
    $jmap = Get-ChildItem -LiteralPath $runtimeDir -Filter "*.jmap" -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($jmap) {
        $JmapPath = $jmap.FullName
    }
}
if (-not $JmapPath -or -not (Test-Path -LiteralPath $JmapPath -PathType Leaf)) {
    throw "Could not locate a runtime JMAP under handoff\movement-runtime. Rerun the runtime probe once."
}
$JmapPath = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $JmapPath).Path)

if (Test-Path -LiteralPath $OutputDir) {
    Remove-Item -LiteralPath $OutputDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$surface = Join-Path $OutputDir "movement-runtime-surface.json"
$thunk = Join-Path $OutputDir "calcvelocity-thunk.json"

$code = Invoke-ProbePython @(
    (Join-Path $repoRoot "tools\analyze_movement_jmap.py"),
    $JmapPath,
    "--output", $surface
)
if ($code -ne 0) {
    throw "Movement JMAP analyzer failed with exit code $code."
}

$code = Invoke-ProbePython @(
    (Join-Path $repoRoot "tools\analyze_calcvelocity_thunk.py"),
    $GameExePath,
    $JmapPath,
    "--output", $thunk
)
if ($code -ne 0) {
    throw "CalcVelocity thunk analyzer failed with exit code $code."
}

$manifest = [ordered]@{
    schema_version = 1
    generated_utc = [DateTime]::UtcNow.ToString("o")
    executable_filename = [System.IO.Path]::GetFileName($GameExePath)
    executable_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $GameExePath).Hash.ToLowerInvariant()
    jmap_filename = [System.IO.Path]::GetFileName($JmapPath)
    jmap_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $JmapPath).Hash.ToLowerInvariant()
    contains_game_executable = $false
    contains_jmap = $false
}
$manifest |
    ConvertTo-Json -Depth 6 |
    Set-Content -LiteralPath (Join-Path $OutputDir "movement-thunk-manifest.json") -Encoding UTF8

$zipPath = "$OutputDir.zip"
if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}
Compress-Archive -Path (Join-Path $OutputDir "*") -DestinationPath $zipPath -CompressionLevel Optimal

Write-Host ""
Write-Host "Momentum CalcVelocity handoff ZIP:"
Write-Host "  $zipPath"
Write-Host ""
Write-Host "The ZIP contains only distilled reflection/thunk metadata and short instruction snippets."
