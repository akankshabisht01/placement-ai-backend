# Quick Deployment Commands

## Push to GitHub
```powershell
cd d:\App\placement-AI\backend

# If first time
git init
git add .
git commit -m "Initial commit for Railway deployment"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/placement-ai-backend.git
git push -u origin main

# For updates
git add .
git commit -m "Update backend"
git push
```

## Test Local Before Deploy
```powershell
# Activate venv
.\venv\Scripts\Activate.ps1

# Test with gunicorn (same as Railway)
gunicorn app:app --bind 0.0.0.0:5000 --timeout 300 --workers 1

# Test health endpoint
curl http://localhost:5000/api/health
```

## After Railway Deployment

### Test endpoints
```powershell
# Replace YOUR-APP with your Railway app name
$API_URL = "https://your-app-name.up.railway.app"

# Health check
curl "$API_URL/api/health"

# DB health
curl "$API_URL/api/db-health"

# Get domains
curl "$API_URL/api/domains"
```

### Update Frontend
Update your frontend API base URL to:
```
https://your-app-name.up.railway.app
```

## Files Created for Deployment

✅ `.gitignore` - Excludes venv, cache, .env
✅ `Procfile` - Tells Railway how to start app
✅ `runtime.txt` - Specifies Python version
✅ `railway.json` - Railway configuration
✅ `nixpacks.toml` - Build configuration for PyTorch
✅ `RAILWAY_DEPLOYMENT.md` - Complete guide

## What NOT to commit
- `venv/` folder (400MB+)
- `__pycache__/` folders
- `.env` file (add variables manually on Railway)
- `*.log` files
- `*.pkl` model files are OK to commit (needed for ML)

## Railway URL
After deployment, your API will be at:
`https://[your-project-name].up.railway.app`

Save this URL for your frontend configuration!
