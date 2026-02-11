@echo off
echo ========================================
echo Starting Backend Server
echo ========================================
echo.

REM Activate the backend's virtual environment
call .venv\Scripts\activate.bat

REM Check if packages are installed
echo Checking required packages...
python -c "import google.generativeai, moviepy, whisper, deep_translator, elevenlabs, yt_dlp" 2>nul
if errorlevel 1 (
    echo.
    echo ERROR: Required packages not found!
    echo Installing required packages...
    pip install google-generativeai moviepy openai-whisper deep-translator elevenlabs yt-dlp
    echo.
)

echo.
echo Starting Flask server...
echo Backend will be available at: http://localhost:5000
echo.
echo Press Ctrl+C to stop the server
echo ========================================
echo.

python app.py
