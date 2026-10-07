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

function Get-RoboquestSteamRoots {
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

function Find-RoboquestShippingExe {
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

    foreach ($root in Get-RoboquestSteamRoots) {
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

    # Last-resort targeted search. Avoid whole-drive recursion; only search common
    # game-library roots where Roboquest is plausibly installed.
    foreach ($drive in Get-PSDrive -PSProvider FileSystem -ErrorAction SilentlyContinue) {
        foreach ($root in @(
            (Join-Path $drive.Root "SteamLibrary"),
            (Join-Path $drive.Root "Steam"),
            (Join-Path $drive.Root "Games"),
            (Join-Path $drive.Root "XboxGames"),
            (Join-Path $drive.Root "Program Files (x86)\Steam\steamapps\common"),
            (Join-Path $drive.Root "Program Files\Steam\steamapps\common")
        )) {
            if (-not (Test-Path -LiteralPath $root)) { continue }
            try {
                $found = Get-ChildItem -LiteralPath $root -Filter "RoboQuest-Win64-Shipping.exe" -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
                if ($found) {
                    return [System.IO.Path]::GetFullPath($found.FullName)
                }
            } catch {
            }
        }
    }

    return $null
}

function Get-RoboquestPathCacheFile([string]$RepoRoot) {
    $cacheDir = Join-Path $RepoRoot "handoff\.runtime-cache"
    if (-not (Test-Path -LiteralPath $cacheDir)) {
        New-Item -ItemType Directory -Force -Path $cacheDir | Out-Null
    }
    return (Join-Path $cacheDir "roboquest-shipping-path.txt")
}

function Get-CachedRoboquestShippingExe([string]$RepoRoot) {
    $cacheFile = Get-RoboquestPathCacheFile $RepoRoot
    if (-not (Test-Path -LiteralPath $cacheFile)) { return $null }

    try {
        $candidate = (Get-Content -LiteralPath $cacheFile -Raw).Trim()
        if (-not $candidate) { return $null }
        if (
            (Test-Path -LiteralPath $candidate -PathType Leaf) -and
            ([System.IO.Path]::GetFileName($candidate) -ieq "RoboQuest-Win64-Shipping.exe")
        ) {
            return [System.IO.Path]::GetFullPath($candidate)
        }
    } catch {
    }

    Remove-Item -LiteralPath $cacheFile -Force -ErrorAction SilentlyContinue
    return $null
}

function Save-CachedRoboquestShippingExe([string]$RepoRoot, [string]$GameExePath) {
    if (-not $GameExePath) { return }
    $cacheFile = Get-RoboquestPathCacheFile $RepoRoot
    [System.IO.Path]::GetFullPath($GameExePath) |
        Set-Content -LiteralPath $cacheFile -Encoding UTF8
}

function Get-RunningRoboquestShippingExe {
    foreach ($proc in Get-Process -ErrorAction SilentlyContinue | Where-Object {
        $_.ProcessName -ieq "RoboQuest-Win64-Shipping"
    }) {
        $candidate = $null

        try {
            $candidate = $proc.Path
        } catch {
        }

        if (-not $candidate) {
            try {
                $cim = Get-CimInstance Win32_Process -Filter "ProcessId=$($proc.Id)" -ErrorAction SilentlyContinue
                $candidate = [string]$cim.ExecutablePath
            } catch {
            }
        }

        if (
            $candidate -and
            (Test-Path -LiteralPath $candidate -PathType Leaf) -and
            ([System.IO.Path]::GetFileName($candidate) -ieq "RoboQuest-Win64-Shipping.exe")
        ) {
            return [System.IO.Path]::GetFullPath($candidate)
        }
    }

    return $null
}

function Wait-ForRunningRoboquestShippingExe([int]$TimeoutSeconds = 180) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)

    while ((Get-Date) -lt $deadline) {
        $candidate = Get-RunningRoboquestShippingExe
        if ($candidate) { return $candidate }
        Start-Sleep -Milliseconds 500
    }

    return $null
}

function Wait-ForRoboquestShippingExit([string]$ExpectedPath, [int]$TimeoutSeconds = 300) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)

    while ((Get-Date) -lt $deadline) {
        if (-not (Find-RoboquestShippingProcess $ExpectedPath)) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    }

    return $false
}

