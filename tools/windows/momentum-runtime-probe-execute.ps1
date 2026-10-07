function Invoke-MomentumRuntimeProbe([string]$RepoRoot,[string]$GameExePath,[string]$OutputDir) {
    if (-not $GameExePath) {
        $GameExePath = Resolve-RoboquestShippingExeInteractive $RepoRoot
    }
    if (-not $GameExePath) {
        throw "Could not locate RoboQuest-Win64-Shipping.exe."
    }
    $GameExePath = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $GameExePath).Path)
    Save-CachedRoboquestShippingExe $RepoRoot $GameExePath
    if ([System.IO.Path]::GetFileName($GameExePath) -ine "RoboQuest-Win64-Shipping.exe"){throw "Wrong executable: $GameExePath"}
    if (Find-RoboquestShippingProcess $GameExePath){throw "Close Roboquest before running the runtime probe."}
    $win64=Split-Path -Parent $GameExePath;$backup=Join-Path $win64 ".momentum-runtime-probe-backup";if (Test-Path $backup){throw "Existing probe backup found. Run cleanup-movement-runtime-probe.cmd first."}
    $OutputDir=[System.IO.Path]::GetFullPath($OutputDir);if (Test-Path $OutputDir){Remove-Item $OutputDir -Recurse -Force};New-Item -ItemType Directory -Force $OutputDir|Out-Null
    $scratch=Join-Path $OutputDir "_scratch";New-Item -ItemType Directory -Force $scratch|Out-Null
    $filter=Join-Path $RepoRoot "tools\filter_movement_jmap.py";$build=$null;$stage=$null;$status="not_started";$jmapsOut=@()
    try {
        Write-Host "=== Momentum runtime compatibility probe ===";Write-Host "Game: $GameExePath"
        $build=Get-ProbeUE4SSBuild $scratch;Write-Host "UE4SS asset: $($build.asset.name)"
        $stage=Stage-MomentumUE4SSProbe $win64 $build;Configure-MomentumUE4SSProbe $stage.ue4ss
        $root=Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $win64));$launcher=Join-Path $root "RoboQuest.exe";$launch=if(Test-Path $launcher){$launcher}else{$GameExePath}
        Write-Host "UE4SS staged temporarily. Stay at the menu for ~15 seconds, then quit Roboquest normally.";Start-Process $launch|Out-Null
        $deadline = (Get-Date).AddSeconds(90);$proc = $null;while ((Get-Date) -lt $deadline){$proc=Find-RoboquestShippingProcess $GameExePath;if ($proc){break};Start-Sleep -Milliseconds 500}
        if (-not $proc){$status="game_never_started";throw "Shipping process did not start within 90 seconds."}
        $status="game_started";Write-Host "Shipping process detected; waiting for game exit...";while (Find-RoboquestShippingProcess $GameExePath){Start-Sleep 1};$status="game_exited"
        $found=@(Get-ChildItem $stage.ue4ss -Filter "*.jmap" -File -Recurse -ErrorAction SilentlyContinue;Get-ChildItem $win64 -Filter "*.jmap" -File -ErrorAction SilentlyContinue)|Sort-Object FullName -Unique
        foreach($j in $found){$dest=Join-Path $OutputDir $j.Name;Copy-Item $j.FullName $dest -Force;$jmapsOut+=$dest;$filtered=Join-Path $OutputDir ("movement-"+$j.BaseName+".json");$code = Invoke-ProbePython @($filter,$dest,"--output",$filtered);if ($code -ne 0){Write-Warning "JMAP filter failed: $($j.Name)"}}
        foreach($log in Get-ChildItem $stage.ue4ss -Filter "*.log" -File -Recurse -ErrorAction SilentlyContinue){Copy-Item $log.FullName (Join-Path $OutputDir $log.Name) -Force}
    } finally { if ($stage){Write-Host "Restoring original game-directory files...";Restore-MomentumUE4SSProbe $stage} }
    $manifest=[ordered]@{schema_version=1;generated_utc=[DateTime]::UtcNow.ToString("o");game_executable_filename=[System.IO.Path]::GetFileName($GameExePath);game_executable_bytes=(Get-Item $GameExePath).Length;game_executable_sha256=(Get-FileHash -Algorithm SHA256 $GameExePath).Hash.ToLowerInvariant();probe_status=$status;ue4ss_release_tag=if ($build){$build.release.tag_name}else{$null};ue4ss_asset=if ($build){$build.asset.name}else{$null};ue4ss_asset_sha256=if ($build){$build.sha256}else{$null};jmap_count=$jmapsOut.Count;contains_game_binary=$false;contains_ue4ss_binary=$false}
    $manifest|ConvertTo-Json -Depth 6|Set-Content (Join-Path $OutputDir "runtime-probe-manifest.json") -Encoding UTF8
    if (Test-Path $scratch){Remove-Item $scratch -Recurse -Force};$zip="$OutputDir.zip";if (Test-Path $zip){Remove-Item $zip -Force};Compress-Archive -Path (Join-Path $OutputDir "*") -DestinationPath $zip -CompressionLevel Optimal
    Write-Host "Runtime probe ZIP: $zip";Write-Host "JMAP files collected: $($jmapsOut.Count)";if ($jmapsOut.Count -eq 0){Write-Warning "No JMAP produced. Upload the ZIP anyway; logs are diagnostic."}
}
