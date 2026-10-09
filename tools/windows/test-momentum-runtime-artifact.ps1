# Deterministic file-only validation. Never launches Roboquest or loads a DLL.
$ErrorActionPreference = "Stop"
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
. (Join-Path $PSScriptRoot "momentum-runtime-probe-artifact.ps1")
Add-Type -AssemblyName System.IO.Compression.FileSystem

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw "ASSERTION FAILED: $Message" }
}
function Assert-Rejected([scriptblock]$Action, [string]$Message) {
    $didThrow = $false
    try { & $Action } catch { $didThrow = $true }
    Assert-True $didThrow $Message
}
function Make-TestZip([string]$Directory, [string]$ZipPath, [string]$BuildCommit, [bool]$CorruptHash = $false, [bool]$OmitManifest = $false) {
    if (Test-Path -LiteralPath $Directory) { Remove-Item $Directory -Recurse -Force }
    New-Item -ItemType Directory -Force -Path (Join-Path $Directory "native"), (Join-Path $Directory "Scripts"), (Join-Path $Directory "config") | Out-Null
    [IO.File]::WriteAllText((Join-Path $Directory "native/main.dll"), "fixture-native-dll")
    [IO.File]::WriteAllText((Join-Path $Directory "Scripts/main.lua"), "print('fixture')")
    [IO.File]::WriteAllText((Join-Path $Directory "config/momentum.ini"), "active=0")
    $dll = Join-Path $Directory "native/main.dll"
    $hash = (Get-FileHash -LiteralPath $dll -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($CorruptHash) { $hash = "0" * 64 }
    if (-not $OmitManifest) {
        @(
            "build_commit=$BuildCommit",
            "native_dll_sha256=$hash",
            "mode=observe_by_default"
        ) | Set-Content -LiteralPath (Join-Path $Directory "runtime-build.txt") -Encoding ascii
    }
    if (Test-Path -LiteralPath $ZipPath) { Remove-Item -LiteralPath $ZipPath -Force }
    [IO.Compression.ZipFile]::CreateFromDirectory($Directory, $ZipPath)
}

$testRoot = Join-Path ([IO.Path]::GetTempPath()) ("momentum-artifact-test-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $testRoot | Out-Null
try {
    $head = (& git -C $repoRoot rev-parse HEAD).Trim()
    Assert-True ($LASTEXITCODE -eq 0) "Cannot inspect local Git commit"

    $dir = Join-Path $testRoot "package"
    $zip = Join-Path $testRoot "test.zip"
    Make-TestZip $dir $zip $head
    $info = Get-MomentumRuntimeBuildInfo $zip
    Assert-True ($info.BuildCommit -eq $head) "Manifest commit was parsed incorrectly"
    Assert-MomentumRuntimeSourceMatches $repoRoot $info.BuildCommit
    Write-Host "PASS current-runtime manifest/source match"

    Make-TestZip $dir $zip $head $true
    Assert-Rejected { $null = Get-MomentumRuntimeBuildInfo $zip } "Tampered DLL unexpectedly accepted"
    Write-Host "PASS native DLL integrity gate"

    Make-TestZip $dir $zip $head $false $true
    Assert-Rejected { $null = Get-MomentumRuntimeBuildInfo $zip } "Missing manifest unexpectedly accepted"
    Write-Host "PASS missing-manifest fail closed"

    # This commit pre-dates the first acceleration overhaul. With full history
    # available, it must not pass the current runtime source comparison.
    $oldCommit = "1a0aebad93b44c311f150f0bcc427ddf93c3992e"
    & git -C $repoRoot cat-file -e "$($oldCommit)^{commit}" 2>$null
    Assert-True ($LASTEXITCODE -eq 0) "CI must fetch full branch history for stale comparison"
    Make-TestZip $dir $zip $oldCommit
    $oldInfo = Get-MomentumRuntimeBuildInfo $zip
    Assert-Rejected { Assert-MomentumRuntimeSourceMatches $repoRoot $oldInfo.BuildCommit } "Old movement physics unexpectedly accepted"
    Write-Host "PASS old-source stale-DLL rejection"

    Assert-True (-not ("UClass::ClassConstructor = 0xB0" -match $MomentumFatalRegex)) "Harmless UE4SS layout diagnostic falsely reported as fatal"
    Assert-True ("Can't find ClassConstructor for class /Game/BP_APlayer_C" -match $MomentumFatalRegex) "Real ClassConstructor crash not detected"
    Assert-True ("LowLevelFatalError" -match $MomentumFatalRegex) "Unreal low-level fatal not detected"
    Write-Host "PASS crash-detection specificity"

    Write-Host "ALL MOMENTUM ARTIFACT PREFLIGHT TESTS PASSED"
} finally {
    Remove-Item -LiteralPath $testRoot -Recurse -Force -ErrorAction SilentlyContinue
}
