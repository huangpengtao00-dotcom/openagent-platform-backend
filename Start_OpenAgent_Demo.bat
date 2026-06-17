@echo off
setlocal
title OpenAgent Demo Launcher

cd /d "%~dp0"

echo.
echo Starting OpenAgent demo...
echo This safe demo keeps real model calls disabled.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_demo.ps1"

if errorlevel 1 (
  echo.
  echo Failed to start the demo. Please check the message above.
  pause
)

endlocal
