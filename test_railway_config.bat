@echo off
echo ====================================
echo  Testing Backend with Gunicorn
echo  (Same as Railway production)
echo ====================================
echo.

REM Check if venv exists
if not exist "venv\" (
    echo ERROR: venv folder not found!
    echo Run: python -m venv venv
    pause
    exit /b 1
)

REM Activate venv
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Check if gunicorn is installed
echo Checking gunicorn installation...
pip show gunicorn >nul 2>&1
if errorlevel 1 (
    echo Installing gunicorn...
    pip install gunicorn
)

echo.
echo Starting server with Gunicorn...
echo Server will run on: http://localhost:5000
echo Press Ctrl+C to stop
echo.

REM Start gunicorn (same config as Railway)
gunicorn app:app --bind 0.0.0.0:5000 --timeout 300 --workers 2 --threads 4
