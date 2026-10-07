function Invoke-MomentumRuntimeProbe([string]$RepoRoot,[string]$GameExePath,[string]$OutputDir) {
    $build = $null
    $stage = $null
    $status = "not_started"
    $jmapsOut = @()
    $probeError = $null
    $win64 = $null
    $scratch = $null

    if (-not $GameExePath) {
        $GameExePath = Resolve-RoboquestShippingExeInteractive $RepoRoot
    }
    if (-not $GameExePath) {
        throw "Could not locate RoboQuest-Win64-Shipping.exe."
    }

    $GameExePath = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $GameExePath).Path)
    Save-CachedRoboquestShippingExe $RepoRoot $GameExePath

    if ([System.IO.Path]::GetFileName($GameExePath) -ine "RoboQuest-Win64-Shipping.exe") {
        throw "Wrong executable: $GameExePath"
    }
    if (Find-RoboquestShippingProcess $GameExePath) {
        throw "Close Roboquest before running the runtime probe."
    }

    $win64 = Split-Path -Parent $GameExePath
    $backup = Join-Path $win64 ".momentum-runtime-probe-backup"
    if (Test-Path -LiteralPath $backup) {
        throw "Existing probe backup found. Run cleanup-movement-runtime-probe.cmd first."
    }

    $OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
    if (Test-Path -LiteralPath $OutputDir) {
        Remove-Item -LiteralPath $OutputDir -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

    $scratch = Join-Path $OutputDir "_scratch"
    New-Item -ItemType Directory -Force -Path $scratch | Out-Null
    $filter = Join-Path $RepoRoot "tools\filter_movement_jmap.py"

    try {
        $writeProbe = Join-Path $win64 ".momentum-write-test-$PID.tmp"
        try {
            [System.IO.File]::WriteAllText($writeProbe, "momentum")
            Remove-Item -LiteralPath $writeProbe -Force
        } catch {
            throw "Momentum cannot write to '$win64'. Rerun Command Prompt as Administrator, then run the probe again. $($_.Exception.Message)"
        }

        Write-Host "=== Momentum runtime compatibility probe ==="
        Write-Host "Game: $GameExePath"

        $build = Get-ProbeUE4SSBuild $scratch
        Write-Host "UE4SS asset: $($build.asset.name)"

        $stage = Stage-MomentumUE4SSProbe $win64 $build
        Configure-MomentumUE4SSProbe $stage.ue4ss

        $root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $win64))
        $launcher = Join-Path $root "RoboQuest.exe"
        $launchMethod = $null

        if (Test-Path -LiteralPath $launcher) {
            Start-Process -FilePath $launcher | Out-Null
            $launchMethod = "launcher-file"
        } elseif ($GameExePath -match "[\\/]steamapps[\\/]common[\\/]") {
            Start-Process "steam://rungameid/692890" | Out-Null
            $launchMethod = "steam"
        } else {
            try {
                $app = Get-StartApps -ErrorAction SilentlyContinue |
                    Where-Object { $_.Name -match "^Robo\s*Quest$|Roboquest" } |
                    Select-Object -First 1
                if ($app -and $app.AppID) {
                    Start-Process ("shell:AppsFolder\" + $app.AppID) | Out-Null
                    $launchMethod = "start-menu"
                }
            } catch {
            }

            if (-not $launchMethod) {
                Start-Process -FilePath $GameExePath | Out-Null
                $launchMethod = "shipping-exe"
            }
        }

        Write-Host "UE4SS staged temporarily."
        Write-Host "Launch method: $launchMethod"
        Write-Host "Stay at the menu for ~15 seconds, then quit Roboquest normally."

        $deadline = (Get-Date).AddSeconds(90)
        $proc = $null
        while ((Get-Date) -lt $deadline) {
            $proc = Find-RoboquestShippingProcess $GameExePath
            if ($proc) { break }
            Start-Sleep -Milliseconds 500
        }

        if (-not $proc) {
            $status = "game_never_started"
            throw "Shipping process did not start within 90 seconds."
        }

        $status = "game_started"
        Write-Host "Shipping process detected; waiting for game exit..."
        while (Find-RoboquestShippingProcess $GameExePath) {
            Start-Sleep 1
        }
        $status = "game_exited"

        $found = @(
            Get-ChildItem -LiteralPath $stage.ue4ss -Filter "*.jmap" -File -Recurse -ErrorAction SilentlyContinue
            Get-ChildItem -LiteralPath $win64 -Filter "*.jmap" -File -ErrorAction SilentlyContinue
        ) | Sort-Object FullName -Unique

        foreach ($j in $found) {
            $dest = Join-Path $OutputDir $j.Name
            Copy-Item -LiteralPath $j.FullName -Destination $dest -Force
            $jmapsOut += $dest

            $filtered = Join-Path $OutputDir ("movement-" + $j.BaseName + ".json")
            $code = Invoke-ProbePython @($filter, $dest, "--output", $filtered)
            if ($code -ne 0) {
                Write-Warning "JMAP filter failed: $($j.Name)"
            }
        }

        foreach ($log in Get-ChildItem -LiteralPath $stage.ue4ss -Filter "*.log" -File -Recurse -ErrorAction SilentlyContinue) {
            Copy-Item -LiteralPath $log.FullName -Destination (Join-Path $OutputDir $log.Name) -Force
        }
    } catch {
        $probeError = $_.Exception.ToString()
        if ($status -eq "not_started") {
            $status = "probe_failed_before_game_start"
        }

        if ($stage -and (Test-Path -LiteralPath $stage.ue4ss)) {
            foreach ($log in Get-ChildItem -LiteralPath $stage.ue4ss -Filter "*.log" -File -Recurse -ErrorAction SilentlyContinue) {
                Copy-Item -LiteralPath $log.FullName -Destination (Join-Path $OutputDir $log.Name) -Force -ErrorAction SilentlyContinue
            }
        }

        $probeError | Set-Content -LiteralPath (Join-Path $OutputDir "probe-error.txt") -Encoding UTF8
        Write-Warning "Momentum runtime probe failed. A diagnostic ZIP will still be produced."
        Write-Warning $_.Exception.Message
    } finally {
        if ($stage) {
            Write-Host "Restoring original game-directory files..."
            Restore-MomentumUE4SSProbe $stage
        }
    }

    $manifest = [ordered]@{
        schema_version = 2
        generated_utc = [DateTime]::UtcNow.ToString("o")
        game_executable_filename = [System.IO.Path]::GetFileName($GameExePath)
        game_executable_bytes = (Get-Item -LiteralPath $GameExePath).Length
        game_executable_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $GameExePath).Hash.ToLowerInvariant()
        probe_status = $status
        probe_error_present = [bool]$probeError
        ue4ss_release_tag = if ($build) { $build.release.tag_name } else { $null }
        ue4ss_asset = if ($build) { $build.asset.name } else { $null }
        ue4ss_asset_sha256 = if ($build) { $build.sha256 } else { $null }
        jmap_count = $jmapsOut.Count
        contains_game_binary = $false
        contains_ue4ss_binary = $false
    }
    $manifest |
        ConvertTo-Json -Depth 6 |
        Set-Content -LiteralPath (Join-Path $OutputDir "runtime-probe-manifest.json") -Encoding UTF8

    if ($scratch -and (Test-Path -LiteralPath $scratch)) {
        Remove-Item -LiteralPath $scratch -Recurse -Force -ErrorAction SilentlyContinue
    }

    $zip = "$OutputDir.zip"
    if (Test-Path -LiteralPath $zip) {
        Remove-Item -LiteralPath $zip -Force
    }
    Compress-Archive -Path (Join-Path $OutputDir "*") -DestinationPath $zip -CompressionLevel Optimal

    Write-Host ""
    Write-Host "Runtime probe ZIP:"
    Write-Host "  $zip"
    Write-Host "JMAP files collected: $($jmapsOut.Count)"

    if ($jmapsOut.Count -eq 0) {
        Write-Warning "No JMAP produced. Upload the ZIP anyway; logs/error diagnostics are included."
    }

    if ($probeError) {
        throw "Momentum runtime probe failed, but diagnostic ZIP was created at '$zip'."
    }
}
