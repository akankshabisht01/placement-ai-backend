Write-Host "`n════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "     Starting Backend Server" -ForegroundColor Cyan
Write-Host "════════════════════════════════════════`n" -ForegroundColor Cyan

# Change to backend directory
Set-Location "d:\App\placement-AI\backend"

Write-Host "📂 Working Directory: $(Get-Location)" -ForegroundColor Yellow
Write-Host "🐍 Python: venv\Scripts\python.exe`n" -ForegroundColor Yellow

# Activate virtual environment and run
& ".\venv\Scripts\python.exe" "app.py"

# Keep window open if there's an error
if ($LASTEXITCODE -ne 0) {
    Write-Host "`n❌ Server exited with error code: $LASTEXITCODE" -ForegroundColor Red
    Read-Host "Press Enter to close"
}
