[CmdletBinding()]
param(
    [string]$RuntimeZipPath = "",
    [string]$GameExePath = "",
    [Alias("Bhop")]
    [switch]$Active,
    [switch]$LoaderOnly,
    [switch]$BootstrapOnly,
    [switch]$Baseline
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $scriptRoot "..\.."))
. (Join-Path $scriptRoot "momentum-runtime-probe-common.ps1")
. (Join-Path $scriptRoot "momentum-runtime-probe-ue4ss.ps1")

# Isolation modes are mutually exclusive. Bare -Active remains explicit and unsafe.
$selectedCount = 0
foreach ($selected in @($Active.IsPresent, $LoaderOnly.IsPresent, $BootstrapOnly.IsPresent, $Baseline.IsPresent)) {
    if ($selected) { $selectedCount++ }
}
if ($selectedCount -gt 1) {
    throw "Select exactly one of -Baseline, -LoaderOnly, -BootstrapOnly, or -Active; omit all for observe mode."
}

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

function Enable-MomentumMod([string]$Ue4ssRoot, [string]$SourceRoot, [bool]$ModeActive, [bool]$OnlyBootstrap) {
    $modRoot = Join-Path $Ue4ssRoot "Mods\MomentumOverhaul"
    New-Item -ItemType Directory -Force -Path $modRoot | Out-Null

    foreach ($file in @("Scripts\main.lua", "config\momentum.ini")) {
        $source = Join-Path $SourceRoot $file
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
            throw "Momentum package is missing $file"
        }
        $destination = Join-Path $modRoot $file
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
        Copy-Item -LiteralPath $source -Destination $destination -Force
    }

    if (-not $OnlyBootstrap) {
        $nativeArtifact = Resolve-MomentumNativeArtifact $SourceRoot
        $nativeDestination = Join-Path $modRoot "native\main.dll"
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $nativeDestination) | Out-Null
        Copy-Item -LiteralPath $nativeArtifact.FullPath -Destination $nativeDestination -Force
    }

    # Preserve authored physics tuning from the artifact. Only switch the
    # active state, so a player's adjustments are not silently discarded.
    $configPath = Join-Path $modRoot "config\momentum.ini"
    $configLines = @(Get-Content -LiteralPath $configPath |
        Where-Object { $_ -notmatch '^\s*(active|probe_mode)\s*=' })
    $configLines += if ($ModeActive -and -not $OnlyBootstrap) { "active=1" } else { "active=0" }
    if ($OnlyBootstrap) { $configLines += "probe_mode=bootstrap_only" }
    Set-Content -LiteralPath $configPath -Value $configLines -Encoding ascii
    return $modRoot
}

function Set-MomentumIsolatedMods([string]$Ue4ssRoot, [bool]$EnableMomentum) {
    $modsDir = Join-Path $Ue4ssRoot "Mods"
    if (-not (Test-Path -LiteralPath $modsDir -PathType Container)) {
        throw "Staged UE4SS Mods directory is missing."
    }

    # UE4SS's enabled.txt bypasses mods.txt. Remove these only from the
    # temporary staged package; the user's original UE4SS tree is backed up.
    Get-ChildItem -LiteralPath $modsDir -Filter "enabled.txt" -Recurse -File -ErrorAction SilentlyContinue |
        Remove-Item -Force -ErrorAction Stop

    $modsTxt = if ($EnableMomentum) { "MomentumOverhaul : 1`n" } else { "; Momentum loader isolation: all Lua/C++ mods disabled`n" }
    $modsJson = if ($EnableMomentum) { '[{"mod_name":"MomentumOverhaul","mod_enabled":true}]' } else { '[]' }
    $utf8NoBom = New-Object System.Text.UTF8Encoding -ArgumentList $false
    [System.IO.File]::WriteAllText((Join-Path $modsDir "mods.txt"), $modsTxt, $utf8NoBom)
    [System.IO.File]::WriteAllText((Join-Path $modsDir "mods.json"), $modsJson, $utf8NoBom)
}

