@echo off
title DeskSense Launcher
echo ========================================================
echo               Launching DeskSense Workspace
echo ========================================================
echo.

cd /d "%~dp0"

set "PYTHON_EXE=C:\Users\venka\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    set "PYTHON_EXE=python"
)

echo [1/2] Starting DeskSense Vision Engine & Embedded API...
start "DeskSense Backend" "%PYTHON_EXE%" main.py

echo [2/2] Starting DeskSense Dashboard UI...
cd ui
start "DeskSense Dashboard" cmd /k "npm run dev"

echo.
echo ========================================================
echo   DeskSense backend and frontend are starting!
echo   Dashboard URL: http://localhost:5173
echo   Localhost API: http://127.0.0.1:8765
echo ========================================================
echo.
timeout /t 5 >nul
start http://localhost:5173
exit
