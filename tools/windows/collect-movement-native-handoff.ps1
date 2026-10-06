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

function Resolve-RoboquestExeFromRoot([string]$Root) {
    if (-not $Root) { return $null }

    # Never accept the small RoboQuest.exe launcher as the target. If a file path
    # was supplied (for example from a running process), only accept it directly
    # when it is the actual shipping executable; otherwise search from its folder.
    if (Test-Path -LiteralPath $Root -PathType Leaf) {
        if ([System.IO.Path]::GetFileName($Root) -ieq "RoboQuest-Win64-Shipping.exe") {
            return [System.IO.Path]::GetFullPath($Root)
        }
        $Root = Split-Path -Parent $Root
    }

    $candidates = @(
        (Join-Path $Root "RoboQuest-Win64-Shipping.exe"),
        (Join-Path $Root "RoboQuest\Binaries\Win64\RoboQuest-Win64-Shipping.exe"),
        (Join-Path $Root "Content\RoboQuest\Binaries\Win64\RoboQuest-Win64-Shipping.exe"),
        (Join-Path $Root "Roboquest\RoboQuest\Binaries\Win64\RoboQuest-Win64-Shipping.exe"),
        (Join-Path $Root "RoboQuest\RoboQuest\Binaries\Win64\RoboQuest-Win64-Shipping.exe"),
        (Join-Path $Root "Roboquest\Content\RoboQuest\Binaries\Win64\RoboQuest-Win64-Shipping.exe"),
        (Join-Path $Root "RoboQuest\Content\RoboQuest\Binaries\Win64\RoboQuest-Win64-Shipping.exe")
    )

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return [System.IO.Path]::GetFullPath($candidate)
        }
    }
    return $null
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

    $pf86 = [Environment]::GetFolderPath([Environment+SpecialFolder]::ProgramFilesX86)
    $pf64 = [Environment]::GetFolderPath([Environment+SpecialFolder]::ProgramFiles)
    foreach ($fallback in @(
        (Join-Path $pf86 "Steam"),
        (Join-Path $pf64 "Steam")
    )) {
        if ($fallback) {
            Add-UniquePath $roots $fallback
        }
    }

    foreach ($drive in Get-PSDrive -PSProvider FileSystem -ErrorAction SilentlyContinue) {
        foreach ($candidate in @(
            (Join-Path $drive.Root "Steam"),
            (Join-Path $drive.Root "SteamLibrary"),
            (Join-Path $drive.Root "Games\Steam"),
            (Join-Path $drive.Root "Program Files (x86)\Steam"),
            (Join-Path $drive.Root "Program Files\Steam")
        )) {
            if (Test-Path -LiteralPath $candidate) {
                Add-UniquePath $roots $candidate
            }
        }
    }

    $expanded = New-Object System.Collections.Generic.List[string]
    foreach ($root in $roots) {
        if (-not (Test-Path -LiteralPath $root)) { continue }
        Add-UniquePath $expanded $root

        $libraries = Join-Path $root "steamapps\libraryfolders.vdf"
        if (-not (Test-Path -LiteralPath $libraries)) { continue }

        foreach ($line in Get-Content -LiteralPath $libraries -ErrorAction SilentlyContinue) {
            if ($line -notmatch '"path"\s+"(.+)"') { continue }
            $candidate = $Matches[1] -replace '\\\\', '\'
            Add-UniquePath $expanded $candidate
        }
    }

    return $expanded
}