function Copy-RoboquestCrashDiagnostics([string]$OutputRoot, [datetime]$RunStarted) {
    $savedRoot = Join-Path $env:LOCALAPPDATA "RoboQuest\Saved"
    if (-not (Test-Path -LiteralPath $savedRoot)) { return }

    $cutoff = $RunStarted.AddSeconds(-5)
    $allowed = @(".log", ".txt", ".xml", ".ini", ".json")

    foreach ($sourceRoot in @(
        (Join-Path $savedRoot "Logs"),
        (Join-Path $savedRoot "Crashes")
    )) {
        if (-not (Test-Path -LiteralPath $sourceRoot)) { continue }

        $files = Get-ChildItem -LiteralPath $sourceRoot -File -Recurse -ErrorAction SilentlyContinue |
            Where-Object {
                $_.LastWriteTime -ge $cutoff -and
                $allowed -contains $_.Extension.ToLowerInvariant()
            } |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 12

        foreach ($file in $files) {
            $safeName = ($file.FullName.Substring($savedRoot.Length).TrimStart("\") -replace '[\\/:*?"<>|]', '_')
            $destination = Join-Path $OutputRoot ("game-" + $safeName)
            Copy-Item -LiteralPath $file.FullName -Destination $destination -Force -ErrorAction SilentlyContinue
        }
    }
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
        foreach ($name in @("runtime-status.txt", "runtime-bindings.ini", "momentum-runtime.log")) {
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
$needsArtifact = -not ($Baseline -or $LoaderOnly -or $BootstrapOnly)
if ($needsArtifact) {
    $RuntimeZipPath = Find-MomentumArtifactZip $RuntimeZipPath
} elseif ($RuntimeZipPath) {
    throw "-RuntimeZipPath is only used by observe and active mode."
}

$stage = $null
$build = $null
$modRoot = $null
$game = $null
$status = "not_started"
$errorMessage = $null
$restoreSucceeded = $true
$runStarted = Get-Date
$mode = if ($Baseline) { "baseline" }
        elseif ($LoaderOnly) { "loader_only" }
        elseif ($BootstrapOnly) { "bootstrap_only" }
        elseif ($Active) { "active" } else { "observe" }

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

$gameHash = (Get-FileHash -LiteralPath $GameExePath -Algorithm SHA256).Hash.ToLowerInvariant()
$expectedHash = "158487e80be71d5570ca0a1e1a1208ab1c0842daf181f4cb6c98920bc4b4dc1f"
if ($mode -in @("observe", "active", "bootstrap_only") -and $gameHash -ne $expectedHash) {
    throw "The game executable does not match the pinned Momentum build. Native/bootstrap tests are disabled; use -LoaderOnly for loader isolation."
}

if (Test-Path -LiteralPath $OutputDir) {
    Remove-Item -LiteralPath $OutputDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $Scratch | Out-Null

try {
    Write-Host "=== Roboquest Momentum controlled startup probe ==="
    Write-Host "Mode: $mode"
    Write-Host "Executable: $GameExePath"
    if ($needsArtifact) { Write-Host "Runtime artifact: $RuntimeZipPath" }
    else { Write-Host "No Momentum runtime artifact is required." }

    $sourceRoot = Join-Path $repoRoot "Source\runtime\native"
    if ($needsArtifact) {
        $sourceRoot = Join-Path $Scratch "artifact"
        Expand-Archive -LiteralPath $RuntimeZipPath -DestinationPath $sourceRoot -Force
        foreach ($file in @("Scripts\main.lua", "config\momentum.ini")) {
            if (-not (Test-Path -LiteralPath (Join-Path $sourceRoot $file) -PathType Leaf)) {
                throw "Invalid Momentum runtime artifact: missing $file"
            }
        }
        $null = Resolve-MomentumNativeArtifact $sourceRoot
    } elseif ($BootstrapOnly) {
        if (-not (Test-Path -LiteralPath (Join-Path $sourceRoot "Scripts\main.lua"))) {
            throw "Bootstrap source missing. Pull the movement branch before testing."
        }
    }

    $writeTest = Join-Path $win64 ".momentum-write-test-$PID.tmp"
    [System.IO.File]::WriteAllText($writeTest, "momentum")
    Remove-Item -LiteralPath $writeTest -Force

    if (-not $Baseline) {
        $build = Get-ProbeUE4SSBuild $Scratch
        Write-Host "UE4SS: $($build.asset.name)"
    }
    $stage = Stage-MomentumUE4SSProbe $win64 $build

    if (-not $Baseline) {
        $settings = Join-Path $stage.ue4ss "UE4SS-settings.ini"
        Set-ProbeIniValue $settings "EngineVersionOverride" "MajorVersion" "4"
        Set-ProbeIniValue $settings "EngineVersionOverride" "MinorVersion" "26"
        Set-ProbeIniValue $settings "EngineVersionOverride" "DebugBuild" "false"
        Set-ProbeIniValue $settings "General" "bUseUObjectArrayCache" "false"
        Set-ProbeIniValue $settings "Debug" "ConsoleEnabled" "1"
        Set-ProbeIniValue $settings "Debug" "GuiConsoleEnabled" "0"
        Set-ProbeIniValue $settings "Debug" "GuiConsoleVisible" "0"

        $enableMomentum = -not $LoaderOnly
        Set-MomentumIsolatedMods $stage.ue4ss $enableMomentum

        if ($enableMomentum) {
            $modRoot = Enable-MomentumMod $stage.ue4ss $sourceRoot ([bool]$Active) ([bool]$BootstrapOnly)
        }
    }

    $runStarted = Get-Date
    $method = Start-MomentumGame $GameExePath $win64
    Write-Host "Launch method: $method"
    if ($mode -in @("baseline", "loader_only", "bootstrap_only")) {
        Write-Host "Enter the same basecamp/game path that previously crashed; stay about 30 seconds, then quit normally."
    } else {
        Write-Host "Play SINGLE-PLAYER, move around for about one minute, then quit normally."
    }
    Write-Host "Logs will be collected automatically; staged files will be restored."

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
    Copy-RoboquestCrashDiagnostics $OutputDir $runStarted
} catch {
    $errorMessage = $_.Exception.ToString()
    if ($status -eq "not_started") { $status = "setup_failed" }
    $errorMessage | Set-Content -LiteralPath (Join-Path $OutputDir "probe-error.txt") -Encoding UTF8
    Write-Warning ("Momentum runtime test failed: " + $_.Exception.Message)
    if ($stage) { Copy-MomentumLogs $modRoot $stage.ue4ss $OutputDir }
    Copy-RoboquestCrashDiagnostics $OutputDir $runStarted
} finally {
    if ($stage) {
        Write-Host "Restoring original Roboquest/UE4SS files..."
        try {
            Restore-MomentumUE4SSProbe $stage
        } catch {
            $restoreSucceeded = $false
            $restoreMessage = "RESTORATION FAILED: $($_.Exception.ToString())"
            $restoreMessage | Set-Content -LiteralPath (Join-Path $OutputDir "restore-error.txt") -Encoding UTF8
            Write-Warning $restoreMessage
            if (-not $errorMessage) { $errorMessage = $restoreMessage }
        }
    }
}

$fatalDetected = $false
$logFiles = @(Get-ChildItem -LiteralPath $OutputDir -File -Filter "*.log" -ErrorAction SilentlyContinue)
foreach ($file in $logFiles) {
    if (Select-String -LiteralPath $file.FullName -Pattern "LowLevelFatalError|ClassConstructor|Fatal error|LogWindows:\s*Error:" -Quiet -ErrorAction SilentlyContinue) {
        $fatalDetected = $true
        break
    }
}
if (@(Get-ChildItem -LiteralPath $OutputDir -File -Filter "game-Crashes_*" -ErrorAction SilentlyContinue).Count -gt 0) {
    $fatalDetected = $true
}

$manifest = [ordered]@{
    schema_version = 2
    generated_utc = [DateTime]::UtcNow.ToString("o")
    started_utc = $runStarted.ToUniversalTime().ToString("o")
    status = $status
    mode = $mode
    native_dll_staged = ($mode -in @("observe", "active"))
    runtime_artifact_sha256 = $(if ($needsArtifact) { (Get-FileHash -LiteralPath $RuntimeZipPath -Algorithm SHA256).Hash.ToLowerInvariant() } else { $null })
    game_executable_filename = [System.IO.Path]::GetFileName($GameExePath)
    game_executable_sha256 = $gameHash
    ue4ss_asset = $(if ($build) { $build.asset.name } else { $null })
    ue4ss_asset_sha256 = $(if ($build) { $build.sha256 } else { $null })
    fatal_error_detected = $fatalDetected
    game_files_restored = $restoreSucceeded
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
if ($fatalDetected) { Write-Warning "Fatal/crash indicators found in this run's logs. Inspect the diagnostic ZIP." }
if ($errorMessage) { throw "Test failed. Diagnostic ZIP was generated; check restore-error.txt if present." }
