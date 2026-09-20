@echo off
reg delete "HKCU\Environment" /F /V NX_SKILL_WORKSPACE >nul 2>&1
echo NX_SKILL_WORKSPACE removed. Restart Designcenter.
pause