function Get-UninstallInstallRoots {
    $roots = New-Object System.Collections.Generic.List[string]
    $uninstallRoots = @(
        "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )

    foreach ($pattern in $uninstallRoots) {
        try {
            foreach ($app in Get-ItemProperty $pattern -ErrorAction SilentlyContinue) {
                if ([string]$app.DisplayName -notmatch "Robo\s*Quest|Roboquest") { continue }
                Add-UniquePath $roots ([string]$app.InstallLocation)
            }
        } catch {
        }
    }
    return $roots
}

function Find-RoboquestExe {
    try {
        foreach ($proc in Get-Process -ErrorAction SilentlyContinue | Where-Object {
            $_.ProcessName -match "^RoboQuest|Roboquest"
        }) {
            try {
                $path = $proc.Path
                if ($path -and (Test-Path -LiteralPath $path -PathType Leaf)) {
                    $resolved = Resolve-RoboquestExeFromRoot $path
                    if ($resolved) { return $resolved }

                    # Some launchers sit one directory above the game content.
                    $parent = Split-Path -Parent $path
                    try {
                        $found = Get-ChildItem -LiteralPath $parent -Filter "RoboQuest-Win64-Shipping.exe" -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
                        if ($found) {
                            return [System.IO.Path]::GetFullPath($found.FullName)
                        }
                    } catch {
                    }
                }
            } catch {
            }
        }
    } catch {
    }

    foreach ($root in Get-SteamRoots) {
        $steamApps = Join-Path $root "steamapps"
        $manifest = Join-Path $steamApps "appmanifest_692890.acf"
        $installDir = "Roboquest"

        if (Test-Path -LiteralPath $manifest) {
            foreach ($line in Get-Content -LiteralPath $manifest -ErrorAction SilentlyContinue) {
                if ($line -match '"installdir"\s+"(.+)"') {
                    $installDir = $Matches[1]
                    break
                }
            }
        }

        foreach ($candidateRoot in @(
            (Join-Path $steamApps "common\$installDir"),
            (Join-Path $steamApps "common\Roboquest"),
            (Join-Path $steamApps "common\RoboQuest")
        )) {
            $resolved = Resolve-RoboquestExeFromRoot $candidateRoot
            if ($resolved) { return $resolved }
        }
    }

    foreach ($root in Get-UninstallInstallRoots) {
        $resolved = Resolve-RoboquestExeFromRoot $root
        if ($resolved) { return $resolved }
    }

    foreach ($drive in Get-PSDrive -PSProvider FileSystem -ErrorAction SilentlyContinue) {
        $xboxRoot = Join-Path $drive.Root "XboxGames"
        if (-not (Test-Path -LiteralPath $xboxRoot)) { continue }

        foreach ($namedRoot in @(
            (Join-Path $xboxRoot "Roboquest"),
            (Join-Path $xboxRoot "RoboQuest")
        )) {
            $resolved = Resolve-RoboquestExeFromRoot $namedRoot
            if ($resolved) { return $resolved }
        }

        try {
            $found = Get-ChildItem -LiteralPath $xboxRoot -Filter "RoboQuest-Win64-Shipping.exe" -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($found) {
                return [System.IO.Path]::GetFullPath($found.FullName)
            }
        } catch {
        }
    }

    try {
        foreach ($pkg in Get-AppxPackage -ErrorAction SilentlyContinue | Where-Object {
            $_.Name -match "Robo\s*Quest|Roboquest" -or
            $_.PackageFullName -match "Robo\s*Quest|Roboquest"
        }) {
            $resolved = Resolve-RoboquestExeFromRoot ([string]$pkg.InstallLocation)
            if ($resolved) { return $resolved }

            try {
                $found = Get-ChildItem -LiteralPath $pkg.InstallLocation -Filter "RoboQuest-Win64-Shipping.exe" -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
                if ($found) {
                    return [System.IO.Path]::GetFullPath($found.FullName)
                }
            } catch {
            }
        }
    } catch {
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

The locator checked:
  - a currently running Roboquest process;
  - Steam registry + libraryfolders.vdf + common alternate-drive Steam roots;
  - Windows uninstall InstallLocation metadata;
  - XboxGames folders on all filesystem drives;
  - matching AppX/MSIX package locations.

If Roboquest is installed somewhere unusual, rerun once with the executable path:
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
