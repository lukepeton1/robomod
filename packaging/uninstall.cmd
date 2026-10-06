@echo off
setlocal EnableExtensions

set "PAKS=%~1"
if not "%PAKS%"=="" goto :havepath

set "STEAM=%ProgramFiles(x86)%\Steam\steamapps\common\Roboquest\RoboQuest\Content\Paks"
if exist "%STEAM%" (
  set "PAKS=%STEAM%"
  goto :havepath
)

echo Weapon Foundry uninstaller
echo.
set /p PAKS=Roboquest Paks folder: 

:havepath
if not exist "%PAKS%" (
  echo ERROR: Paks folder not found:
  echo   %PAKS%
  exit /b 1
)

set "MODS=%PAKS%\Mods"
for %%F in (WeaponFoundry_P.pak WeaponFoundry_P.ucas WeaponFoundry_P.utoc) do (
  if exist "%MODS%\%%F" (
    del /f /q "%MODS%\%%F"
    echo Removed %%F
  )
)

echo.
echo Weapon Foundry removed.
exit /b 0
