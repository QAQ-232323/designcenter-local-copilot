@echo off
REM ============================================================
REM  Register our custom NX directory (UGII_USER_DIR).
REM  Effect after restarting Designcenter:
REM    1) "NX Skill" cascade appears in the menubar, right of Help
REM    2) "Copilot" toolbar becomes available in Customize,
REM       containing the working local-Copilot button
REM       (the built-in UG_APP_COPILOT is disabled without
REM        the Designcenter X entitlement)
REM  Undo: user-dir-off.cmd
REM  NOTE: NX searches UGII_USER_DIR by default (it is the first
REM        entry of UGII/menus/ug_custom_dirs.dat), so this does
REM        NOT touch your NXMCP UGII_CUSTOM_DIRECTORY_FILE entry.
REM ============================================================
setx UGII_USER_DIR "E:\AIprojects\nx-skill\nx_runtime"
echo.
echo UGII_USER_DIR = E:\AIprojects\nx-skill\nx_runtime
echo Restart Designcenter, then either:
echo   * menubar: Help ... "NX Skill" -^> "Copilot (Local)..."
echo   * hotkey : Ctrl+Alt+Shift+C
echo   * left toolbar: Customize -^> Toolbars -^> tick "Copilot"
echo     then drag it to the far left edge
echo.
pause
