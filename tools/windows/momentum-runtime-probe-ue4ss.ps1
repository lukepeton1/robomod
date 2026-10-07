function Get-ProbeUE4SSBuild([string]$Scratch) {
    $api = "https://api.github.com/repos/UE4SS-RE/RE-UE4SS/releases/tags/experimental-latest"
    $release = Invoke-RestMethod -Uri $api -Headers @{"User-Agent"="Roboquest-Momentum-Probe"}
    $asset = $release.assets | Where-Object { $_.name -like "zDEV-UE4SS_*.zip" } | Select-Object -First 1
    if (-not $asset) { throw "UE4SS experimental-latest has no zDEV asset." }
    $zip=Join-Path $Scratch "ue4ss-zdev.zip"; $extract=Join-Path $Scratch "ue4ss-package"
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zip -Headers @{"User-Agent"="Roboquest-Momentum-Probe"}
    $hash=(Get-FileHash -Algorithm SHA256 -LiteralPath $zip).Hash.ToLowerInvariant()
    if ($asset.digest -and [string]$asset.digest -match '^sha256:(.+)$' -and $hash -ne $Matches[1].ToLowerInvariant()) { throw "UE4SS archive SHA-256 mismatch." }
    Expand-Archive -LiteralPath $zip -DestinationPath $extract -Force
    $dwm=Get-ChildItem $extract -Filter "dwmapi.dll" -File -Recurse | Select-Object -First 1
    $dir=Get-ChildItem $extract -Directory -Filter "ue4ss" -Recurse | Select-Object -First 1
    if (-not $dwm -or -not $dir) { throw "Unexpected UE4SS zDEV archive layout." }
    return [pscustomobject]@{release=$release;asset=$asset;sha256=$hash;dwm=$dwm.FullName;ue4ss=$dir.FullName}
}

function Stage-MomentumUE4SSProbe([string]$Win64,$Build) {
    $backup = Join-Path $Win64 ".momentum-runtime-probe-backup"
    $state = [ordered]@{
        original_dwmapi = $false
        original_ue4ss = $false
        original_xinput = $false
    }

    $stage = [pscustomobject]@{
        backup = $backup
        dwm = (Join-Path $Win64 "dwmapi.dll")
        ue4ss = (Join-Path $Win64 "ue4ss")
        xinput = (Join-Path $Win64 "xinput1_3.dll")
        state = $state
    }

    New-Item -ItemType Directory -Force -Path $backup | Out-Null

    try {
        if (Test-Path -LiteralPath $stage.dwm) {
            Move-Item -LiteralPath $stage.dwm -Destination (Join-Path $backup "dwmapi.dll") -Force
            $state.original_dwmapi = $true
        }
        if (Test-Path -LiteralPath $stage.ue4ss) {
            Move-Item -LiteralPath $stage.ue4ss -Destination (Join-Path $backup "ue4ss") -Force
            $state.original_ue4ss = $true
        }
        if (Test-Path -LiteralPath $stage.xinput) {
            Move-Item -LiteralPath $stage.xinput -Destination (Join-Path $backup "xinput1_3.dll") -Force
            $state.original_xinput = $true
        }

        $state |
            ConvertTo-Json |
            Set-Content -LiteralPath (Join-Path $backup "state.json") -Encoding UTF8

        Copy-Item -LiteralPath $Build.dwm -Destination $stage.dwm -Force
        Copy-Item -LiteralPath $Build.ue4ss -Destination $stage.ue4ss -Recurse -Force
        return $stage
    } catch {
        $message = $_.Exception.Message
        try {
            Restore-MomentumUE4SSProbe $stage
        } catch {
        }
        throw "Failed to stage the UE4SS runtime probe in '$Win64': $message"
    }
}

function Restore-MomentumUE4SSProbe($Stage) {
    if(-not $Stage -or -not (Test-Path $Stage.backup)){return}
    Remove-Item $Stage.dwm -Force -ErrorAction SilentlyContinue; Remove-Item $Stage.ue4ss -Recurse -Force -ErrorAction SilentlyContinue
    if($Stage.state.original_dwmapi -and (Test-Path (Join-Path $Stage.backup "dwmapi.dll"))){Move-Item (Join-Path $Stage.backup "dwmapi.dll") $Stage.dwm -Force}
    if($Stage.state.original_ue4ss -and (Test-Path (Join-Path $Stage.backup "ue4ss"))){Move-Item (Join-Path $Stage.backup "ue4ss") $Stage.ue4ss -Force}
    if($Stage.state.original_xinput -and (Test-Path (Join-Path $Stage.backup "xinput1_3.dll"))){Move-Item (Join-Path $Stage.backup "xinput1_3.dll") $Stage.xinput -Force}
    Remove-Item $Stage.backup -Recurse -Force -ErrorAction SilentlyContinue
}

function Configure-MomentumUE4SSProbe([string]$Ue4ssDir) {
    $settings=Join-Path $Ue4ssDir "UE4SS-settings.ini"; if(-not(Test-Path $settings)){throw "UE4SS-settings.ini not found."}
    Set-ProbeIniValue $settings "EngineVersionOverride" "MajorVersion" "4"; Set-ProbeIniValue $settings "EngineVersionOverride" "MinorVersion" "26"
    Set-ProbeIniValue $settings "EngineVersionOverride" "DebugBuild" "false"; Set-ProbeIniValue $settings "General" "bUseUObjectArrayCache" "false"
    Set-ProbeIniValue $settings "Debug" "ConsoleEnabled" "1"; Set-ProbeIniValue $settings "Debug" "GuiConsoleEnabled" "0"; Set-ProbeIniValue $settings "Debug" "GuiConsoleVisible" "0"
    $scripts=Join-Path $Ue4ssDir "Mods\MomentumProbe\Scripts"; New-Item -ItemType Directory -Force -Path $scripts | Out-Null
    $lua=@'
print("[MomentumProbe] loaded")
print("[MomentumProbe] EngineTickAvailable=" .. tostring(EngineTickAvailable))
print("[MomentumProbe] ProcessEventAvailable=" .. tostring(ProcessEventAvailable))

print("[MomentumProbe] starting native-only JMAP dump")
local ok,err=pcall(function()
    DumpJMAP(false, false)
end)

if ok then
    print("[MomentumProbe] JMAP dump call completed")
else
    print("[MomentumProbe] JMAP dump failed: " .. tostring(err))
end
'@
    $luaPath = Join-Path $scripts "main.lua"
    $utf8NoBom = New-Object System.Text.UTF8Encoding -ArgumentList $false
    [System.IO.File]::WriteAllText($luaPath, $lua, $utf8NoBom)
    $mods=Join-Path $Ue4ssDir "Mods\mods.txt"; if(-not(Test-Path $mods)){New-Item -ItemType File -Force -Path $mods|Out-Null}
    $lines=@(Get-Content $mods -ErrorAction SilentlyContinue|Where-Object{$_ -notmatch '^\s*MomentumProbe\s*:'});$lines+="MomentumProbe : 1";Set-Content $mods $lines -Encoding UTF8
}
