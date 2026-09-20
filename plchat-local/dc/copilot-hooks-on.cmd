@echo off
REM ============================================================
REM  Point the OFFICIAL Copilot panel at our local page/backend.
REM  Only useful if the built-in Copilot command is enabled
REM  (needs the Designcenter X entitlement). On a classic install
REM  the command is inert and these variables do nothing.
REM  Undo: copilot-hooks-off.cmd
REM ============================================================
setx UGII_PLCHATUI_LOCAL_APP_URL "http://127.0.0.1:8765/"
setx UGII_PLCHAT_CUSTOM_BACKEND_URL "http://127.0.0.1:8765/api/ask"
echo.
echo UGII_PLCHATUI_LOCAL_APP_URL    = http://127.0.0.1:8765/
echo UGII_PLCHAT_CUSTOM_BACKEND_URL = http://127.0.0.1:8765/api/ask
echo Restart Designcenter and open Help -^> Copilot...
echo.
pause
