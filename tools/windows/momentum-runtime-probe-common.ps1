function Resolve-RoboquestExeFromRoot([string]$Root) {
    if (-not $Root) { return $null }
    if (Test-Path -LiteralPath $Root -PathType Leaf) {
        if ([System.IO.Path]::GetFileName($Root) -ieq "RoboQuest-Win64-Shipping.exe") { return [System.IO.Path]::GetFullPath($Root) }
        $Root = Split-Path -Parent $Root
    }
    foreach ($candidate in @(
        (Join-Path $Root "RoboQuest-Win64-Shipping.exe"),
        (Join-Path $Root "RoboQuest\Binaries\Win64\RoboQuest-Win64-Shipping.exe"),
        (Join-Path $Root "Content\RoboQuest\Binaries\Win64\RoboQuest-Win64-Shipping.exe"),
        (Join-Path $Root "Roboquest\RoboQuest\Binaries\Win64\RoboQuest-Win64-Shipping.exe"),
        (Join-Path $Root "RoboQuest\RoboQuest\Binaries\Win64\RoboQuest-Win64-Shipping.exe"),
        (Join-Path $Root "Roboquest\Content\RoboQuest\Binaries\Win64\RoboQuest-Win64-Shipping.exe"),
        (Join-Path $Root "RoboQuest\Content\RoboQuest\Binaries\Win64\RoboQuest-Win64-Shipping.exe")
    )) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return [System.IO.Path]::GetFullPath($candidate) }
    }
    return $null
}

function Add-UniquePath([System.Collections.Generic.List[string]]$List, [string]$Path) {
    if (-not $Path) { return }
    try { $full = [System.IO.Path]::GetFullPath($Path) } catch { return }
    if (-not $List.Contains($full)) { $List.Add($full) }
}

function Get-RoboquestSteamRoots {
    $roots = New-Object System.Collections.Generic.List[string]
    foreach ($reg in @("HKCU:\Software\Valve\Steam","HKLM:\SOFTWARE\WOW6432Node\Valve\Steam","HKLM:\SOFTWARE\Valve\Steam")) {
        if (-not (Test-Path $reg)) { continue }
        try {
            $props = Get-ItemProperty $reg
            Add-UniquePath $roots $props.SteamPath
            Add-UniquePath $roots $props.InstallPath
        } catch {}
    }
    foreach ($drive in Get-PSDrive -PSProvider FileSystem -ErrorAction SilentlyContinue) {
        foreach ($candidate in @(
            (Join-Path $drive.Root "Steam"),(Join-Path $drive.Root "SteamLibrary"),(Join-Path $drive.Root "Games\Steam"),
            (Join-Path $drive.Root "Program Files (x86)\Steam"),(Join-Path $drive.Root "Program Files\Steam")
        )) { if (Test-Path -LiteralPath $candidate) { Add-UniquePath $roots $candidate } }
    }
    $expanded = New-Object System.Collections.Generic.List[string]
    foreach ($root in $roots) {
        if (-not (Test-Path -LiteralPath $root)) { continue }
        Add-UniquePath $expanded $root
        $vdf = Join-Path $root "steamapps\libraryfolders.vdf"
        if (-not (Test-Path -LiteralPath $vdf)) { continue }
        foreach ($line in Get-Content -LiteralPath $vdf -ErrorAction SilentlyContinue) {
            if ($line -match '"path"\s+"(.+)"') { Add-UniquePath $expanded ($Matches[1] -replace '\\\\','\') }
        }
    }
    return $expanded
}

function Find-RoboquestShippingExe {
    foreach ($proc in Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -match "^RoboQuest|Roboquest" }) {
        try { $r = Resolve-RoboquestExeFromRoot $proc.Path; if ($r) { return $r } } catch {}
    }
    foreach ($root in Get-RoboquestSteamRoots) {
        $apps = Join-Path $root "steamapps"; $manifest = Join-Path $apps "appmanifest_692890.acf"; $dir = "Roboquest"
        if (Test-Path -LiteralPath $manifest) {
            foreach ($line in Get-Content -LiteralPath $manifest -ErrorAction SilentlyContinue) {
                if ($line -match '"installdir"\s+"(.+)"') { $dir = $Matches[1]; break }
            }
        }
        foreach ($candidate in @((Join-Path $apps "common\$dir"),(Join-Path $apps "common\Roboquest"),(Join-Path $apps "common\RoboQuest"))) {
            $r = Resolve-RoboquestExeFromRoot $candidate; if ($r) { return $r }
        }
    }
    foreach ($drive in Get-PSDrive -PSProvider FileSystem -ErrorAction SilentlyContinue) {
        $xbox = Join-Path $drive.Root "XboxGames"; if (-not (Test-Path -LiteralPath $xbox)) { continue }
        try {
            $found = Get-ChildItem -LiteralPath $xbox -Filter "RoboQuest-Win64-Shipping.exe" -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($found) { return [System.IO.Path]::GetFullPath($found.FullName) }
        } catch {}
    }
    return $null
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
