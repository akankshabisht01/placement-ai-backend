import smtplib
import ssl
import random
import string
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

class OTPService:
    def __init__(self):
        self.smtp_server = "smtp.gmail.com"
        self.smtp_port_ssl = 465  # SSL port (try first)
        self.smtp_port_tls = 587  # TLS port (fallback)
        self.sender_email = "placementprediction007@gmail.com"
        self.otp_storage = {}  # In production, use Redis or database
    
    @property
    def sender_password(self):
        """Get password dynamically from environment"""
        return os.getenv('EMAIL_PASSWORD', '')
        
    def generate_otp(self, length=6):
        """Generate a random OTP of specified length"""
        return ''.join(random.choices(string.digits, k=length))
    
    def send_otp(self, recipient_email, user_name="User"):
        """Send OTP via email"""
        try:
            # Generate OTP
            otp = self.generate_otp()
            
            # Store OTP with expiry (5 minutes)
            expiry = datetime.now() + timedelta(minutes=5)
            self.otp_storage[recipient_email] = {
                'otp': otp,
                'expiry': expiry,
                'attempts': 0
            }
            
            # Create email message
            message = MIMEMultipart("alternative")
            message["Subject"] = "Your OTP for Placement Prediction Registration"
            message["From"] = self.sender_email
            message["To"] = recipient_email
            
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
            
            # Plain text alternative
            text_body = f"""
            Placement Prediction System - Email Verification
            
            Hello {user_name}!
            
            Your One-Time Password (OTP) for registration is: {otp}
            
            This OTP is valid for 5 minutes only.
            Do not share this OTP with anyone.
            
            If you didn't request this, please ignore this email.
            
            ---
            This is an automated email from Placement Prediction System
            """
            
            # Attach parts
            text_part = MIMEText(text_body, "plain")
            html_part = MIMEText(html_body, "html")
            message.attach(text_part)
            message.attach(html_part)
            
            # Try SSL on port 465 first (often works when TLS is blocked)
            send_success = False
            last_error = None
            
            # Method 1: SMTP_SSL on port 465
            try:
                print(f"Trying Gmail SSL on port {self.smtp_port_ssl}...")
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port_ssl, context=context, timeout=30) as server:
                    server.login(self.sender_email, self.sender_password)
                    server.send_message(message)
                    send_success = True
                    print("Email sent successfully via SSL (port 465)")
            except Exception as ssl_error:
                last_error = ssl_error
                print(f"SSL (port 465) failed: {str(ssl_error)}")
                
                # Method 2: SMTP with STARTTLS on port 587 as fallback
                try:
                    print(f"Trying Gmail STARTTLS on port {self.smtp_port_tls}...")
                    with smtplib.SMTP(self.smtp_server, self.smtp_port_tls, timeout=30) as server:
                        server.starttls()
                        server.login(self.sender_email, self.sender_password)
                        server.send_message(message)
                        send_success = True
                        print("Email sent successfully via STARTTLS (port 587)")
                except Exception as tls_error:
                    last_error = tls_error
                    print(f"STARTTLS (port 587) failed: {str(tls_error)}")
            
            if send_success:
                return {
                    'success': True,
                    'message': 'OTP sent successfully',
                    'expiry_minutes': 5
                }
            else:
                raise last_error
            
        except smtplib.SMTPAuthenticationError as e:
            error_msg = str(e)
            print(f"Gmail Authentication Error: {error_msg}")
            if "Username and Password not accepted" in error_msg:
                return {
                    'success': False,
                    'message': 'Gmail authentication failed. Please ensure you have set up a Gmail App Password correctly in the .env file. Regular Gmail passwords will not work.'
                }
            else:
                return {
                    'success': False,
                    'message': f'Authentication error: {error_msg}'
                }
        except (smtplib.SMTPException, TimeoutError, OSError) as e:
            print(f"SMTP/Network Error sending OTP: {str(e)}")
            return {
                'success': False,
                'message': 'Email server connection failed. Please try again later.'
            }
        except Exception as e:
            print(f"Error sending OTP: {str(e)}")
            return {
                'success': False,
                'message': f'Failed to send OTP: {str(e)}'
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
otp_service = OTPService()