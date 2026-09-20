@echo off
REM ============================================================
REM  FALLBACK: make Help -^> Designcenter Help... open our page.
REM  NX reads UGII_HTML_UGDOC for the documentation home page
REM  (libsyss.dll). Setting it replaces the Siemens doc site,
REM  INCLUDING F1 context help.
REM  Undo: help-url-off.cmd
REM ============================================================
setx UGII_HTML_UGDOC "http://127.0.0.1:8765/"
echo.
echo UGII_HTML_UGDOC = http://127.0.0.1:8765/
echo Restart Designcenter, then: Help -^> Designcenter Help...
echo.
pause
