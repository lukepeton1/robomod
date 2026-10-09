# Momentum runtime artifact preflight. Never use a stale DLL from handoff/
# simply because it was found first. This helper performs no game writes.

# A reflected field address is NOT a game fatal. Only match actual fatal text.
$MomentumFatalRegex = "LowLevelFatalError|Can.t find ClassConstructor for class|Fatal error|LogWindows:\s*Error:"


function Get-MomentumRuntimeBuildInfo([string]$ZipPath) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = $null
    $dllStream = $null
    $hasher = $null
    $reader = $null
    try {
        $archive = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
        $manifestEntry = $archive.GetEntry("runtime-build.txt")
        if (-not $manifestEntry) {
            throw "Missing runtime-build.txt. This is an old/unverified Momentum package."
        }
        foreach ($required in @("Scripts/main.lua", "config/momentum.ini")) {
            if (-not $archive.GetEntry($required)) {
                throw "Momentum package missing $required."
            }
        }
        $dllEntry = $archive.GetEntry("native/main.dll")
        if (-not $dllEntry) { $dllEntry = $archive.GetEntry("dlls/main.dll") }
        if (-not $dllEntry) { throw "Momentum package missing native/main.dll." }

        $reader = New-Object System.IO.StreamReader($manifestEntry.Open())
        $manifestText = $reader.ReadToEnd()
        $reader.Dispose()
        $reader = $null
        $entries = @{}
        foreach ($line in ($manifestText -split '\r?\n')) {
            if ($line -match '^([a-z_]+)=(.*)$') {
                $entries[$Matches[1]] = $Matches[2].Trim()
            }
        }
        $commit = [string]$entries["build_commit"]
        $declaredDllHash = [string]$entries["native_dll_sha256"]
        if ($commit -notmatch '^[0-9a-fA-F]{40}$') {
            throw "runtime-build.txt has no valid full build_commit SHA."
        }
        if ($declaredDllHash -notmatch '^[0-9a-fA-F]{64}$') {
            throw "runtime-build.txt has no valid native_dll_sha256."
        }

        $dllStream = $dllEntry.Open()
        $hasher = [System.Security.Cryptography.SHA256]::Create()
        $actualDllHash = [BitConverter]::ToString($hasher.ComputeHash($dllStream)).Replace("-", "").ToLowerInvariant()
        if ($actualDllHash -ne $declaredDllHash.ToLowerInvariant()) {
            throw "Native DLL hash differs from runtime-build.txt. Refusing modified/broken package."
        }
        return [pscustomobject]@{
            ZipPath = [System.IO.Path]::GetFullPath($ZipPath)
            BuildCommit = $commit.ToLowerInvariant()
            DllSha256 = $actualDllHash
        }
    } finally {
        if ($reader) { $reader.Dispose() }
        if ($dllStream) { $dllStream.Dispose() }
        if ($hasher) { $hasher.Dispose() }
        if ($archive) { $archive.Dispose() }
    }
}

function Assert-MomentumRuntimeSourceMatches([string]$RepoRoot, [string]$BuildCommit) {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw "Git is required to verify a native DLL against checked-out source."
    }

    # Require a known historical branch commit, not arbitrary provenance.
    & git -C $RepoRoot cat-file -e "$($BuildCommit)^{commit}" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Build commit $BuildCommit is not in local Git history. Run git fetch origin and retry."
    }
    & git -C $RepoRoot merge-base --is-ancestor $BuildCommit HEAD 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Build commit $BuildCommit is not an ancestor of the checked-out branch."
    }

    # A later docs-only/test-runner commit does not require recompilation, but
    # ANY native source, Lua, config or packaging change does. This catches
    # old binaries even when the archive filename is unchanged.
    $changed = @(& git -C $RepoRoot diff --name-only $BuildCommit HEAD -- "Source/runtime" ".github/workflows/build-momentum-runtime.yml" 2>$null)
    if ($LASTEXITCODE -ne 0) {
        throw "Git could not compare build commit $BuildCommit against local runtime source."
    }
    if ($changed.Count -gt 0) {
        $short = $BuildCommit.Substring(0, 12)
        throw "STALE Momentum DLL (build $short). Native/Lua/config source changed after this build: $($changed -join ', ')"
    }
}

function Find-MomentumCompatibleRuntimeZip([string]$Provided, [string]$RepoRoot) {
    $paths = New-Object System.Collections.Generic.List[string]
    if ($Provided) {
        if (-not (Test-Path -LiteralPath $Provided -PathType Leaf)) {
            throw "Runtime ZIP does not exist: $Provided"
        }
        [void]$paths.Add([System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $Provided).Path))
    } else {
        $downloads = Join-Path ([Environment]::GetFolderPath("UserProfile")) "Downloads"
        foreach ($dir in @((Join-Path $RepoRoot "handoff"), $RepoRoot, $downloads)) {
            if (-not (Test-Path -LiteralPath $dir -PathType Container)) { continue }
            # Browsers often save another download as "(1)" or "(2)".
            foreach ($file in Get-ChildItem -LiteralPath $dir -Filter "MomentumOverhaul-runtime*.zip" -File -ErrorAction SilentlyContinue) {
                if (-not $paths.Contains($file.FullName)) {
                    [void]$paths.Add($file.FullName)
                }
            }
        }
    }
    if ($paths.Count -eq 0) {
        throw "Momentum runtime ZIP not found. Download MomentumOverhaul-runtime from the newest successful GitHub Actions 'Build Momentum Runtime' run: https://github.com/lukepeton1/robomod/actions/workflows/build-momentum-runtime.yml"
    }

    $candidates = @($paths | ForEach-Object { Get-Item -LiteralPath $_ } | Sort-Object LastWriteTime -Descending)
    $rejects = New-Object System.Collections.Generic.List[string]
    foreach ($candidate in $candidates) {
        try {
            $info = Get-MomentumRuntimeBuildInfo $candidate.FullName
            Assert-MomentumRuntimeSourceMatches $RepoRoot $info.BuildCommit
            Write-Host "Verified Momentum runtime: $($candidate.FullName)"
            Write-Host "  Built from compatible commit: $($info.BuildCommit)"
            Write-Host "  DLL SHA-256: $($info.DllSha256)"
            return $info.ZipPath
        } catch {
            [void]$rejects.Add("$($candidate.FullName): $($_.Exception.Message)")
            if ($Provided) { break }
        }
    }
    foreach ($reject in $rejects) { Write-Warning $reject }
    throw "No compatible Momentum DLL archive found. Download a fresh MomentumOverhaul-runtime artifact from https://github.com/lukepeton1/robomod/actions/workflows/build-momentum-runtime.yml and rerun. Stale files can remain in handoff; a compatible copy in Downloads will be selected automatically."
}
