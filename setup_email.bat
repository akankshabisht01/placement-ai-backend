@echo off
echo 🚀 Setting up OTP Email Service...

REM Install required Python packages if not already installed
echo 📦 Installing Python dependencies...
pip install python-dotenv

echo ✅ Dependencies installed!

echo.
echo 📧 EMAIL SETUP INSTRUCTIONS:
echo ==================================
echo.
echo To enable OTP email sending, you need to set up Gmail App Password:
echo.
echo 1. Go to your Google Account (https://myaccount.google.com/)
echo 2. Navigate to Security → 2-Step Verification → App passwords
echo 3. Generate an App Password for 'Mail'
echo 4. Copy the generated 16-character password
echo 5. Open backend\.env file
echo 6. Replace 'your-gmail-app-password-here' with your App Password
echo.
echo ⚠️  IMPORTANT: Use App Password, NOT your regular Gmail password!
echo.
echo 📝 Example .env configuration:
echo EMAIL_PASSWORD=abcd efgh ijkl mnop
echo.
echo ✅ After setup, restart your backend server for changes to take effect.
pause