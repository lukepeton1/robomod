[CmdletBinding()]
param(
    [string]$RuntimeZipPath = "",
    [string]$GameExePath = "",
    [switch]$Active
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $scriptRoot "..\.."))
. (Join-Path $scriptRoot "momentum-runtime-probe-common.ps1")
. (Join-Path $scriptRoot "momentum-runtime-probe-ue4ss.ps1")

function Find-MomentumArtifactZip([string]$Provided) {
    if ($Provided) {
        if (-not (Test-Path -LiteralPath $Provided -PathType Leaf)) {
            throw "Runtime artifact ZIP not found: $Provided"
        }
        return [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $Provided).Path)
    }
    $downloads = Join-Path ([Environment]::GetFolderPath("UserProfile")) "Downloads"
    foreach ($candidate in @(
        (Join-Path $repoRoot "handoff\MomentumOverhaul-runtime.zip"),
        (Join-Path $repoRoot "MomentumOverhaul-runtime.zip"),
        (Join-Path $downloads "MomentumOverhaul-runtime.zip")
    )) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return [System.IO.Path]::GetFullPath($candidate)
        }
    }
    throw "Download MomentumOverhaul-runtime.zip and place it in repo\handoff\, repo root, or Downloads."
}

function Resolve-MomentumNativeArtifact([string]$ExtractedRoot) {
    foreach ($relative in @(
        "native\main.dll",
        "dlls\main.dll"
    )) {
        $candidate = Join-Path $ExtractedRoot $relative
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return [pscustomobject]@{
                RelativePath = $relative
                FullPath = [System.IO.Path]::GetFullPath($candidate)
            }
        }
    }
    throw "Invalid Momentum runtime artifact: missing native\main.dll (or legacy dlls\main.dll)."
}

function Enable-MomentumMod([string]$Ue4ssRoot, [string]$ExtractedRoot, [bool]$ModeActive) {
    $modRoot = Join-Path $Ue4ssRoot "Mods\MomentumOverhaul"
    New-Item -ItemType Directory -Force -Path $modRoot | Out-Null

    foreach ($file in @(
        "Scripts\main.lua",
        "config\momentum.ini"
    )) {
        $source = Join-Path $ExtractedRoot $file
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
            throw "Runtime artifact is missing $file"
        }
        $destination = Join-Path $modRoot $file
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
        Copy-Item -LiteralPath $source -Destination $destination -Force
    }

    $nativeArtifact = Resolve-MomentumNativeArtifact $ExtractedRoot
    $nativeDestination = Join-Path $modRoot "native\main.dll"
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $nativeDestination) | Out-Null
    Copy-Item -LiteralPath $nativeArtifact.FullPath -Destination $nativeDestination -Force

    # Force safe observation mode unless explicitly requested otherwise.
    $modeText = if ($ModeActive) { "active=1" } else { "active=0" }
    Set-Content -LiteralPath (Join-Path $modRoot "config\momentum.ini") -Value $modeText -Encoding ascii

    $modsFile = Join-Path $Ue4ssRoot "Mods\mods.txt"
    $lines = @()
    if (Test-Path -LiteralPath $modsFile) {
        $lines = @(Get-Content -LiteralPath $modsFile -ErrorAction SilentlyContinue |
            Where-Object { $_ -notmatch '^\s*MomentumOverhaul\s*:' })
    }
    $lines += "MomentumOverhaul : 1"
    Set-Content -LiteralPath $modsFile -Value $lines -Encoding ascii

    $jsonFile = Join-Path $Ue4ssRoot "Mods\mods.json"
    if (Test-Path -LiteralPath $jsonFile) {
        try {
            $decoded = @(Get-Content -LiteralPath $jsonFile -Raw | ConvertFrom-Json)
            $others = @($decoded | Where-Object {
                $_ -and $_.mod_name -ne "MomentumOverhaul"
            })
            $others += [pscustomobject]@{
                mod_name = "MomentumOverhaul"
                mod_enabled = $true
            }
            ConvertTo-Json -InputObject @($others) -Depth 10 |
                Set-Content -LiteralPath $jsonFile -Encoding UTF8
        } catch {
            Write-Warning "Could not update mods.json; mods.txt has been updated."
        }
    }

    return $modRoot
}

