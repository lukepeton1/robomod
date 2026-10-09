# File-system-only regression tests; never launches Roboquest or downloads UE4SS.
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "momentum-runtime-probe-ue4ss.ps1")

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw "ASSERTION FAILED: $Message" }
}
function Assert-Text([string]$Path, [string]$Expected) {
    Assert-True (Test-Path -LiteralPath $Path -PathType Leaf) "Missing $Path"
    $actual = [System.IO.File]::ReadAllText($Path)
    Assert-True ($actual -ceq $Expected) "Expected '$Expected' in $Path, got '$actual'"
}
function Set-Text([string]$Path, [string]$Value) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path) | Out-Null
    [System.IO.File]::WriteAllText($Path, $Value)
}
function New-StageFixture([string]$Root) {
    New-Item -ItemType Directory -Force -Path $Root | Out-Null
    Set-Text (Join-Path $Root "dwmapi.dll") "original-dwm"
    Set-Text (Join-Path $Root "xinput1_3.dll") "original-xinput"
    Set-Text (Join-Path $Root "ue4ss/Mods/original-mod.txt") "original-ue4ss"
}

$testRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("momentum-stage-test-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $testRoot | Out-Null
try {
    # 1. Baseline mode temporarily removes UE4SS, then restores every original.
    $baseline = Join-Path $testRoot "baseline"
    New-StageFixture $baseline
    $stage = Stage-MomentumUE4SSProbe $baseline $null
    Assert-True (-not (Test-Path -LiteralPath $stage.dwm)) "Baseline still has UE4SS proxy"
    Assert-True (-not (Test-Path -LiteralPath $stage.ue4ss)) "Baseline still has UE4SS directory"
    Assert-True (-not (Test-Path -LiteralPath $stage.xinput)) "Baseline still has xinput proxy"
    Assert-Text (Join-Path $stage.backup "dwmapi.dll") "original-dwm"
    Restore-MomentumUE4SSProbe $stage
    Assert-Text (Join-Path $baseline "dwmapi.dll") "original-dwm"
    Assert-Text (Join-Path $baseline "xinput1_3.dll") "original-xinput"
    Assert-Text (Join-Path $baseline "ue4ss/Mods/original-mod.txt") "original-ue4ss"
    Assert-True (-not (Test-Path -LiteralPath $stage.backup)) "Baseline backup not cleaned"
    Write-Host "PASS baseline original-file preservation"

    # 2. UE4SS install overwrites no originals and cleans staged files.
    $game = Join-Path $testRoot "loader"
    New-StageFixture $game
    $fixtureBuildRoot = Join-Path $testRoot "build"
    $buildDwm = Join-Path $fixtureBuildRoot "dwmapi.dll"
    $buildUe4ss = Join-Path $fixtureBuildRoot "ue4ss"
    Set-Text $buildDwm "staged-dwm"
    Set-Text (Join-Path $buildUe4ss "Mods/staged-mod.txt") "staged-ue4ss"
    $build = [pscustomobject]@{dwm=$buildDwm; ue4ss=$buildUe4ss}
    $stage = Stage-MomentumUE4SSProbe $game $build
    Assert-Text $stage.dwm "staged-dwm"
    Assert-Text (Join-Path $stage.ue4ss "Mods/staged-mod.txt") "staged-ue4ss"
    Assert-True (Test-Path -LiteralPath (Join-Path $stage.backup "state.json")) "Missing recovery journal"
    Restore-MomentumUE4SSProbe $stage
    Assert-Text (Join-Path $game "dwmapi.dll") "original-dwm"
    Assert-Text (Join-Path $game "xinput1_3.dll") "original-xinput"
    Assert-Text (Join-Path $game "ue4ss/Mods/original-mod.txt") "original-ue4ss"
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $game "ue4ss/Mods/staged-mod.txt"))) "Staged UE4SS leaked after restore"
    Assert-True (-not (Test-Path -LiteralPath $stage.backup)) "Loader backup not cleaned"
    Write-Host "PASS loader staging and original-file restoration"

    # 3. Crash halfway through staging (original still at destination)
    # must not result in the remaining original files being deleted.
    $partial = Join-Path $testRoot "partial"
    New-StageFixture $partial
    $backup = Join-Path $partial ".momentum-runtime-probe-backup"
    New-Item -ItemType Directory -Force -Path $backup | Out-Null
    @{
        original_dwmapi = $true
        original_ue4ss = $true
        original_xinput = $true
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $backup "state.json")
    Move-Item -LiteralPath (Join-Path $partial "dwmapi.dll") -Destination (Join-Path $backup "dwmapi.dll")
    $stage = [pscustomobject]@{
        backup = $backup
        dwm = (Join-Path $partial "dwmapi.dll")
        ue4ss = (Join-Path $partial "ue4ss")
        xinput = (Join-Path $partial "xinput1_3.dll")
    }
    Restore-MomentumUE4SSProbe $stage
    Assert-Text (Join-Path $partial "dwmapi.dll") "original-dwm"
    Assert-Text (Join-Path $partial "xinput1_3.dll") "original-xinput"
    Assert-Text (Join-Path $partial "ue4ss/Mods/original-mod.txt") "original-ue4ss"
    Assert-True (-not (Test-Path -LiteralPath $backup)) "Partial backup not cleaned"
    Write-Host "PASS crash-interrupted partial staging recovery"

    # 4. A missing original backup after completed staging MUST fail closed.
    $broken = Join-Path $testRoot "missing-backup"
    New-Item -ItemType Directory -Force -Path $broken | Out-Null
    $backup = Join-Path $broken ".momentum-runtime-probe-backup"
    New-Item -ItemType Directory -Force -Path $backup | Out-Null
    @{original_dwmapi=$true; original_ue4ss=$false; original_xinput=$false} |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $backup "state.json")
    "staged" | Set-Content -LiteralPath (Join-Path $backup "stage-complete.txt")
    Set-Text (Join-Path $broken "dwmapi.dll") "staged-not-original"
    $stage = [pscustomobject]@{
        backup = $backup
        dwm = (Join-Path $broken "dwmapi.dll")
        ue4ss = (Join-Path $broken "ue4ss")
        xinput = (Join-Path $broken "xinput1_3.dll")
    }
    $failedSafely = $false
    try { Restore-MomentumUE4SSProbe $stage } catch { $failedSafely = $true }
    Assert-True $failedSafely "Missing original backup was silently ignored"
    Assert-Text (Join-Path $broken "dwmapi.dll") "staged-not-original"
    Assert-True (Test-Path -LiteralPath $backup) "Unrecoverable backup metadata was deleted"
    Write-Host "PASS missing-backup fail-closed behavior"

    Write-Host "ALL MOMENTUM STAGING TESTS PASSED"
} finally {
    Remove-Item -LiteralPath $testRoot -Recurse -Force -ErrorAction SilentlyContinue
}