function Start-RoboquestDiscoveryLaunch {
    # Prefer Steam when it is installed because app id 692890 is stable.
    try {
        if ((Get-RoboquestSteamRoots).Count -gt 0) {
            Start-Process "steam://rungameid/692890" | Out-Null
            return "steam"
        }
    } catch {
    }

    # Xbox / Microsoft Store and other registered installs generally expose a
    # Start-menu app id even when the install directory itself is protected.
    try {
        $app = Get-StartApps -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match "^Robo\s*Quest$|Roboquest" } |
            Select-Object -First 1

        if ($app -and $app.AppID) {
            Start-Process ("shell:AppsFolder\" + $app.AppID) | Out-Null
            return "start-menu"
        }
    } catch {
    }

    return $null
}

function Resolve-RoboquestShippingExeInteractive([string]$RepoRoot) {
    $cached = Get-CachedRoboquestShippingExe $RepoRoot
    if ($cached) {
        Write-Host "Using cached Roboquest shipping executable:"
        Write-Host "  $cached"
        return $cached
    }

    $static = Find-RoboquestShippingExe
    if ($static) {
        Save-CachedRoboquestShippingExe $RepoRoot $static
        return $static
    }

    Write-Host ""
    Write-Host "Static install discovery could not locate Roboquest."
    Write-Host "Starting a one-time normal game launch so Momentum can capture the"
    Write-Host "real RoboQuest-Win64-Shipping.exe path from the running process."

    $launchMethod = Start-RoboquestDiscoveryLaunch
    if ($launchMethod) {
        Write-Host "Normal discovery launch requested via $launchMethod."
    } else {
        Write-Host ""
        Write-Host "Launch Roboquest normally from Steam/Xbox now."
    }

    Write-Host "Waiting up to 3 minutes for RoboQuest-Win64-Shipping.exe..."
    $captured = Wait-ForRunningRoboquestShippingExe -TimeoutSeconds 180

    if (-not $captured) {
        throw @"
Could not observe RoboQuest-Win64-Shipping.exe within 3 minutes.

Launch Roboquest normally and rerun this command, or pass -GameExePath explicitly.
"@
    }

    Save-CachedRoboquestShippingExe $RepoRoot $captured

    Write-Host ""
    Write-Host "Captured and cached the shipping executable:"
    Write-Host "  $captured"
    Write-Host ""
    Write-Host "Quit this normal Roboquest launch now."
    Write-Host "The probe is waiting and will continue automatically after the game exits."

    if (-not (Wait-ForRoboquestShippingExit $captured -TimeoutSeconds 300)) {
        throw "Roboquest did not exit within 5 minutes. Quit the game and rerun the probe."
    }

    return $captured
}

function Set-ProbeIniValue([string]$Path,[string]$Section,[string]$Key,[string]$Value) {
    $lines = @(Get-Content -LiteralPath $Path); $header = "[$Section]"; $s = -1
    for ($i=0;$i -lt $lines.Count;$i++) { if ($lines[$i].Trim() -ieq $header) { $s=$i; break } }
    if ($s -lt 0) { $lines += ""; $lines += $header; $lines += "$Key = $Value"; Set-Content $Path $lines -Encoding UTF8; return }
    $end=$lines.Count; for ($i=$s+1;$i -lt $lines.Count;$i++) { if ($lines[$i].Trim() -match '^\[.+\]$') { $end=$i; break } }
    $pattern='^\s*'+[regex]::Escape($Key)+'\s*='
    for ($i=$s+1;$i -lt $end;$i++) { if ($lines[$i] -match $pattern) { $lines[$i]="$Key = $Value"; Set-Content $Path $lines -Encoding UTF8; return } }
    $before=@($lines[0..$s]); $after=if($s+1 -lt $lines.Count){@($lines[($s+1)..($lines.Count-1)])}else{@()}
    Set-Content $Path @($before+"$Key = $Value"+$after) -Encoding UTF8
}

function Invoke-ProbePython([string[]]$Arguments) {
    if (Get-Command python -ErrorAction SilentlyContinue) { & python @Arguments | Out-Host; return $(if($null -eq $LASTEXITCODE){0}else{[int]$LASTEXITCODE}) }
    if (Get-Command py -ErrorAction SilentlyContinue) { & py -3 @Arguments | Out-Host; return $(if($null -eq $LASTEXITCODE){0}else{[int]$LASTEXITCODE}) }
    throw "Python 3 was not found on PATH."
}

function Find-RoboquestShippingProcess([string]$ExpectedPath) {
    foreach ($proc in Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -ieq "RoboQuest-Win64-Shipping" }) {
        try { if ([System.IO.Path]::GetFullPath($proc.Path) -ieq $ExpectedPath) { return $proc } } catch {}
    }
    return $null
}
