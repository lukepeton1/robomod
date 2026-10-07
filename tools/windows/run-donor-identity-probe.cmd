@echo off
setlocal

echo.
echo RETIRED DIAGNOSTIC
echo ------------------
echo The AWeaponAffix world-actor enumeration probe has completed.
echo Runtime result: GetAllActorsOfClass(AWeaponAffix) returned 0 with an affixed weapon present.
echo.
echo Do not reinstall this probe.
echo Restore the normal Weapon Foundry build with:
echo   tools\windows\run-weapon-foundry.cmd
echo.
echo Then collect the next native ownership metadata with:
echo   tools\windows\collect-native-affix-metadata.cmd
echo.
exit /b 3
