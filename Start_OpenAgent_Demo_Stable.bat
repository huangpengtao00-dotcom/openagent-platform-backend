@echo off
setlocal
title OpenAgent Demo Stable Launcher
cd /d "%~dp0"
echo.
echo [OpenAgent] Stable demo mode
echo [OpenAgent] Two service windows will open. Keep both windows open during the demo.
echo.
start "OpenAgent API - keep open" "%~dp0Start_OpenAgent_API_Visible.bat"
timeout /t 3 /nobreak >nul
start "OpenAgent Frontend - keep open" "%~dp0Start_OpenAgent_Frontend_Visible.bat"
set "DEMO_URL=http://127.0.0.1:5173/"
set "EDGE_EXE="
if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" set "EDGE_EXE=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
if not defined EDGE_EXE if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" set "EDGE_EXE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
timeout /t 5 /nobreak >nul
if defined EDGE_EXE (
  echo [OpenAgent] Opening demo in Microsoft Edge...
  start "OpenAgent Demo Edge" "%EDGE_EXE%" --new-window "%DEMO_URL%"
) else (
  echo [OpenAgent] Microsoft Edge was not found. Opening the demo with the default browser...
  start "" "%DEMO_URL%"
)
echo.
echo [OpenAgent] API:      http://127.0.0.1:8000
echo [OpenAgent] Frontend: http://127.0.0.1:5173
echo.
echo If the browser did not open automatically, open http://127.0.0.1:5173/ in Edge.
echo Do not open the demo inside Codex's in-app browser for the interview.
echo.
pause
endlocal
