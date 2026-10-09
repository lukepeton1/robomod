function Get-ProbeUE4SSBuild([string]$Scratch, [string]$ArchivePath = "") {
    # experimental-latest is mutable. The exact, formerly validated 1161
    # build was moved to the historical 'experimental' release on 2026-10-09.
    # Do NOT silently upgrade UE4SS during the BP_APlayer_C crash investigation.
    $expectedName = "zDEV-UE4SS_v3.0.1-1161-g6eb3d9bc.zip"
    $expectedSha256 = "580a244bc30352cfd0d0019c4c63726c2bddd5bb04ef91f985df237aa81b06e9"
    $downloadUrl = "https://github.com/UE4SS-RE/RE-UE4SS/releases/download/experimental/$expectedName"
    $release = [pscustomobject]@{ tag_name = "experimental" }
    $asset = [pscustomobject]@{
        name = $expectedName
        browser_download_url = $downloadUrl
        digest = "sha256:$expectedSha256"
        id = 616464965
    }

    New-Item -ItemType Directory -Force -Path $Scratch | Out-Null
    $zip = Join-Path $Scratch "ue4ss-zdev.zip"
    $extract = Join-Path $Scratch "ue4ss-package"

    # Keep a *hash-verified* local copy so future tests are reproducible
    # even when GitHub moves another release tag or is temporarily offline.
    $cacheBase = [Environment]::GetFolderPath("LocalApplicationData")
    if (-not $cacheBase) { $cacheBase = [Environment]::GetFolderPath("UserProfile") }
    $cacheDir = Join-Path $cacheBase "RoboQuest\MomentumCache"
    $cacheZip = Join-Path $cacheDir $expectedName
    $downloads = Join-Path ([Environment]::GetFolderPath("UserProfile")) "Downloads"
    $candidates = @()
    if ($ArchivePath) {
        # An explicit override is exact; reject rather than ignoring mistakes.
        if (-not (Test-Path -LiteralPath $ArchivePath -PathType Leaf)) {
            throw "Specified UE4SS archive was not found: $ArchivePath"
        }
        $candidates += $ArchivePath
    } else {
        $candidates += $cacheZip
        $candidates += (Join-Path $downloads $expectedName)
    }

    $archiveReady = $false
    foreach ($candidate in $candidates) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        $sha = (Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($sha -ne $expectedSha256) {
            if ($ArchivePath) {
                throw "Specified UE4SS ZIP has SHA-256 $sha; expected $expectedSha256. Refusing to load it."
            }
            Write-Warning "Ignoring invalid cached UE4SS ZIP at $candidate (SHA-256 mismatch)."
            continue
        }
        Copy-Item -LiteralPath $candidate -Destination $zip -Force
        Write-Host "Using hash-verified UE4SS ZIP: $candidate"
        $archiveReady = $true
        break
    }

    if (-not $archiveReady) {
        Write-Host "Fetching pinned UE4SS 1161 from the historical experimental release..."
        try {
            Invoke-WebRequest -Uri $downloadUrl -OutFile $zip -UseBasicParsing -ErrorAction Stop
        } catch {
            throw "Could not download pinned UE4SS from $downloadUrl. $($_.Exception.Message) You may also pass -UE4SSZipPath with a local copy of $expectedName."
        }
        $sha = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($sha -ne $expectedSha256) {
            throw "Downloaded UE4SS SHA-256 mismatch ($sha). Expected $expectedSha256. No game files were changed."
        }
        try {
            New-Item -ItemType Directory -Force -Path $cacheDir | Out-Null
            Copy-Item -LiteralPath $zip -Destination $cacheZip -Force
        } catch {
            Write-Warning "UE4SS ZIP verified, but could not cache it for the next run: $($_.Exception.Message)"
        }
    }

    # Recompute the hash after resolving either path, before any staging.
    $hash = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($hash -ne $expectedSha256) { throw "UE4SS ZIP failed final SHA-256 verification." }
    Expand-Archive -LiteralPath $zip -DestinationPath $extract -Force
    $dwm = Get-ChildItem -LiteralPath $extract -Filter "dwmapi.dll" -File -Recurse | Select-Object -First 1
    $dir = Get-ChildItem -LiteralPath $extract -Directory -Filter "ue4ss" -Recurse | Select-Object -First 1
    if (-not $dwm -or -not $dir) { throw "Unexpected pinned UE4SS archive layout." }
    return [pscustomobject]@{
        release = $release
        asset = $asset
        sha256 = $hash
        dwm = $dwm.FullName
        ue4ss = $dir.FullName
    }
}

