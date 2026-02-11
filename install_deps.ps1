# PowerShell script to install ML dependencies
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "    Installing ML Dependencies" -ForegroundColor Cyan
Write-Host "    Python 3.13 Compatible" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

try {
    # Check if Python is available
    $pythonVersion = python --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Python not found! Please install Python 3.8+ first." -ForegroundColor Red
        exit 1
    }
    
    Write-Host "✅ Found Python: $pythonVersion" -ForegroundColor Green
    
    # Run the installation script
    Write-Host "🔄 Running dependency installation..." -ForegroundColor Yellow
    python install_dependencies.py
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "🎉 Dependencies installed successfully!" -ForegroundColor Green
        Write-Host "You can now run: python train_model.py" -ForegroundColor Cyan
    } else {
        Write-Host "❌ Installation failed!" -ForegroundColor Red
        exit 1
    }
    
} catch {
    Write-Host "❌ Error: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Press any key to continue..." -ForegroundColor Yellow
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
