@echo off
cd /d "%~dp0"
echo.
echo ========================================
echo    Starting Backend Server
echo ========================================
echo.
echo Python: venv\Scripts\python.exe
echo Port: 5000
echo.
set PYTHONIOENCODING=utf-8
venv\Scripts\python.exe app.py
pause
