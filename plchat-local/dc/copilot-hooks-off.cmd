@echo off
for %%V in (UGII_PLCHATUI_LOCAL_APP_URL UGII_PLCHAT_CUSTOM_BACKEND_URL) do reg delete "HKCU\Environment" /F /V %%V >nul 2>&1
echo Copilot hook variables removed. Restart Designcenter.
pause
