@echo off
setlocal
title OpenAgent Frontend - keep open
cd /d "%~dp0frontend"
echo [OpenAgent Frontend] http://127.0.0.1:5173
echo Keep this window open during the demo.
npm.cmd run dev -- --host 127.0.0.1 --port 5173
pause
endlocal