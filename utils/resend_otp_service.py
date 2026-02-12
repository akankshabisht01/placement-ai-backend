import resend
import random
import string
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()


class ResendOTPService:
    """OTP Service using Resend email API - works on cloud platforms like Railway"""
    
    def __init__(self):
        self.otp_storage = {}  # In production, use Redis or database
        self.from_email = os.getenv('RESEND_FROM_EMAIL', 'Placement AI <onboarding@resend.dev>')
    
    @property
    def api_key(self):
        """Get Resend API key from environment"""
        return os.getenv('RESEND_API_KEY', '')
    
    def generate_otp(self, length=6):
        """Generate a random OTP of specified length"""
        return ''.join(random.choices(string.digits, k=length))
    
    def send_otp(self, recipient_email, user_name="User"):
        """Send OTP via Resend email API"""
        try:
            # Check if API key is configured
            if not self.api_key:
                return {
                    'success': False,
                    'message': 'Resend API key not configured'
                }
            
            # Configure Resend
            resend.api_key = self.api_key
            
            # Generate OTP
            otp = self.generate_otp()
            
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
            
            # Send email via Resend API
            params = {
                "from": self.from_email,
                "to": [recipient_email],
                "subject": "Your OTP for Placement Prediction Registration",
                "html": html_body,
            }
            
            response = resend.Emails.send(params)
            
            if response and response.get('id'):
                print(f"Resend email sent successfully: {response['id']}")
                return {
                    'success': True,
                    'message': 'OTP sent successfully',
                    'expiry_minutes': 5
                }
            else:
                return {
                    'success': False,
                    'message': f'Failed to send email: {response}'
                }
            
        except Exception as e:
            error_msg = str(e)
            print(f"Resend Error sending OTP: {error_msg}")
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
    
    def cleanup_expired_otps(self):
        """Clean up expired OTPs (call this periodically)"""
        current_time = datetime.now()
        expired_emails = [
            email for email, data in self.otp_storage.items()
            if current_time > data['expiry']
        ]
        
        for email in expired_emails:
            del self.otp_storage[email]
        
        return len(expired_emails)


# Global instance
resend_otp_service = ResendOTPService()