# This staging helper also handles -Baseline (Build=$null): move aside
# pre-existing UE4SS/proxy files without installing any replacement.
function Stage-MomentumUE4SSProbe([string]$Win64, $Build) {
    $backup = Join-Path $Win64 ".momentum-runtime-probe-backup"
    if (Test-Path -LiteralPath $backup) {
        throw "Refusing to overwrite an existing Momentum backup: $backup"
    }

    $stage = [pscustomobject]@{
        backup = $backup
        dwm = (Join-Path $Win64 "dwmapi.dll")
        ue4ss = (Join-Path $Win64 "ue4ss")
        xinput = (Join-Path $Win64 "xinput1_3.dll")
        state = $null
    }
    $state = [ordered]@{
        original_dwmapi = [bool](Test-Path -LiteralPath $stage.dwm)
        original_ue4ss = [bool](Test-Path -LiteralPath $stage.ue4ss)
        original_xinput = [bool](Test-Path -LiteralPath $stage.xinput)
    }
    $stage.state = $state

    New-Item -ItemType Directory -Path $backup -ErrorAction Stop | Out-Null
    # Durable state MUST exist before moving even one original file, allowing
    # cleanup after PowerShell/game interruption during the staging sequence.
    $state | ConvertTo-Json |
        Set-Content -LiteralPath (Join-Path $backup "state.json") -Encoding UTF8 -ErrorAction Stop

    try {
        if ($state.original_dwmapi) {
            Move-Item -LiteralPath $stage.dwm -Destination (Join-Path $backup "dwmapi.dll") -ErrorAction Stop
        }
        if ($state.original_ue4ss) {
            Move-Item -LiteralPath $stage.ue4ss -Destination (Join-Path $backup "ue4ss") -ErrorAction Stop
        }
        if ($state.original_xinput) {
            Move-Item -LiteralPath $stage.xinput -Destination (Join-Path $backup "xinput1_3.dll") -ErrorAction Stop
        }

        if ($null -ne $Build) {
            Copy-Item -LiteralPath $Build.dwm -Destination $stage.dwm -Force -ErrorAction Stop
            Copy-Item -LiteralPath $Build.ue4ss -Destination $stage.ue4ss -Recurse -Force -ErrorAction Stop
        }

        "staged" | Set-Content -LiteralPath (Join-Path $backup "stage-complete.txt") -Encoding ascii -ErrorAction Stop
        return $stage
    } catch {
        $message = $_.Exception.Message
        try {
            Restore-MomentumUE4SSProbe $stage
        } catch {
            throw "Staging failed: $message. Automatic restoration also failed: $($_.Exception.Message). Backup preserved at $backup"
        }
        throw "Failed to stage UE4SS/isolate vanilla in '$Win64': $message"
    }
}

function Restore-MomentumUE4SSProbe($Stage) {
    if (-not $Stage -or -not (Test-Path -LiteralPath $Stage.backup)) { return }

    $statePath = Join-Path $Stage.backup "state.json"
    if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) {
        throw "Backup has no state.json. No staged files were deleted: $($Stage.backup)"
    }
    $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json

    foreach ($entry in @(
        @{ Name="dwmapi.dll"; Destination=$Stage.dwm; Original=[bool]$state.original_dwmapi },
        @{ Name="ue4ss"; Destination=$Stage.ue4ss; Original=[bool]$state.original_ue4ss },
        @{ Name="xinput1_3.dll"; Destination=$Stage.xinput; Original=[bool]$state.original_xinput }
    )) {
        $saved = Join-Path $Stage.backup $entry.Name
        $savedExists = Test-Path -LiteralPath $saved
        $destExists = Test-Path -LiteralPath $entry.Destination

        if ($entry.Original -and -not $savedExists) {
            if ($destExists -and -not (Test-Path -LiteralPath (Join-Path $Stage.backup "stage-complete.txt"))) {
                # Staging may have been interrupted before moving this original.
                # Never delete an original when the expected backup does not exist.
                continue
            }
            throw "Original $($entry.Name) backup missing; preserving destination and recovery state."
        }

        if ($destExists) {
            Remove-Item -LiteralPath $entry.Destination -Recurse -Force -ErrorAction Stop
        }
        if ($entry.Original) {
            Move-Item -LiteralPath $saved -Destination $entry.Destination -ErrorAction Stop
        }
    }
    # Remove the backup ONLY after every required original was restored.
    Remove-Item -LiteralPath $Stage.backup -Recurse -Force -ErrorAction Stop
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
