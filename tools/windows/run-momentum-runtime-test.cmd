@echo off
setlocal EnableExtensions
set "REPO=%~dp0..\.."
for %%I in ("%REPO%") do set "REPO=%%~fI"
powershell -ExecutionPolicy Bypass -File "%REPO%\tools\windows\run-momentum-runtime-test.ps1" %*
exit /b %ERRORLEVEL%
