@echo off
setlocal

set "REPO=%~dp0..\.."
for %%I in ("%REPO%") do set "REPO=%%~fI"
for %%I in ("%REPO%\..") do set "RQROOT=%%~fI"

powershell -ExecutionPolicy Bypass -File "%REPO%\tools\windows\build-phase2-prototype.ps1" ^
  -LegacyExtractRoot "%RQROOT%\LegacyExtract" ^
  -UAssetGUIPath "%RQROOT%\UAssetGUI\UAssetGUI.exe" ^
  -RetocPath "%RQROOT%\retoc\retoc.exe" ^
  -Install ^
  -GamePaksDir "%RQROOT%\RoboQuest\Content\Paks"

exit /b %ERRORLEVEL%
