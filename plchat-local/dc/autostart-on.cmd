@echo off
REM ============================================================
REM  Start the local Copilot host together with Designcenter / NX.
REM
REM  Installs host_watchdog.vbs (this folder) to run at logon:
REM  the watchdog polls http://127.0.0.1:<port>/api/ping every 3s
REM  and, only while ugraf.exe (= Designcenter / NX, any release)
REM  is running, starts "node server.js <port>" if the host is down.
REM  It never stops a host that is already up, and never touches
REM  Designcenter. Undo: autostart-off.cmd
REM
REM  It also removes the older no-script autostart entry (Run key
REM  "Designcenter Local Copilot Host") if a previous version of
REM  this script installed it - that one started the host at logon
REM  regardless of Designcenter, which is the opposite of what we
REM  want now.
REM
REM  ANTIVIRUS: some engines classify a VBScript that queries
REM  processes and launches a hidden program as a downloader
REM  (Huorong deleted an earlier copy as TrojanDownloader/VBS.Agent.dd
REM  on 2026-09-20 - false positive). If yours does, allow
REM  host_watchdog.vbs, or fall back to the Run-key autostart.
REM
REM  ASCII only: a .cmd is parsed with the console code page, so
REM  non-ASCII text here would be mangled. Paths are passed through
REM  %~dp0 and never written into this file; the one generated file
REM  that needs the repo path (the Startup launcher) stays ASCII by
REM  resolving it through the environment variable DC_COPILOT_WATCHDOG.
REM ============================================================
setlocal
set HERE=%~dp0
set CONF=%HERE%host_watchdog.conf
set WATCHDOG=%~dp0host_watchdog.vbs
set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set LAUNCHER=%STARTUP%\designcenter-local-copilot.vbs
set RUNKEY=HKCU\Software\Microsoft\Windows\CurrentVersion\Run
set VNAME=Designcenter Local Copilot Host

REM --- 1) locate node.exe (this machine keeps it outside Program Files) ---
set NODE=
for /f "delims=" %%i in ('where node 2^>nul') do if not defined NODE set "NODE=%%i"
if not defined NODE (
  echo [X] node.exe was not found in PATH. Install Node.js first.
  pause
  exit /b 1
)

REM --- 2) remove the previous Run-key autostart, if present ---
reg delete "%RUNKEY%" /v "%VNAME%" /f >nul 2>nul

REM --- 3) watchdog config (ASCII; the repo path is derived by the .vbs) ---
> "%CONF%"  echo # written by autostart-on.cmd - ASCII values only
>>"%CONF%" echo # requireDc=1 = start the host only while ugraf.exe runs (set 0 to keep it always on)
>>"%CONF%" echo node=%NODE%
>>"%CONF%" echo port=8765
>>"%CONF%" echo requireDc=1
>>"%CONF%" echo intervalMs=3000

REM --- 4) logon launcher in the Startup folder ---
setx DC_COPILOT_WATCHDOG "%WATCHDOG%" >nul
set DC_COPILOT_WATCHDOG=%WATCHDOG%
> "%LAUNCHER%"  echo Set sh = CreateObject("WScript.Shell")
>>"%LAUNCHER%" echo sh.Run "wscript.exe """ ^& sh.ExpandEnvironmentStrings("%%DC_COPILOT_WATCHDOG%%") ^& """", 0, False

REM --- 5) start it now, unless it is already watching ---
set RUNNING=
for /f "delims=" %%i in ('powershell -NoProfile -Command "(Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'wscript.exe' -and $_.CommandLine -like '*host_watchdog.vbs*' } | Measure-Object).Count"') do set RUNNING=%%i
if "%RUNNING%"=="0" (
  start "" wscript.exe "%WATCHDOG%"
  echo [OK] watchdog started now
) else (
  echo [OK] watchdog was already running
)

echo.
echo node     = %NODE%
echo server   = %HERE%..\server.js
echo watchdog = %WATCHDOG%
echo config   = %CONF%   (requireDc=1)
echo logon    = %LAUNCHER%
echo.
echo From now on: start Designcenter / NX -^> the host is up a few
echo seconds later. Close Designcenter and the host stays up (it is
echo only *started* with Designcenter). The watchdog also restarts the
echo host if it dies while Designcenter is open.
echo Undo with: autostart-off.cmd
echo.
pause
