@echo off
setlocal
title OpenAgent One-Click Local Demo
cd /d "%~dp0"
echo.
echo [OpenAgent] Starting local demo without Docker, WSL, Redis, or virtualization.
echo [OpenAgent] API:      http://127.0.0.1:8000
echo [OpenAgent] Frontend: http://127.0.0.1:5173
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_demo.ps1" -KeepDemoData
echo.
echo [OpenAgent] If the browser did not open, open http://127.0.0.1:5173/
pause
endlocal
