@echo off
setlocal EnableExtensions

set "REPO=%~dp0..\.."
for %%I in ("%REPO%") do set "REPO=%%~fI"
for %%I in ("%REPO%\..") do set "RQROOT=%%~fI"

echo === Weapon Foundry static preflight ===
where python >nul 2>nul
if not errorlevel 1 (
  python "%REPO%\tools\validate_release_candidate.py"
) else (
  py -3 "%REPO%\tools\validate_release_candidate.py"
)
if errorlevel 1 exit /b %ERRORLEVEL%

echo.
echo === Build + install Weapon Foundry ===
powershell -ExecutionPolicy Bypass -File "%REPO%\tools\windows\build-weapon-foundry.ps1" ^
  -LegacyExtractRoot "%RQROOT%\LegacyExtract" ^
  -UAssetGUIPath "%RQROOT%\UAssetGUI\UAssetGUI.exe" ^
  -RetocPath "%RQROOT%\retoc\retoc.exe" ^
  -Install ^
  -GamePaksDir "%RQROOT%\RoboQuest\Content\Paks"

exit /b %ERRORLEVEL%
