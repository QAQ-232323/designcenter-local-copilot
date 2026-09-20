@echo off
reg delete "HKCU\Environment" /F /V UGII_HTML_UGDOC >nul 2>&1
echo UGII_HTML_UGDOC removed. Help returns to the Siemens doc site.
pause
