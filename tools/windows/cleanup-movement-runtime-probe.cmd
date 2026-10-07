@echo off
setlocal EnableExtensions
set "REPO=%~dp0..\.."
for %%I in ("%REPO%") do set "REPO=%%~fI"
powershell -ExecutionPolicy Bypass -File "%REPO%\tools\windows\cleanup-movement-runtime-probe.ps1" %*
exit /b %ERRORLEVEL%