function Start-MomentumGame([string]$GameExe, [string]$Win64) {
    $gameRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $Win64))
    $launcher = Join-Path $gameRoot "RoboQuest.exe"

    if (Test-Path -LiteralPath $launcher -PathType Leaf) {
        Start-Process -FilePath $launcher | Out-Null
        return "launcher"
    }

    if ($GameExe -match '[\\/ ]steamapps[\\/]common[\\/]') {
        Start-Process "steam://rungameid/692890" | Out-Null
        return "steam"
    }

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

    Start-Process -FilePath $GameExe | Out-Null
    return "shipping-executable"
}

function Copy-MomentumLogs([string]$ModRoot, [string]$Ue4ssRoot, [string]$OutputRoot) {
    if ($ModRoot -and (Test-Path -LiteralPath $ModRoot)) {
        foreach ($name in @("runtime-status.txt", "momentum-runtime.log")) {
            $source = Join-Path $ModRoot $name
            if (Test-Path -LiteralPath $source -PathType Leaf) {
                Copy-Item -LiteralPath $source -Destination (Join-Path $OutputRoot $name) -Force
            }
        }
    }
    if ($Ue4ssRoot -and (Test-Path -LiteralPath $Ue4ssRoot)) {
        foreach ($log in Get-ChildItem -LiteralPath $Ue4ssRoot -Filter "*.log" -File -Recurse -ErrorAction SilentlyContinue) {
            $destination = Join-Path $OutputRoot $log.Name
            Copy-Item -LiteralPath $log.FullName -Destination $destination -Force -ErrorAction SilentlyContinue
        }
    }
}

$OutputDir = Join-Path $repoRoot "handoff\momentum-runtime-test"
$Scratch = Join-Path $OutputDir "_scratch"
$RuntimeZipPath = Find-MomentumArtifactZip $RuntimeZipPath
$stage = $null
$build = $null
$modRoot = $null
$game = $null
$status = "not_started"
$errorMessage = $null

if (-not $GameExePath) {
    $GameExePath = Resolve-RoboquestShippingExeInteractive $repoRoot
}
if (-not $GameExePath) {
    throw "RoboQuest-Win64-Shipping.exe not found."
}
$GameExePath = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $GameExePath).Path)
if ([System.IO.Path]::GetFileName($GameExePath) -ine "RoboQuest-Win64-Shipping.exe") {
    throw "Pass the actual RoboQuest-Win64-Shipping.exe, not the launcher."
}
if (Find-RoboquestShippingProcess $GameExePath) {
    throw "Close Roboquest before running this test."
}
$win64 = Split-Path -Parent $GameExePath
$backup = Join-Path $win64 ".momentum-runtime-probe-backup"
if (Test-Path -LiteralPath $backup) {
    throw "An earlier test backup exists. Run cleanup-movement-runtime-probe.cmd first."
}

