@echo off
setlocal

echo.
echo VERIFIED / RETIRED DIAGNOSTIC
echo -----------------------------
echo AAWeapon.GetAffixRowNames() has been verified in a real run:
echo   WF ROW PROBE: GetAffixRowNames returned rows
echo.
echo Do not reinstall this probe.
echo Restore normal production with:
echo   tools\windows\run-weapon-foundry.cmd
echo.
echo The current end-to-end GRAFT transaction probe is:
echo   tools\windows\run-ground-graft-ping-probe.cmd
echo.
exit /b 3
