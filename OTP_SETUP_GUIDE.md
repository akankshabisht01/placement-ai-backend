# 📧 OTP Email Service Setup Guide

## 🎯 Overview
This system sends real OTP emails from `placementprediction007@gmail.com` and verifies them through your backend API.

## 🛠️ Setup Instructions

### 1. Gmail App Password Setup
Since we're using Gmail SMTP, you need to create an App Password:

1. **Go to Google Account Settings**
   - Visit: https://myaccount.google.com/
   - Sign in with `placementprediction007@gmail.com`

2. **Enable 2-Step Verification**
   - Go to Security → 2-Step Verification
   - Follow the setup process if not already enabled

3. **Generate App Password**
   - Go to Security → 2-Step Verification → App passwords
   - Select "Mail" as the app
   - Generate password (16 characters)

4. **Update Environment Variables**
   - Open `backend/.env` file
   - Replace `your-gmail-app-password-here` with the generated password
   ```
   EMAIL_PASSWORD=abcd efgh ijkl mnop
   ```

### 2. Backend Setup
The backend is already configured with:
- ✅ OTP Service (`utils/otp_service.py`)
- ✅ API Endpoints (`/api/send-otp`, `/api/verify-otp`)
- ✅ Email Templates (HTML + Plain text)

### 3. Frontend Integration
The React app now uses real API calls:
- ✅ Send OTP via `fetch('/api/send-otp')`
- ✅ Verify OTP via `fetch('/api/verify-otp')`
- ✅ Error handling and user feedback

## 🚀 How to Start

### Backend
```bash
cd backend
pip install -r requirements.txt
python app.py
```

### Frontend
```bash
cd placement-prediction-system
npm start
```

## 📧 Email Features

### Professional Email Template
- **Beautiful HTML Design** with gradients and styling
- **Company Branding** with placement prediction theme
- **Security Information** with expiry and usage guidelines
- **Plain Text Alternative** for compatibility

### Security Features
- **5-minute OTP expiry** for security
- **3 attempt limit** to prevent abuse
- **Automatic cleanup** of expired OTPs
- **Email validation** and sanitization

### OTP System
- **6-digit numeric OTP** easy to read and enter
- **Real-time verification** with detailed error messages
- **Attempt tracking** with remaining tries feedback

## 🔧 Technical Details

### API Endpoints

#### Send OTP
```http
POST /api/send-otp
Content-Type: application/json

{
  "email": "user@example.com",
  "firstName": "John"
}
```

#### Verify OTP
```http
POST /api/verify-otp
Content-Type: application/json

{
  "email": "user@example.com",
  "otp": "123456"
}
```

### Error Handling
- Network errors with backend connection status
- Invalid email format validation
- OTP expiry and attempt limit enforcement
- User-friendly error messages

## 🎨 Email Template Preview

The OTP email includes:
- **Header**: Placement Prediction System branding
- **OTP Display**: Large, prominent 6-digit code
- **Instructions**: Clear usage guidelines
- **Security Info**: Expiry time and security warnings
- **Footer**: Professional automated message disclaimer

## 🔒 Security Considerations

1. **App Password Storage**: Store securely in `.env` file
2. **OTP Expiry**: 5-minute window for security
3. **Attempt Limiting**: Max 3 attempts per OTP
4. **Email Validation**: Sanitize and validate all inputs
5. **HTTPS**: Use HTTPS in production for API calls

## 🐛 Troubleshooting

### Common Issues:

1. **"Authentication failed"**
   - Check if 2-Step Verification is enabled
   - Verify App Password is correct (16 characters)
   - Ensure using App Password, not regular password

2. **"Network error"**
   - Check if backend server is running (port 5000)
   - Verify CORS is properly configured
   - Check console for detailed error messages

3. **"OTP not received"**
   - Check spam/junk folder
   - Verify email address is correct
   - Check backend logs for sending errors

### Testing Commands:
```bash
# Test backend health
curl http://localhost:5000/api/health

# Test OTP sending
curl -X POST http://localhost:5000/api/send-otp \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","firstName":"Test"}'
```

## ✅ Production Checklist

- [ ] Gmail App Password configured
- [ ] Environment variables set
- [ ] Backend server running
- [ ] Frontend connecting to correct API URL
- [ ] Email deliverability tested
- [ ] Error handling verified
- [ ] Security measures in place

---

**🎉 Your OTP system is now ready! Users will receive professional emails from `placementprediction007@gmail.com` with secure 6-digit OTPs.**