import random
import string
from datetime import datetime, timedelta

class MockOTPService:
    """
    Mock OTP Service for testing when Gmail is not configured
    This will simulate email sending and always use OTP: 123456
    """
    
    def __init__(self):
        self.otp_storage = {}
        self.mock_otp = "123456"  # Fixed OTP for testing
        
    def generate_otp(self, length=6):
        """Generate a mock OTP (always returns 123456)"""
        return self.mock_otp
    
    def send_otp(self, recipient_email, user_name="User"):
        """Mock OTP sending - always succeeds"""
        try:
            # Generate mock OTP
            otp = self.generate_otp()
            
            # Store OTP with expiry (5 minutes)
            expiry = datetime.now() + timedelta(minutes=5)
            self.otp_storage[recipient_email] = {
                'otp': otp,
                'expiry': expiry,
                'attempts': 0
            }
            
            print(f"📧 MOCK EMAIL SENT to {recipient_email}")
            print(f"🔑 OTP: {otp} (valid for 5 minutes)")
            print("📝 This is a mock email - no real email was sent")
            
            return {
                'success': True,
                'message': f'Mock OTP sent successfully. Use OTP: {otp}',
                'expiry_minutes': 5,
                'mock': True
            }
            
        except Exception as e:
            return {
                'success': False,
                'message': f'Mock OTP service error: {str(e)}'
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
            return {
                'success': False,
                'message': f'Error verifying OTP: {str(e)}'
            }

# Create mock instance
mock_otp_service = MockOTPService()