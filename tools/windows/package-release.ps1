[CmdletBinding()]
param(
    [string]$RepoRoot = "",
    [string]$BuildReleaseDir = "",
    [string]$Version = "",
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not $RepoRoot) {
    $RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $scriptRoot "..\.."))
}
if (-not $BuildReleaseDir) {
    $BuildReleaseDir = Join-Path $RepoRoot "build\weapon-foundry\release"
}
if (-not $OutputDir) {
    $OutputDir = Join-Path $RepoRoot "dist"
}
if (-not $Version) {
    $versionFile = Join-Path $RepoRoot "VERSION"
    if (-not (Test-Path -LiteralPath $versionFile)) {
        throw "VERSION file not found and -Version was not supplied."
    }
    $Version = (Get-Content -LiteralPath $versionFile -Raw).Trim()
    if (-not $Version) { throw "VERSION file is empty." }
}

$required = @(
    "WeaponFoundry_P.pak",
    "WeaponFoundry_P.ucas",
    "WeaponFoundry_P.utoc"
)
foreach ($name in $required) {
    $path = Join-Path $BuildReleaseDir $name
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Missing production build artifact: $path. Run build-weapon-foundry.ps1 first."
    }
}

$packageName = "Roboquest_WeaponFoundry_v$Version"
$stage = Join-Path $OutputDir $packageName
$zip = Join-Path $OutputDir ($packageName + ".zip")

if (Test-Path -LiteralPath $stage) { Remove-Item -Recurse -Force $stage }
if (Test-Path -LiteralPath $zip) { Remove-Item -Force $zip }

$install = Join-Path $stage "Install"
$source = Join-Path $stage "Source"
$docs = Join-Path $stage "Docs"
New-Item -ItemType Directory -Force -Path $install, $source, $docs | Out-Null

foreach ($name in $required) {
    Copy-Item -LiteralPath (Join-Path $BuildReleaseDir $name) -Destination (Join-Path $install $name)
}
$manifest = Join-Path $BuildReleaseDir "weapon-foundry-manifest.json"
if (Test-Path -LiteralPath $manifest) {
    Copy-Item -LiteralPath $manifest -Destination (Join-Path $install "weapon-foundry-manifest.json")
}

Copy-Item -LiteralPath (Join-Path $RepoRoot "packaging\install.cmd") -Destination (Join-Path $install "install.cmd")
Copy-Item -LiteralPath (Join-Path $RepoRoot "packaging\uninstall.cmd") -Destination (Join-Path $install "uninstall.cmd")

$sourceFiles = @(
    "Source\composition\composition_rules.json",
    "Source\grafting\transfer_policy.json",
    "Source\grafting\graft_transaction.json",
    "Source\manifests\production_packages.json",
    "Source\patches\weapon_foundry_core.json",
    "Source\patches\weapon_foundry_mods.json",
    "Source\patches\foundry_merchant.json",
    "tools\patch_uassetapi_datatable.py",
    "tools\verify_uassetapi_patch.py",
    "tools\patch_fragmentation_bytecode.py",
    "tools\patch_homing_resolver.py",
    "tools\patch_foundry_interactive.py",
    "tools\patch_uassetapi_cdo.py",
    "tools\kismet_layout.py",
    "tools\generate_weapon_foundry_core_patch.py",
    "tools\generate_weapon_foundry_mod_patch.py",
    "tools\generate_transfer_policy.py",
    "tools\generate_foundry_merchant.py",
    "tools\windows\build-weapon-foundry.ps1"
)
foreach ($relative in $sourceFiles) {
    $src = Join-Path $RepoRoot $relative
    if (-not (Test-Path -LiteralPath $src)) { throw "Missing release source file: $src" }
    $dest = Join-Path $source $relative
    New-Item -ItemType Directory -Force -Path ([System.IO.Path]::GetDirectoryName($dest)) | Out-Null
    Copy-Item -LiteralPath $src -Destination $dest
}

Copy-Item -LiteralPath (Join-Path $RepoRoot "Docs\*") -Destination $docs -Recurse
Copy-Item -LiteralPath (Join-Path $RepoRoot "README.md") -Destination (Join-Path $stage "README.md")
Copy-Item -LiteralPath (Join-Path $RepoRoot "VERSION") -Destination (Join-Path $stage "VERSION")

$releaseInfo = [ordered]@{
    name = "Roboquest Weapon Foundry"
    version = $Version
    package = $packageName
    generated_utc = [DateTime]::UtcNow.ToString("o")
    install_files = $required
    vanilla_game_assets_included = $false
}
$releaseInfo | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $stage "release.json") -Encoding UTF8

Compress-Archive -LiteralPath (Join-Path $stage "*") -DestinationPath $zip -CompressionLevel Optimal

Write-Host "Release package:"
Write-Host "  $zip"
