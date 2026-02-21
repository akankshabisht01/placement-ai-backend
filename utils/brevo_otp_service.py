import requests
import random
import string
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()


class BrevoOTPService:
    """OTP Service using Brevo (formerly Sendinblue) email API - works on cloud platforms"""
    
    def __init__(self):
        self.otp_storage = {}  # In production, use Redis or database
        self.from_email = os.getenv('BREVO_FROM_EMAIL', 'placementprediction007@gmail.com')
        self.from_name = os.getenv('BREVO_FROM_NAME', 'Placement AI')
        self.api_url = "https://api.brevo.com/v3/smtp/email"
    
    @property
    def api_key(self):
        """Get Brevo API key from environment"""
        return os.getenv('BREVO_API_KEY', '')
    
    def generate_otp(self, length=6):
        """Generate a random OTP of specified length"""
        return ''.join(random.choices(string.digits, k=length))
    
    def send_otp(self, recipient_email, user_name="User"):
        """Send OTP via Brevo email API"""
        try:
            print(f"[Brevo] Starting send_otp to {recipient_email}")
            print(f"[Brevo] API key set: {bool(self.api_key)}, length: {len(self.api_key)}")
            
            # Check if API key is configured
            if not self.api_key:
                print("[Brevo] ERROR: API key not configured")
                return {
                    'success': False,
                    'message': 'Brevo API key not configured'
                }
            
            # Generate OTP
            otp = self.generate_otp()
            print(f"[Brevo] Generated OTP: {otp}")
            
            # Store OTP with expiry (5 minutes)
            expiry = datetime.now() + timedelta(minutes=5)
            self.otp_storage[recipient_email] = {
                'otp': otp,
                'expiry': expiry,
                'attempts': 0
            }
            
            # HTML email template
            html_body = f"""
            <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 10px;">
                        <div style="text-align: center; margin-bottom: 30px;">
                            <h1 style="color: #2563eb; margin-bottom: 10px;">🎓 Placement Prediction System</h1>
                            <p style="color: #666; font-size: 16px;">Verify Your Email Address</p>
                        </div>
                        
                        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; border-radius: 10px; text-align: center; margin-bottom: 30px;">
                            <h2 style="color: white; margin-bottom: 15px;">Hello {user_name}!</h2>
                            <p style="color: white; margin-bottom: 20px; font-size: 16px;">
                                Your One-Time Password (OTP) for registration is:
                            </p>
                            <div style="background: white; display: inline-block; padding: 20px 40px; border-radius: 8px; font-size: 32px; font-weight: bold; color: #2563eb; letter-spacing: 8px; margin: 10px;">
                                {otp}
                            </div>
                        </div>
                        
                        <div style="background: #f8fafc; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
                            <h3 style="color: #374151; margin-bottom: 15px;">⏰ Important Information:</h3>
                            <ul style="color: #6b7280; padding-left: 20px;">
                                <li>This OTP is valid for <strong>5 minutes only</strong></li>
                                <li>Do not share this OTP with anyone</li>
                                <li>If you didn't request this, please ignore this email</li>
                            </ul>
                        </div>
                        
                        <div style="text-align: center; padding: 20px; border-top: 1px solid #e5e7eb;">
                            <p style="color: #9ca3af; font-size: 14px; margin: 0;">
                                This is an automated email from Placement Prediction System<br>
                                Please do not reply to this email.
                            </p>
                        </div>
                    </div>
                </body>
            </html>
            """
            
            # Brevo API payload
            payload = {
                "sender": {
                    "name": self.from_name,
                    "email": self.from_email
                },
                "to": [
                    {
                        "email": recipient_email,
                        "name": user_name
                    }
                ],
                "subject": "Your OTP for Placement Prediction Registration",
                "htmlContent": html_body
            }
            
            headers = {
                "accept": "application/json",
                "api-key": self.api_key,
                "content-type": "application/json"
            }
            
            print(f"[Brevo] Sending email from {self.from_email} to {recipient_email}")
            response = requests.post(self.api_url, json=payload, headers=headers, timeout=30)
            print(f"[Brevo] Response status: {response.status_code}")
            print(f"[Brevo] Response body: {response.text}")
            
            if response.status_code in [200, 201]:
                result = response.json()
                print(f"[Brevo] Email sent successfully: {result.get('messageId', 'unknown')}")
                return {
                    'success': True,
                    'message': 'OTP sent successfully',
                    'expiry_minutes': 5
                }
            else:
                error_detail = response.json() if response.text else {'message': 'Unknown error'}
                print(f"[Brevo] Failed - {error_detail}")
                return {
                    'success': False,
                    'message': f"Failed to send email: {error_detail.get('message', response.text)}"
                }
            
        except Exception as e:
            import traceback
            error_msg = str(e)
            print(f"[Brevo] ERROR: {error_msg}")
            print(f"[Brevo] Traceback: {traceback.format_exc()}")
            return {
                'success': False,
                'message': f'Failed to send OTP: {error_msg}'
            }
    
    def verify_otp(self, recipient_email, entered_otp):
        """Verify the entered OTP"""
        try:
            if recipient_email not in self.otp_storage:
                return {
                    'success': False,
                    'message': 'No OTP found for this email. Please request a new OTP.'
                }
            
            stored_data = self.otp_storage[recipient_email]
            
            # Check if OTP has expired
            if datetime.now() > stored_data['expiry']:
                del self.otp_storage[recipient_email]
                return {
                    'success': False,
                    'message': 'OTP has expired. Please request a new OTP.'
                }
            
            # Check attempts limit
            if stored_data['attempts'] >= 3:
                del self.otp_storage[recipient_email]
                return {
                    'success': False,
                    'message': 'Too many failed attempts. Please request a new OTP.'
                }
            
            # Verify OTP
            if stored_data['otp'] == entered_otp:
                del self.otp_storage[recipient_email]
                return {
                    'success': True,
                    'message': 'OTP verified successfully!'
                }
            else:
                # Increment attempts
                self.otp_storage[recipient_email]['attempts'] += 1
                remaining_attempts = 3 - self.otp_storage[recipient_email]['attempts']
                return {
                    'success': False,
                    'message': f'Invalid OTP. {remaining_attempts} attempts remaining.'
                }
                
        except Exception as e:
            print(f"Error verifying OTP: {str(e)}")
            return {
                'success': False,
                'message': f'Error verifying OTP: {str(e)}'
            }


# Global instance
brevo_otp_service = BrevoOTPService()
