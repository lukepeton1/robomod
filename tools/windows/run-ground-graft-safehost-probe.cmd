@echo off
setlocal

echo RETIRED DIAGNOSTIC
echo ------------------
echo The GetInteractSound mutation probe loaded but did not produce observable affix transfer.
echo It does not report whether its donor filter or RPC path executed.
echo.
echo Use the new visible, read-only gate diagnostic:
echo   tools\windows\run-ground-graft-gate-probe.cmd
echo.
echo Restore normal game interaction with:
echo   tools\windows\run-weapon-foundry.cmd
exit /b 3
