@echo off
setlocal

set "REPO=%~dp0..\.."
for %%I in ("%REPO%") do set "REPO=%%~fI"
for %%I in ("%REPO%\..") do set "RQROOT=%%~fI"

powershell -ExecutionPolicy Bypass -File "%REPO%\tools\windows\collect-legacy-handoff.ps1" ^
  -ExtractRoot "%RQROOT%\LegacyExtract" ^
  -UAssetGUIPath "%RQROOT%\UAssetGUI\UAssetGUI.exe"

exit /b %ERRORLEVEL%
