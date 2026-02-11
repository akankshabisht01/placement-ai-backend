@echo off
echo.
echo 🚀 Gmail App Password Setup Guide
echo =====================================
echo.
echo ⚠️  CRITICAL: You must set up a Gmail App Password to send OTPs!
echo.
echo 📧 Step-by-Step Instructions:
echo.
echo 1. Go to Google Account Settings:
echo    https://myaccount.google.com/
echo.
echo 2. Sign in with: placementprediction007@gmail.com
echo.
echo 3. Navigate to Security (left sidebar)
echo.
echo 4. Enable 2-Step Verification:
echo    - Click "2-Step Verification"
echo    - Follow the setup process if not already enabled
echo.
echo 5. Generate App Password:
echo    - Go back to Security
echo    - Click "2-Step Verification"
echo    - Scroll down to "App passwords"
echo    - Click "App passwords"
echo    - Select "Mail" from dropdown
echo    - Click "Generate"
echo.
echo 6. Copy the 16-character password (format: xxxx xxxx xxxx xxxx)
echo.
echo 7. Update .env file:
echo    - Open: backend\.env
echo    - Find: EMAIL_PASSWORD=Launchpad03
echo    - Replace with: EMAIL_PASSWORD=your-16-char-app-password
echo    - Remove spaces from the app password
echo.
echo 📝 Example:
echo    If Google gives you: abcd efgh ijkl mnop
echo    Set in .env: EMAIL_PASSWORD=abcdefghijklmnop
echo.
echo 8. Restart the backend server after updating .env
echo.
echo ⚠️  IMPORTANT NOTES:
echo - Do NOT use your regular Gmail password
echo - App Password must be exactly 16 characters
echo - Remove all spaces from the App Password
echo - Make sure 2-Step Verification is enabled first
echo.
echo 🔒 Security: App passwords are safer than regular passwords
echo           for automated applications like this OTP system.
echo.
pause