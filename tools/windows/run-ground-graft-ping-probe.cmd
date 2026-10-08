@echo off
setlocal

echo.
echo RETIRED DIAGNOSTIC
echo ------------------
echo The BP_APlayer-hosted ground GRAFT ping probe is retired.
echo It reached a real runtime ClassConstructor failure for BP_APlayer_C.
echo.
echo Do not reinstall the BP_APlayer overlay.
echo Restore normal production with:
echo   tools\windows\run-weapon-foundry.cmd
echo.
echo Then use the safe-host diagnostic:
echo   tools\windows\run-ground-graft-safehost-probe.cmd
echo.
exit /b 3
