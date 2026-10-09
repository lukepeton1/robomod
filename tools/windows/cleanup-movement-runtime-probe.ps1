[CmdletBinding()]
param([string]$GameExePath = "")

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $scriptRoot "..\.."))
. (Join-Path $scriptRoot "momentum-runtime-probe-common.ps1")
. (Join-Path $scriptRoot "momentum-runtime-probe-ue4ss.ps1")

# Recovery should never launch a new game instance or require a fresh runtime ZIP.
if (-not $GameExePath) {
    $GameExePath = Get-CachedRoboquestShippingExe $repoRoot
}
if (-not $GameExePath) {
    $GameExePath = Find-RoboquestShippingExe
}
if (-not $GameExePath) {
    throw "Could not locate RoboQuest-Win64-Shipping.exe. Pass -GameExePath to recover its game directory."
}
$GameExePath = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $GameExePath).Path)
if ([System.IO.Path]::GetFileName($GameExePath) -ine "RoboQuest-Win64-Shipping.exe") {
    throw "Wrong executable; pass RoboQuest-Win64-Shipping.exe."
}
if (Find-RoboquestShippingProcess $GameExePath) {
    throw "Close Roboquest before restoring staged proxy DLLs and UE4SS files."
}

$win64 = Split-Path -Parent $GameExePath
$backupRoot = Join-Path $win64 ".momentum-runtime-probe-backup"
if (-not (Test-Path -LiteralPath $backupRoot)) {
    Write-Host "No Momentum probe backup exists. Nothing to restore."
    exit 0
}

$stage = [pscustomobject]@{
    backup = $backupRoot
    dwm = (Join-Path $win64 "dwmapi.dll")
    ue4ss = (Join-Path $win64 "ue4ss")
    xinput = (Join-Path $win64 "xinput1_3.dll")
    state = $null
}

Restore-MomentumUE4SSProbe $stage
Write-Host "Original game-directory files restored. Backup was removed after verification."
