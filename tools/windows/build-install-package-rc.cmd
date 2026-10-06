@echo off
setlocal EnableExtensions

set "REPO=%~dp0..\.."
for %%I in ("%REPO%") do set "REPO=%%~fI"
for %%I in ("%REPO%\..") do set "RQROOT=%%~fI"

echo === Weapon Foundry RC build ===
echo Repo:      %REPO%
echo Game root: %RQROOT%
echo.

call "%REPO%\tools\windows\run-weapon-foundry.cmd"
if errorlevel 1 exit /b %ERRORLEVEL%

echo.
echo === Packaging release ZIP ===
call "%REPO%\tools\windows\package-weapon-foundry.cmd"
if errorlevel 1 exit /b %ERRORLEVEL%

echo.
echo Weapon Foundry release candidate is built, installed, and packaged.
echo See:
echo   %REPO%\dist
exit /b 0
