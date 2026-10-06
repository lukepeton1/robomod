@echo off
setlocal EnableExtensions

set "REPO=%~dp0..\.."
for %%I in ("%REPO%") do set "REPO=%%~fI"
for %%I in ("%REPO%\..") do set "RQROOT=%%~fI"

echo === Weapon Foundry RC build ===
echo Repo:      %REPO%
echo Game root: %RQROOT%
echo.

echo === Static RC preflight ===
where python >nul 2>nul
if not errorlevel 1 (
  python "%REPO%\tools\validate_release_candidate.py"
) else (
  py -3 "%REPO%\tools\validate_release_candidate.py"
)
if errorlevel 1 exit /b %ERRORLEVEL%

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
