@echo off
setlocal EnableExtensions
set "REPO=%~dp0..\.."
for %%I in ("%REPO%") do set "REPO=%%~fI"
powershell -ExecutionPolicy Bypass -File "%REPO%\tools\windows\collect-movement-thunk-handoff.ps1" %*
exit /b %ERRORLEVEL%
