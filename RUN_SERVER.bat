@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo.
echo ========================================
echo   Starting Backend Server
echo ========================================
echo.
echo Working Directory: %CD%
echo Python: venv\Scripts\python.exe
echo.

set PYTHONIOENCODING=utf-8
venv\Scripts\python.exe app.py

if errorlevel 1 (
    echo.
    echo ========================================
    echo   Server exited with error!
    echo ========================================
    pause
)
