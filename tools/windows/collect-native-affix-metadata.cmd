@echo off
setlocal EnableExtensions

set "REPO=%~dp0..\.."
for %%I in ("%REPO%") do set "REPO=%%~fI"
for %%I in ("%REPO%\..") do set "RQROOT=%%~fI"

set "BINROOT=%RQROOT%\RoboQuest\Binaries\Win64"
set "OUT=%REPO%\handoff\native-affix-metadata.json"

if not exist "%BINROOT%" (
  echo Roboquest binary directory not found:
  echo   %BINROOT%
  exit /b 2
)

if not exist "%REPO%\handoff" mkdir "%REPO%\handoff"

where python >nul 2>nul
if not errorlevel 1 (
  python "%REPO%\tools\scan_native_affix_metadata.py" "%BINROOT%" --output "%OUT%"
) else (
  py -3 "%REPO%\tools\scan_native_affix_metadata.py" "%BINROOT%" --output "%OUT%"
)
if errorlevel 1 exit /b %ERRORLEVEL%

echo.
echo Native affix metadata collection complete:
echo   %OUT%
exit /b 0
