@echo off
setlocal EnableExtensions

set "PAKS=%~1"
if not "%PAKS%"=="" goto :havepath

set "STEAM=%ProgramFiles(x86)%\Steam\steamapps\common\Roboquest\RoboQuest\Content\Paks"
if exist "%STEAM%" (
  set "PAKS=%STEAM%"
  goto :havepath
)

echo Weapon Foundry installer
echo.
echo Pass the Roboquest Paks folder as the first argument, for example:
echo   install.cmd "C:\Program Files (x86)\Steam\steamapps\common\Roboquest\RoboQuest\Content\Paks"
echo.
set /p PAKS=Roboquest Paks folder: 

:havepath
if not exist "%PAKS%" (
  echo ERROR: Paks folder not found:
  echo   %PAKS%
  exit /b 1
)

set "MODS=%PAKS%\Mods"
if not exist "%MODS%" mkdir "%MODS%"

for %%F in (WeaponFoundry_P.pak WeaponFoundry_P.ucas WeaponFoundry_P.utoc) do (
  if not exist "%~dp0%%F" (
    echo ERROR: Missing %%F next to installer.
    exit /b 1
  )
  copy /y "%~dp0%%F" "%MODS%\%%F" >nul
  echo Installed %%F
)

echo.
echo Weapon Foundry installed to:
echo   %MODS%
exit /b 0
