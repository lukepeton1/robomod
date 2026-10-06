@echo off
setlocal EnableExtensions

set "REPO=%~dp0..\.."
for %%I in ("%REPO%") do set "REPO=%%~fI"
for %%I in ("%REPO%\..") do set "RQROOT=%%~fI"
set "HANDOFF=%REPO%\handoff\legacy-assets"

echo === Collect expanded Weapon Foundry handoff ===
powershell -ExecutionPolicy Bypass -File "%REPO%\tools\windows\collect-legacy-handoff.ps1" ^
  -ExtractRoot "%RQROOT%\LegacyExtract" ^
  -UAssetGUIPath "%RQROOT%\UAssetGUI\UAssetGUI.exe"
if errorlevel 1 exit /b %ERRORLEVEL%

echo.
echo === Analyze donor / tooltip / affix seams ===
where python >nul 2>nul
if not errorlevel 1 (
  python "%REPO%\tools\analyze_donor_handoff.py" "%HANDOFF%" --output "%HANDOFF%\donor-affix-seams.json"
) else (
  py -3 "%REPO%\tools\analyze_donor_handoff.py" "%HANDOFF%" --output "%HANDOFF%\donor-affix-seams.json"
)
if errorlevel 1 exit /b %ERRORLEVEL%

echo.
echo Expanded handoff and donor seam analysis complete.
echo ZIP:
echo   %HANDOFF%.zip
echo Analysis:
echo   %HANDOFF%\donor-affix-seams.json
exit /b 0
