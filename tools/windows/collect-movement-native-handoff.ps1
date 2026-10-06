[CmdletBinding()]
param(
    [string]$GameExePath = "",
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $scriptRoot "..\.."))
if (-not $OutputDir) {
    $OutputDir = Join-Path $repoRoot "handoff\movement-native"
}
$scanner = Join-Path $repoRoot "tools\analyze_native_movement_strings.py"

function Add-UniquePath([System.Collections.Generic.List[string]]$List, [string]$Path) {
    if (-not $Path) { return }
    try {
        $full = [System.IO.Path]::GetFullPath($Path)
    } catch {
        return
    }
    if (-not $List.Contains($full)) {
        $List.Add($full)
    }
}

function Get-SteamRoots {
    $roots = New-Object System.Collections.Generic.List[string]

    foreach ($reg in @(
        "HKCU:\Software\Valve\Steam",
        "HKLM:\SOFTWARE\WOW6432Node\Valve\Steam",
        "HKLM:\SOFTWARE\Valve\Steam"
    )) {
        if (-not (Test-Path $reg)) { continue }
        try {
            $props = Get-ItemProperty $reg
            Add-UniquePath $roots $props.SteamPath
            Add-UniquePath $roots $props.InstallPath
        } catch {
        }
    }

    foreach ($fallback in @(
        "${env:ProgramFiles(x86)}\Steam",
        "$env:ProgramFiles\Steam"
    )) {
        if ($fallback) {
            Add-UniquePath $roots $fallback
        }
    }

    $expanded = New-Object System.Collections.Generic.List[string]
    foreach ($root in $roots) {
        if (-not (Test-Path -LiteralPath $root)) { continue }
        Add-UniquePath $expanded $root

        $libraries = Join-Path $root "steamapps\libraryfolders.vdf"
        if (-not (Test-Path -LiteralPath $libraries)) { continue }

        foreach ($line in Get-Content -LiteralPath $libraries) {
            if ($line -notmatch '"path"\s+"(.+)"') { continue }
            $candidate = $Matches[1] -replace '\\\\', '\'
            Add-UniquePath $expanded $candidate
        }
    }

    return $expanded
}

function Find-RoboquestExe {
    $steamRoots = Get-SteamRoots
    foreach ($root in $steamRoots) {
        $steamApps = Join-Path $root "steamapps"
        # Roboquest Steam app ID: 692890.
        $manifest = Join-Path $steamApps "appmanifest_692890.acf"
        $installDir = "Roboquest"

        if (Test-Path -LiteralPath $manifest) {
            foreach ($line in Get-Content -LiteralPath $manifest) {
                if ($line -match '"installdir"\s+"(.+)"') {
                    $installDir = $Matches[1]
                    break
                }
            }
        }

        $candidate = Join-Path $steamApps "common\$installDir\RoboQuest\Binaries\Win64\RoboQuest-Win64-Shipping.exe"
        if (Test-Path -LiteralPath $candidate) {
            return [System.IO.Path]::GetFullPath($candidate)
        }
    }

    foreach ($candidate in @(
        "C:\Program Files (x86)\Steam\steamapps\common\Roboquest\RoboQuest\Binaries\Win64\RoboQuest-Win64-Shipping.exe",
        "C:\Program Files\Steam\steamapps\common\Roboquest\RoboQuest\Binaries\Win64\RoboQuest-Win64-Shipping.exe"
    )) {
        if (Test-Path -LiteralPath $candidate) {
            return [System.IO.Path]::GetFullPath($candidate)
        }
    }

    return $null
}

function Invoke-Python([string[]]$Arguments) {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        & python @Arguments | Out-Host
        if ($null -eq $LASTEXITCODE) { return 0 }
        return [int]$LASTEXITCODE
    }
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        & py -3 @Arguments | Out-Host
        if ($null -eq $LASTEXITCODE) { return 0 }
        return [int]$LASTEXITCODE
    }
    throw "Python 3 was not found on PATH."
}

if (-not $GameExePath) {
    $GameExePath = Find-RoboquestExe
}
if (-not $GameExePath -or -not (Test-Path -LiteralPath $GameExePath)) {
    throw @"
Could not locate RoboQuest-Win64-Shipping.exe automatically.
Rerun with:
  tools\windows\collect-movement-native-handoff.cmd -GameExePath "C:\path\to\RoboQuest-Win64-Shipping.exe"
"@
}

$GameExePath = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $GameExePath).Path)
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)

if (Test-Path -LiteralPath $OutputDir) {
    Remove-Item -LiteralPath $OutputDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

Write-Host "=== Roboquest Momentum: native movement probe ==="
Write-Host "Executable:"
Write-Host "  $GameExePath"
Write-Host ""

$outJson = Join-Path $OutputDir "native-movement-strings.json"
$code = Invoke-Python @(
    $scanner,
    $GameExePath,
    "--output", $outJson
)
if ($code -ne 0) {
    throw "Native movement scanner failed with exit code $code."
}

$file = Get-Item -LiteralPath $GameExePath
$version = $file.VersionInfo
$manifest = [ordered]@{
    schema_version = 1
    generated_utc = [DateTime]::UtcNow.ToString("o")
    executable_filename = $file.Name
    executable_bytes = $file.Length
    executable_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $GameExePath).Hash.ToLowerInvariant()
    file_version = $version.FileVersion
    product_version = $version.ProductVersion
    product_name = $version.ProductName
    scanner = "tools/analyze_native_movement_strings.py"
    contains_game_binary = $false
}
$manifestPath = Join-Path $OutputDir "native-handoff-manifest.json"
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

$zipPath = "$OutputDir.zip"
if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}
Compress-Archive -Path (Join-Path $OutputDir "*") -DestinationPath $zipPath -CompressionLevel Optimal

Write-Host ""
Write-Host "Native movement handoff ZIP:"
Write-Host "  $zipPath"
Write-Host ""
Write-Host "The ZIP contains hashes/metadata/string evidence only; it does not contain the game executable."
exit 0
