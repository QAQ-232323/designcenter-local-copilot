@echo off
REM ============================================================
REM  Fix the NX Skill live bridge so it works behind a TUN/fake-IP proxy.
REM
REM  Problem: the bridge server (inside NX) publishes its remoting objects
REM  using the MACHINE NAME. With Clash/verge TUN mode that name resolves to
REM  a fake IP (198.18.x.x), so the client never connects.
REM  Fix: publish on 127.0.0.1 (already patched in the source) - rebuild here.
REM
REM  NX must be CLOSED: it locks nx_runtime\startup\NxLiveBridgeServer.dll.
REM
REM  After it succeeds: start Designcenter, then
REM     NX Skill -> Start NX Skill Live Bridge
REM ============================================================
setlocal

powershell -NoProfile -Command "if (Get-Process ugraf -ErrorAction SilentlyContinue) { exit 1 } else { exit 0 }"
if errorlevel 1 (
  echo.
  echo [X] Designcenter ^(ugraf.exe^) is still running - it locks the bridge DLL.
  echo     Close Designcenter completely, then run this script again.
  echo.
  pause
  exit /b 1
)

echo Rebuilding the live bridge ^(server + client^) ...
powershell -NoProfile -ExecutionPolicy Bypass -File "E:\AIprojects\nx-skill\scripts\build_dotnet_bridge.ps1"
if errorlevel 1 (
  echo.
  echo [X] Build failed - see the message above.
  pause
  exit /b 1
)

echo.
echo [OK] Bridge rebuilt.
echo      Next: start Designcenter, then click  NX Skill -^> Start NX Skill Live Bridge
echo      Then in the Copilot panel use "Run in current NX session".
echo.
pause
