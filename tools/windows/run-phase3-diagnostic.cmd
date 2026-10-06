@echo off
setlocal

set "REPO=%~dp0..\.."
for %%I in ("%REPO%") do set "REPO=%%~fI"
for %%I in ("%REPO%\..") do set "RQROOT=%%~fI"

set "LEGACY=%RQROOT%\LegacyExtract"
set "UASSETGUI=%RQROOT%\UAssetGUI\UAssetGUI.exe"
set "RETOC=%RQROOT%\retoc\retoc.exe"
set "PAKS=%RQROOT%\RoboQuest\Content\Paks"

echo Repo:        %REPO%
echo Legacy:      %LEGACY%
echo UAssetGUI:   %UASSETGUI%
echo retoc:       %RETOC%
echo Game Paks:   %PAKS%
echo.

powershell -ExecutionPolicy Bypass -File "%REPO%\tools\windows\build-phase3-diagnostic.ps1" ^
  -LegacyExtractRoot "%LEGACY%" ^
  -UAssetGUIPath "%UASSETGUI%" ^
  -RetocPath "%RETOC%" ^
  -Install ^
  -GamePaksDir "%PAKS%"

exit /b %ERRORLEVEL%
