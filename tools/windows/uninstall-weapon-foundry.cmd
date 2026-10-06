@echo off
setlocal

set "REPO=%~dp0..\.."
for %%I in ("%REPO%") do set "REPO=%%~fI"
for %%I in ("%REPO%\..") do set "RQROOT=%%~fI"

set "MODS=%RQROOT%\RoboQuest\Content\Paks\Mods"
echo Removing Weapon Foundry from:
echo   %MODS%
echo.

for %%F in (WeaponFoundry_P.pak WeaponFoundry_P.ucas WeaponFoundry_P.utoc) do (
  if exist "%MODS%\%%F" (
    del /f /q "%MODS%\%%F"
    echo Removed %%F
  )
)

echo Weapon Foundry uninstall complete.
exit /b 0
