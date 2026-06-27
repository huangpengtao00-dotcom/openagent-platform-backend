@echo off
setlocal
title OpenAgent Demo Launcher
cd /d "%~dp0"

if exist "Start_OpenAgent_Demo_Stable.bat" (
  call "Start_OpenAgent_Demo_Stable.bat"
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_demo.ps1" -KeepDemoData -NoBrowser
  echo.
  echo Open http://127.0.0.1:5173/ in external Chrome or Edge.
  pause
)

endlocal