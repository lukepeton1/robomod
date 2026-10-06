@echo off
setlocal

set "REPO=%~dp0..\.."
for %%I in ("%REPO%") do set "REPO=%%~fI"

powershell -ExecutionPolicy Bypass -File "%REPO%\tools\windows\package-release.ps1"

exit /b %ERRORLEVEL%
