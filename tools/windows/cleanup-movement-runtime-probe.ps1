[CmdletBinding()]
param([string]$GameExePath = "")

$ErrorActionPreference = "Stop"

if (-not $GameExePath) {
    foreach ($proc in Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -match "^RoboQuest|Roboquest" }) {
        try {
            $root = Split-Path -Parent $proc.Path
            $candidate = Join-Path $root "RoboQuest\Binaries\Win64\RoboQuest-Win64-Shipping.exe"
            if (Test-Path -LiteralPath $candidate) { $GameExePath = $candidate; break }
            $found = Get-ChildItem -LiteralPath $root -Filter "RoboQuest-Win64-Shipping.exe" -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($found) { $GameExePath = $found.FullName; break }
        } catch {}
    }
}

if (-not $GameExePath) {
    throw "Pass -GameExePath to RoboQuest-Win64-Shipping.exe so the interrupted probe can be restored."
}
$GameExePath = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $GameExePath).Path)
$win64 = Split-Path -Parent $GameExePath
$backupRoot = Join-Path $win64 ".momentum-runtime-probe-backup"
if (-not (Test-Path -LiteralPath $backupRoot)) {
    Write-Host "No Momentum runtime-probe backup exists. Nothing to restore."
    exit 0
}

$statePath = Join-Path $backupRoot "state.json"
if (-not (Test-Path -LiteralPath $statePath)) { throw "Probe backup is missing state.json: $backupRoot" }
$state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
$targetDwm = Join-Path $win64 "dwmapi.dll"
$targetUe4ss = Join-Path $win64 "ue4ss"
$targetXinput = Join-Path $win64 "xinput1_3.dll"

Remove-Item -LiteralPath $targetDwm -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $targetUe4ss -Recurse -Force -ErrorAction SilentlyContinue

if ($state.original_dwmapi -and (Test-Path -LiteralPath (Join-Path $backupRoot "dwmapi.dll"))) {
    Move-Item -LiteralPath (Join-Path $backupRoot "dwmapi.dll") -Destination $targetDwm -Force
}
if ($state.original_ue4ss -and (Test-Path -LiteralPath (Join-Path $backupRoot "ue4ss"))) {
    Move-Item -LiteralPath (Join-Path $backupRoot "ue4ss") -Destination $targetUe4ss -Force
}
if ($state.original_xinput -and (Test-Path -LiteralPath (Join-Path $backupRoot "xinput1_3.dll"))) {
    Move-Item -LiteralPath (Join-Path $backupRoot "xinput1_3.dll") -Destination $targetXinput -Force
}
Remove-Item -LiteralPath $backupRoot -Recurse -Force
Write-Host "Momentum runtime-probe files restored/removed successfully."
