# PowerShell script to start backend server
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Starting Backend Server" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Activate the backend's virtual environment
& ".\\.venv\Scripts\Activate.ps1"

# Check if packages are installed
Write-Host "Checking required packages..." -ForegroundColor Yellow
try {
    python -c "import google.generativeai, moviepy, whisper, deep_translator, elevenlabs, yt_dlp" 2>$null
    if ($LASTEXITCODE -ne 0) { throw }
    Write-Host "✅ All required packages found!" -ForegroundColor Green
} catch {
    Write-Host ""
    Write-Host "⚠️  Required packages not found!" -ForegroundColor Red
    Write-Host "Installing required packages..." -ForegroundColor Yellow
    pip install google-generativeai moviepy openai-whisper deep-translator elevenlabs yt-dlp
    Write-Host ""
}

Write-Host ""
Write-Host "Starting Flask server..." -ForegroundColor Green
Write-Host "Backend will be available at: http://localhost:5000" -ForegroundColor Green
Write-Host ""
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

python app.py
