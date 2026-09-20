@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 启动 Designcenter Copilot 本地宿主 ...
start "" http://127.0.0.1:8765/
node server.js 8765
pause
