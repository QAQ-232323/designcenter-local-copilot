@echo off
REM ============================================================
REM  Undo autostart-on.cmd: stop the watchdog and remove the logon
REM  launcher, the environment variable and the generated config.
REM  Also removes the older Run-key autostart entry, in case it is
REM  still there from a previous version of the script.
REM
REM  The host process itself is left running - close its window if
REM  you want it gone now. Designcenter is untouched either way.
REM
REM  ASCII only, same reason as autostart-on.cmd.
REM ============================================================
setlocal
set HERE=%~dp0
set CONF=%HERE%host_watchdog.conf
set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set LAUNCHER=%STARTUP%\designcenter-local-copilot.vbs
set RUNKEY=HKCU\Software\Microsoft\Windows\CurrentVersion\Run
set VNAME=Designcenter Local Copilot Host

REM --- 1) stop the running watchdog ---
set KILLED=
for /f "delims=" %%i in ('powershell -NoProfile -Command "(Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'wscript.exe' -and $_.CommandLine -like '*host_watchdog.vbs*' } | Measure-Object).Count"') do set KILLED=%%i
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'wscript.exe' -and $_.CommandLine -like '*host_watchdog.vbs*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo [OK] stopped watchdog processes: %KILLED%

REM --- 2) remove the logon launcher ---
if exist "%LAUNCHER%" (
  del "%LAUNCHER%"
  echo [OK] removed %LAUNCHER%
) else (
  echo [--] no logon launcher at %LAUNCHER%
)

REM --- 3) drop the environment variable, the generated config, and any Run key ---
reg delete HKCU\Environment /F /V DC_COPILOT_WATCHDOG >nul 2>nul
if exist "%CONF%" del "%CONF%"
reg delete "%RUNKEY%" /v "%VNAME%" /f >nul 2>nul
echo [OK] removed DC_COPILOT_WATCHDOG, host_watchdog.conf and any Run-key entry

echo.
echo The host process (if any) is still running. Designcenter is untouched.
echo.
pause