if (Test-Path -LiteralPath $OutputDir) {
    Remove-Item -LiteralPath $OutputDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $Scratch | Out-Null

try {
    Write-Host "=== Roboquest Momentum native runtime smoke test ==="
    Write-Host "Artifact: $RuntimeZipPath"
    Write-Host "Executable: $GameExePath"
    Write-Host ("Mode: " + $(if ($Active) { "ACTIVE (modifies movement)" } else { "OBSERVE (vanilla movement)" }))

    $extracted = Join-Path $Scratch "artifact"
    Expand-Archive -LiteralPath $RuntimeZipPath -DestinationPath $extracted -Force

    # Validate package contents BEFORE modifying the game installation.
    foreach ($file in @("Scripts\main.lua", "config\momentum.ini")) {
        if (-not (Test-Path -LiteralPath (Join-Path $extracted $file) -PathType Leaf)) {
            throw "Invalid Momentum runtime artifact: missing $file"
        }
    }
    $null = Resolve-MomentumNativeArtifact $extracted

    $writeTest = Join-Path $win64 ".momentum-write-test-$PID.tmp"
    [System.IO.File]::WriteAllText($writeTest, "momentum")
    Remove-Item -LiteralPath $writeTest -Force

    $build = Get-ProbeUE4SSBuild $Scratch
    Write-Host "UE4SS: $($build.asset.name)"
    $stage = Stage-MomentumUE4SSProbe $win64 $build

    $settings = Join-Path $stage.ue4ss "UE4SS-settings.ini"
    Set-ProbeIniValue $settings "EngineVersionOverride" "MajorVersion" "4"
    Set-ProbeIniValue $settings "EngineVersionOverride" "MinorVersion" "26"
    Set-ProbeIniValue $settings "EngineVersionOverride" "DebugBuild" "false"
    Set-ProbeIniValue $settings "General" "bUseUObjectArrayCache" "false"
    Set-ProbeIniValue $settings "Debug" "ConsoleEnabled" "1"
    Set-ProbeIniValue $settings "Debug" "GuiConsoleEnabled" "0"
    Set-ProbeIniValue $settings "Debug" "GuiConsoleVisible" "0"

    $modRoot = Enable-MomentumMod $stage.ue4ss $extracted ([bool]$Active)
    $method = Start-MomentumGame $GameExePath $win64
    Write-Host "Launch method: $method"
    Write-Host "Play SINGLE-PLAYER, move around for about one minute, then quit Roboquest normally."
    Write-Host "This window will collect the hook telemetry and restore the original game installation."

    $deadline = (Get-Date).AddSeconds(90)
    while ((Get-Date) -lt $deadline) {
        $game = Find-RoboquestShippingProcess $GameExePath
        if ($game) { break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $game) {
        $status = "game_not_started"
        throw "The shipping process did not appear within 90 seconds."
    }

    $status = "game_started"
    while (Find-RoboquestShippingProcess $GameExePath) {
        Start-Sleep -Seconds 1
    }
    $status = "game_exited"
    Copy-MomentumLogs $modRoot $stage.ue4ss $OutputDir
} catch {
    $errorMessage = $_.Exception.ToString()
    if ($status -eq "not_started") { $status = "setup_failed" }
    $errorMessage | Set-Content -LiteralPath (Join-Path $OutputDir "probe-error.txt") -Encoding UTF8
    Write-Warning ("Momentum runtime test failed: " + $_.Exception.Message)
    if ($stage) {
        Copy-MomentumLogs $modRoot $stage.ue4ss $OutputDir
    }
} finally {
    if ($stage) {
        Write-Host "Restoring original Roboquest/UE4SS files..."
        Restore-MomentumUE4SSProbe $stage
    }
}

$manifest = [ordered]@{
    schema_version = 1
    generated_utc = [DateTime]::UtcNow.ToString("o")
    status = $status
    mode = $(if ($Active) { "active" } else { "observe" })
    runtime_artifact_sha256 = (Get-FileHash -LiteralPath $RuntimeZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
    game_executable_filename = [System.IO.Path]::GetFileName($GameExePath)
    game_executable_sha256 = (Get-FileHash -LiteralPath $GameExePath -Algorithm SHA256).Hash.ToLowerInvariant()
    ue4ss_asset = $(if ($build) { $build.asset.name } else { $null })
    ue4ss_asset_sha256 = $(if ($build) { $build.sha256 } else { $null })
    error_present = [bool]$errorMessage
}
$manifest | ConvertTo-Json -Depth 6 |
    Set-Content -LiteralPath (Join-Path $OutputDir "momentum-test-manifest.json") -Encoding UTF8

if (Test-Path -LiteralPath $Scratch) {
    Remove-Item -LiteralPath $Scratch -Recurse -Force -ErrorAction SilentlyContinue
}
$zip = "$OutputDir.zip"
if (Test-Path -LiteralPath $zip) {
    Remove-Item -LiteralPath $zip -Force
}
Compress-Archive -Path (Join-Path $OutputDir "*") -DestinationPath $zip -CompressionLevel Optimal

Write-Host ""
Write-Host "Momentum test diagnostics:"
Write-Host "  $zip"
if ($errorMessage) {
    throw "Test failed. The diagnostic ZIP was still generated."
}
