@echo off
REM Undo: stop loading our custom NX directory.
reg delete "HKCU\Environment" /F /V UGII_USER_DIR >nul 2>&1
echo UGII_USER_DIR removed. Restart Designcenter.
pause
