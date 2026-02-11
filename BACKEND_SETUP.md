# Backend Setup Guide

## ⚠️ IMPORTANT: Virtual Environment

This backend uses a **virtual environment** located at `backend\.venv`.

**ALWAYS** start the server using one of the startup scripts to ensure the correct environment is used.

## 🚀 Quick Start

### Option 1: Using Batch File (Recommended for Windows)
```bash
cd backend
start_backend.bat
```

### Option 2: Using PowerShell Script
```powershell
cd backend
.\start_backend.ps1
```

### Option 3: Manual Start (Advanced)
```bash
cd backend
.\.venv\Scripts\activate
python app.py
```

## 📦 Required Packages

The backend requires these packages for video translation:
- `google-generativeai` - Gemini AI for text optimization
- `moviepy` - Video/audio processing
- `openai-whisper` - Speech recognition
- `deep-translator` - Language translation
- `elevenlabs` - Text-to-speech
- `yt-dlp` - YouTube video downloading

**The startup scripts automatically check and install missing packages!**

## 🔧 Manual Package Installation

If you need to install packages manually:

```bash
cd backend
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## ❌ Common Issues

### Issue: "ModuleNotFoundError: No module named 'google.generativeai'"

**Cause**: The backend is running without the virtual environment activated.

**Solution**: 
1. Stop the backend server (Ctrl+C)
2. Use one of the startup scripts above
3. Never run `python app.py` directly from outside the backend folder

### Issue: "Packages keep disappearing"

**Cause**: You're switching between different Python environments.

**Solution**: 
- **ALWAYS** use the startup scripts (`start_backend.bat` or `start_backend.ps1`)
- **NEVER** run `python app.py` from the root folder
- **NEVER** activate the root `.venv` instead of backend's `.venv`

## 🔍 Verify Installation

To check if packages are installed correctly:

```bash
cd backend
.\.venv\Scripts\python.exe -c "import google.generativeai, moviepy, whisper, deep_translator, elevenlabs, yt_dlp; print('✅ All packages OK!')"
```

## 📍 Environment Structure

```
placement-AI-1/
├── .venv/                    ❌ Root venv (DO NOT USE for backend)
└── backend/
    ├── .venv/                ✅ Backend venv (USE THIS)
    ├── app.py
    ├── start_backend.bat     ✅ Use this!
    ├── start_backend.ps1     ✅ Or this!
    └── requirements.txt
```

## 🎯 Best Practices

1. **Always start from the backend folder**
2. **Always use the startup scripts**
3. **Never mix virtual environments**
4. **If packages are missing, the startup script will auto-install them**

## 📝 Notes

- The backend virtual environment is at: `backend\.venv`
- Backend runs on: `http://localhost:5000`
- MongoDB connection required (set in `.env`)
- Gmail SMTP configured for OTP service

---

**Last Updated**: November 11, 2025
