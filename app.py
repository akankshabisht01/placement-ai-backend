import sys
import os

# Add the app directory to Python path for Railway deployment
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import tempfile
import time
import random
import razorpay
from datetime import datetime, timedelta
from models.ml_placement_model import MLPlacementPredictor
from data.domain_data import get_domain_data
from utils.resume_parser import parse_resume as parse_resume_file
from utils.ats_calculator import calculate_ats_score
from utils.db import save_parsed_resume, save_candidate_prediction, get_db, normalize_phone, format_phone_id
from utils.suggestions import generate_suggestions
from utils.otp_service import otp_service
from utils.mock_otp_service import mock_otp_service
from utils.student_analysis import save_student_analysis_safe, bulk_sync_resumes_to_analysis, sync_resume_to_student_analysis
from utils.validators import validate_prediction_input, sanitize_text_input, deduplicate_skills
from utils.error_handler import (
    handle_errors, format_error_response, format_success_response,
    ErrorCode, ValidationError, DatabaseError, ModelError, ResourceNotFoundError,
    validate_required_fields, validate_numeric_range, log_error, generate_request_id
)
from utils.student_analysis import save_student_analysis_safe
from dotenv import load_dotenv
import requests
import zipfile
import io

load_dotenv()  # Load env vars like PERPLEXITY_API_KEY

# Helper function to split combined skills
def split_combined_skills(skills_list):
    """
    Split any combined skills (containing ' & ') into individual skills.
    Example: ["Python", "Machine Learning Models & scikit-learn"] 
          -> ["Python", "Machine Learning Models", "scikit-learn"]
    """
    if not isinstance(skills_list, list):
        return skills_list
    
    new_skills = []
    for skill in skills_list:
        if isinstance(skill, str) and ' & ' in skill:
            # Split and add individual skills
            individual_skills = [s.strip() for s in skill.split(' & ')]
            new_skills.extend(individual_skills)
        else:
            new_skills.append(skill)
    
    # Remove duplicates while preserving order (case-insensitive)
    seen = set()
    unique_skills = []
    for skill in new_skills:
        if isinstance(skill, str):
            skill_lower = skill.lower()
            if skill_lower not in seen:
                seen.add(skill_lower)
                unique_skills.append(skill)
        else:
            unique_skills.append(skill)
    
    return unique_skills

# notify-answer-response endpoint moved below app initialization to avoid
# referencing `app` before it is created. See insertion later in this file.
from pymongo import MongoClient
import re
import threading

# In-memory lock to prevent duplicate weekly plan API calls while one is in progress
_weekly_plan_locks = {}
_weekly_plan_lock_mutex = threading.Lock()

# Check if Gmail is properly configured
email_password = os.getenv('EMAIL_PASSWORD', '')
use_mock_otp = (not email_password or 
                email_password in ['your-app-password', 'your-gmail-app-password-here', 'Launchpad03'])

if use_mock_otp:
    print("⚠️  Using Mock OTP Service (Gmail not configured)")
    print("📧 All OTPs will be: 123456")
    print("🔧 To enable real emails, set up Gmail App Password in .env")
    active_otp_service = mock_otp_service
else:
    print("✅ Using Real Gmail OTP Service")
    active_otp_service = otp_service

app = Flask(__name__)
# Limit uploaded file size to 10MB
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024

# Suppress werkzeug OPTIONS request logs
import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# Allow common dev origins (localhost, 127.0.0.1, and LAN IPs) for the API
# Broaden CORS for local development across any port/host on the LAN
CORS(app, resources={
    r"/api/*": {
        "origins": "*",
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

# Add CORS headers to all responses
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# Initialize the ML-based placement predictor
predictor = MLPlacementPredictor()

# Initialize Razorpay Client
razorpay_key_id = os.getenv('RAZORPAY_KEY_ID', '')
razorpay_key_secret = os.getenv('RAZORPAY_KEY_SECRET', '')

if razorpay_key_id and razorpay_key_secret:
    razorpay_client = razorpay.Client(auth=(razorpay_key_id, razorpay_key_secret))
    print("✅ Razorpay client initialized")
else:
    razorpay_client = None
    print("⚠️  Razorpay not configured (add RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET to .env)")

def send_prediction_to_n8n(user_data, prediction_data, action_type="prediction_completed"):
    """
    Helper function to send prediction data to n8n webhook for student analysis processing
    
    n8n will process this data and call /api/save-student-analysis when complete
    
    Args:
        user_data (dict): User form data (name, email, mobile, etc.)
        prediction_data (dict): Prediction results
        action_type (str): Type of action for n8n workflow
        
    Returns:
        dict: Result of the webhook call
    """
    try:
        import requests
        
        webhook_url = os.getenv('N8N_MOBILE_WEBHOOK')
        if not webhook_url:
            return {
                'success': False,
                'message': 'N8N_MOBILE_WEBHOOK not configured'
            }
        
        # Prepare comprehensive webhook payload for n8n
        webhook_payload = {
            'mobile': user_data.get('mobile') or user_data.get('phone', ''),
            'email': user_data.get('email', ''),
            'name': user_data.get('name', ''),
            'timestamp': datetime.now().isoformat(),
            'action': action_type,
            'source': 'placement-ai-prediction',
            
            # Add prediction results
            'placement_score': prediction_data.get('placementScore', 0),
            'ml_score': prediction_data.get('mlModelScore', 0),
            'prediction_confidence': prediction_data.get('predictionConfidence', 0),
            'is_eligible': prediction_data.get('isEligible', False),
            
            # Add form data for comprehensive analysis
            'academic_data': {
                'tenth_percentage': user_data.get('tenthPercentage', 0),
                'twelfth_percentage': user_data.get('twelfthPercentage', 0),
                'college_cgpa': user_data.get('collegeCGPA', 0),
                'degree': user_data.get('degree', ''),
                'college': user_data.get('college', '')
            },
            
            # Add job selection data
            'job_data': {
                'selected_domain': user_data.get('selectedDomainId', ''),
                'selected_skills': user_data.get('selectedSkills', []),
                'custom_job_role': user_data.get('customJobRole', '')
            },
            
            # Full data for n8n processing
            'full_form_data': user_data,
            'full_prediction_data': prediction_data
        }
        
        # Send to primary n8n webhook
        response = requests.post(
            webhook_url,
            json=webhook_payload,
            headers={'Content-Type': 'application/json'},
            timeout=30
        )

        result = {
            'success': response.status_code == 200,
            'n8n_status': response.status_code,
            'n8n_response': response.text[:200] if response.text else None
        }

        # Try optional secondary webhook (non-blocking)
        webhook_url_2 = os.getenv('N8N_MOBILE_WEBHOOK_2')
        if webhook_url_2:
            try:
                resp2 = requests.post(
                    webhook_url_2,
                    json=webhook_payload,
                    headers={'Content-Type': 'application/json'},
                    timeout=30
                )
                result['n8n_2_status'] = resp2.status_code
                result['n8n_2_response'] = resp2.text[:200] if resp2.text else None
            except Exception as e:
                result['n8n_2_error'] = str(e)

        if result['success']:
            return {
                'success': True,
                'message': 'Data sent to n8n successfully',
                'webhook_info': result
            }
        else:
            return {
                'success': False,
                'message': f'n8n webhook returned status {response.status_code}',
                'webhook_info': result
            }
            
    except requests.exceptions.RequestException as e:
        return {
            'success': False,
            'message': f'Failed to send data to n8n: {str(e)}'
        }
    except Exception as e:
        return {
            'success': False,
            'message': f'Error sending to n8n: {str(e)}'
        }


# Endpoint: notify n8n about test 'View Results' click (server-side proxy to avoid CORS)
@app.route('/api/notify-answer-response', methods=['POST'])
def notify_answer_response():
    """Proxy endpoint that accepts { mobile } and forwards to configured n8n webhook.

    This avoids browser CORS issues and centralizes webhook delivery and logging.
    """
    try:
        payload = request.get_json() or {}
        mobile = payload.get('mobile')
        if not mobile:
            return jsonify({'success': False, 'error': 'mobile is required'}), 400

        # Allow caller to request a specific action. For roadmap button clicks use the
        # dedicated n8n webhook (the URL the team provided); otherwise fallback to
        # the test answer response webhook configured in env.
        action = payload.get('action')
        if action == 'roadmap_click':
            # Use environment-configured roadmap webhook
            webhook_url = os.getenv('N8N_ROADMAP_WEBHOOK', 'https://n8n23-80hw.onrender.com/webhook-test/e52661f1-2a51-40ec-90c6-35edb5eb00e2')
            print(f"[notify-answer-response] 🎯 Roadmap webhook URL from env: {os.getenv('N8N_ROADMAP_WEBHOOK')}")
            print(f"[notify-answer-response] 🔗 Final webhook URL: {webhook_url}")
            
            # For roadmap generation, fetch user data from Resume collection
            try:
                db = get_db()
                resume_collection = db['Resume']
                user_data = resume_collection.find_one({'mobile': mobile})
                
                if user_data:
                    # Extract skills and prepare payload for n8n
                    skills = user_data.get('skills', [])
                    # Convert skills array to topics format n8n expects
                    topics = [skill if isinstance(skill, str) else skill.get('name', str(skill)) for skill in skills]
                    
                    # Prepare comprehensive payload for roadmap generation
                    webhook_payload = {
                        'mobile': mobile,
                        'topics': topics if topics else ['Python', 'Data Analysis', 'Machine Learning'],  # Default topics if none found
                        'action': action,
                        'user_data': {
                            'name': user_data.get('name', ''),
                            'email': user_data.get('email', ''),
                            'domain': user_data.get('domain', 'Data Science'),
                            'experience_years': user_data.get('experience_years', 0)
                        }
                    }
                    print(f"[notify-answer-response] roadmap payload with {len(topics)} topics: {topics[:5]}")
                else:
                    # User not found, send basic payload with default topics
                    webhook_payload = {
                        'mobile': mobile,
                        'topics': ['Python', 'Data Analysis', 'SQL', 'Machine Learning'],
                        'action': action
                    }
                    print(f"[notify-answer-response] user not found, using default topics")
            except Exception as e:
                print(f"[notify-answer-response] error fetching user data: {e}")
                # Fallback to basic payload
                webhook_payload = {
                    'mobile': mobile,
                    'topics': ['Python', 'Data Analysis', 'SQL'],
                    'action': action
                }
        elif action == 'analysis_request':
            # For test analysis report generation - use configured webhook
            webhook_url = os.getenv('N8N_TEST_ANSWER_RESPONSE_WEBHOOK', 'https://n8n23-80hw.onrender.com/webhook-test/answer-response')
            webhook_payload = {
                'mobile': mobile,
                'action': action
            }
            print(f"[notify-answer-response] 📊 Analysis request - triggering webhook for mobile: {mobile}")
        elif action == 'weekly_test_analysis' or action == 'progress_tracking_weekly':
            # For weekly test progress tracking analysis
            webhook_url = os.getenv('N8N_PROGRESS_TRACKING_WEEKLY_WEBHOOK', 'https://n8n23-80hw.onrender.com/webhook/Progress_tracking_week')
            week = payload.get('week')
            month = payload.get('month')
            webhook_payload = {
                'mobile': mobile,
                'action': action,
                'week': week,
                'month': month
            }
            print(f"[notify-answer-response] 📈 Weekly test analysis request - triggering webhook for mobile: {mobile}, week: {week}, month: {month}")
            print(f"[notify-answer-response] 🔗 Progress tracking webhook URL: {webhook_url}")
        elif action == 'generate_weekly_test':
            # For generating weekly test - calculate current week/month
            webhook_url = os.getenv('N8N_WEEKLY_TEST_WEBHOOK', 'https://n8n23-80hw.onrender.com/webhook-test/201bbf9b-1b8a-4e3b-8064-85f4d88f6c1f')
            
            # Clean up mobile number
            mobile_clean = mobile.replace('-', '').replace(' ', '').strip()
            
            # Extract 10-digit number
            if mobile_clean.startswith('+91'):
                number_part = mobile_clean[3:]
            elif mobile_clean.startswith('91') and len(mobile_clean) == 12:
                number_part = mobile_clean[2:]
            else:
                number_part = mobile_clean
            
            # Format as +91 XXXXXXXXXX (with space after +91)
            clean_mobile = f'+91 {number_part}'
            
            # Get current week from Weekly_test_analysis collection
            from pymongo import MongoClient
            mongo_uri = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
            db_name = os.getenv('MONGODB_DB', 'Placement_Ai')
            client = MongoClient(mongo_uri)
            db = client[db_name]
            
            analysis_collection = db['Weekly_test_analysis']
            completed_weeks = []
            
            # Search for completed analyses
            analyses = list(analysis_collection.find({'mobile': clean_mobile}))
            for analysis in analyses:
                if 'analysis' in analysis and 'week' in analysis['analysis']:
                    completed_weeks.append(analysis['analysis']['week'])
            
            # Calculate current week (next week to generate)
            current_week = 1
            if completed_weeks:
                current_week = max(completed_weeks) + 1
            
            # Calculate current month (4 weeks per month)
            current_month = ((current_week - 1) // 4) + 1
            
            webhook_payload = {
                'mobile': clean_mobile,
                'week': current_week,
                'month': current_month
            }
            print(f"[notify-answer-response] 🔄 Generate weekly test request - mobile: {clean_mobile}, week: {current_week}, month: {current_month}")
        else:
            webhook_url = os.getenv('N8N_TEST_ANSWER_RESPONSE_WEBHOOK', 'https://n8n-1-2ldl.onrender.com/webhook-test/answer-response')
            webhook_payload = {
                'mobile': mobile,
                'action': action
            }

        try:
            import requests
            # Debug logging for webhook forwarding
            print(f"[notify-answer-response] received payload: mobile={mobile}, action={action}")
            print(f"[notify-answer-response] forwarding to: {webhook_url}")
            
            # Use webhook_payload if defined (for roadmap), otherwise use simple payload
            payload_to_send = webhook_payload if 'webhook_payload' in locals() else {'mobile': mobile, 'action': action}
            
            resp = requests.post(webhook_url, json=payload_to_send, timeout=10)
            # Log response status for debugging
            resp_text = None
            try:
                resp_text = resp.text
            except Exception:
                resp_text = '<unreadable response body>'
            print(f"[notify-answer-response] webhook response status={resp.status_code} body={resp_text[:1000] if resp_text else ''}")
            return jsonify({'success': True, 'webhook': {'status_code': resp.status_code, 'text': resp_text[:1000] if resp_text else None, 'url_used': webhook_url}})
        except requests.exceptions.RequestException as e:
            # network/requests-specific exception
            print(f"[notify-answer-response] requests exception: {e}")
            return jsonify({'success': False, 'webhook': {'error': str(e), 'url_used': webhook_url}}), 502
        except Exception as e:
            # generic exception
            print(f"[notify-answer-response] general exception: {e}")
            return jsonify({'success': False, 'webhook': {'error': str(e), 'url_used': webhook_url}}), 502

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/check-weekly-test', methods=['POST'])
def check_weekly_test():
    """Check if weekly test exists in week_test collection for a given mobile number, week, and month"""
    try:
        payload = request.get_json() or {}
        mobile = payload.get('mobile')
        week = payload.get('week')  # Optional: check for specific week
        month = payload.get('month')  # Optional: check for specific month
        
        if not mobile:
            return jsonify({'success': False, 'error': 'mobile is required'}), 400
        
        # Connect to MongoDB
        db = get_db()
        week_test_collection = db['week_test']
        
        # Build query
        query = {'mobile': mobile}
        
        # If week and month are provided, check for that specific test
        if week is not None and month is not None:
            query['week'] = week
            query['month'] = month
            print(f"[check-weekly-test] Checking for specific Week {week}, Month {month}")
        else:
            print(f"[check-weekly-test] Checking for any test")
        
        # Check if test exists
        test_exists = week_test_collection.find_one(query)
        
        if test_exists:
            print(f"[check-weekly-test] ✅ Test found for mobile: {mobile}, Week: {week}, Month: {month}")
            return jsonify({'success': True, 'exists': True, 'test': {'week': test_exists.get('week'), 'month': test_exists.get('month')}})
        else:
            print(f"[check-weekly-test] ⏳ Test not yet found for mobile: {mobile}, Week: {week}, Month: {month}")
            return jsonify({'success': True, 'exists': False})
            
    except Exception as e:
        print(f"[check-weekly-test] ❌ Error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/debug-weekly-test-payload', methods=['POST', 'OPTIONS'])
def debug_weekly_test_payload():
    """Debug endpoint to show what payload would be sent to N8N without actually calling it"""
    # Handle CORS preflight
    if request.method == 'OPTIONS':
        return jsonify({'status': 'ok'}), 200
    
    try:
        payload = request.get_json() or {}
        mobile = payload.get('mobile')
        
        if not mobile:
            return jsonify({'success': False, 'error': 'mobile is required'}), 400
        
        # Clean up mobile number
        mobile = mobile.replace('-', '').replace(' ', '').strip()
        
        # Extract 10-digit number
        if mobile.startswith('+91'):
            number_part = mobile[3:]
        elif mobile.startswith('91') and len(mobile) == 12:
            number_part = mobile[2:]
        else:
            number_part = mobile
        
        # Validate
        if len(number_part) != 10:
            return jsonify({'success': False, 'error': f'Invalid mobile format: {mobile}'}), 400
        
        # Format as +91 XXXXXXXXXX (with space after +91)
        clean_mobile = f'+91 {number_part}'
        
        # Get current week info for this user
        mongo_uri = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
        db_name = os.getenv('MONGODB_DB', 'Placement_Ai')
        client = MongoClient(mongo_uri)
        db = client[db_name]
        
        # Get current week from Weekly_test_analysis collection
        analysis_collection = db['Weekly_test_analysis']
        completed_weeks = []
        
        # Search for completed analyses
        analyses = list(analysis_collection.find({'mobile': clean_mobile}))
        for analysis in analyses:
            if 'analysis' in analysis and 'week' in analysis['analysis']:
                completed_weeks.append(analysis['analysis']['week'])
        
        # Calculate current week (next week to generate)
        current_week = 1
        if completed_weeks:
            current_week = max(completed_weeks) + 1
        
        # Calculate current month (4 weeks per month)
        current_month = ((current_week - 1) // 4) + 1
        
        # Prepare webhook payload with mobile, week, and month
        webhook_payload = {
            'mobile': clean_mobile,
            'week': current_week,
            'month': current_month
        }
        
        # Return debug info
        return jsonify({
            'success': True,
            'debug_info': {
                'original_mobile': mobile,
                'clean_mobile': clean_mobile,
                'completed_weeks': completed_weeks,
                'current_week': current_week,
                'current_month': current_month,
                'webhook_payload': webhook_payload,
                'analyses_found': len(analyses)
            }
        })
        
    except Exception as e:
        print(f"[debug-weekly-test-payload] Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/trigger-weekly-test', methods=['POST', 'OPTIONS'])
def trigger_weekly_test():
    """Trigger weekly test generation webhook when user clicks Take Test button"""
    # Handle CORS preflight
    if request.method == 'OPTIONS':
        return jsonify({'status': 'ok'}), 200
    
    try:
        payload = request.get_json() or {}
        mobile = payload.get('mobile')
        
        if not mobile:
            return jsonify({'success': False, 'error': 'mobile is required'}), 400
        
        # Get weekly test webhook URL from environment
        webhook_url = os.getenv('N8N_WEEKLY_TEST_WEBHOOK')
        
        if not webhook_url:
            return jsonify({'success': False, 'error': 'Weekly test webhook not configured'}), 500
        
        try:
            import requests
            
            # Clean mobile number but keep +91 prefix with space
            clean_mobile = str(mobile).strip()
            
            # Remove any spaces, dashes, or special characters first
            clean_mobile = clean_mobile.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
            
            # Extract just the 10-digit number
            if clean_mobile.startswith('+91'):
                number_part = clean_mobile[3:]
            elif clean_mobile.startswith('91') and len(clean_mobile) == 12:
                number_part = clean_mobile[2:]
            elif clean_mobile.startswith('+'):
                number_part = clean_mobile[1:]
            else:
                number_part = clean_mobile
            
            # Format as +91 XXXXXXXXXX (with space after +91)
            clean_mobile = f'+91 {number_part}'
            
            # Clear any previous error status for this mobile
            if clean_mobile in test_generation_status:
                del test_generation_status[clean_mobile]
            
            # Get current week info for this user
            mongo_uri = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
            db_name = os.getenv('MONGODB_DB', 'Placement_Ai')
            client = MongoClient(mongo_uri)
            db = client[db_name]
            
            # Get current week from Weekly_test_analysis collection
            analysis_collection = db['Weekly_test_analysis']
            completed_weeks = []
            
            # Search for completed analyses
            analyses = list(analysis_collection.find({'mobile': clean_mobile}))
            for analysis in analyses:
                if 'analysis' in analysis and 'week' in analysis['analysis']:
                    completed_weeks.append(analysis['analysis']['week'])
            
            # Calculate current week (next week to generate)
            current_week = 1
            if completed_weeks:
                current_week = max(completed_weeks) + 1
            
            # Calculate current month (4 weeks per month)
            current_month = ((current_week - 1) // 4) + 1
            
            # Prepare webhook payload with mobile, week, and month
            webhook_payload = {
                'mobile': clean_mobile,
                'week': current_week,
                'month': current_month
            }
            
            print(f"[trigger-weekly-test] Original mobile: {mobile}, Clean mobile: {clean_mobile}")
            print(f"[trigger-weekly-test] Current week: {current_week}, Month: {current_month}")
            print(f"[trigger-weekly-test] Sending to: {webhook_url}")
            print(f"[trigger-weekly-test] Payload: {webhook_payload}")
            print(f"[trigger-weekly-test] Payload JSON: {json.dumps(webhook_payload, indent=2)}")
            
            # Set initial status as 'generating'
            test_generation_status[clean_mobile] = {
                'status': 'generating',
                'timestamp': datetime.now().isoformat()
            }
            
            # Trigger n8n webhook
            print(f"[trigger-weekly-test] Making POST request to N8N...")
            resp = requests.post(webhook_url, json=webhook_payload, timeout=10)
            resp_text = resp.text if resp.text else None
            
            print(f"[trigger-weekly-test] Response status={resp.status_code}")
            
            # Check if N8N returned an error
            if resp.status_code >= 400:
                error_msg = f"N8N workflow returned error {resp.status_code}"
                if resp_text:
                    error_msg += f": {resp_text[:200]}"
                print(f"[trigger-weekly-test] N8N error: {error_msg}")
                return jsonify({
                    'success': False,
                    'error': 'N8N workflow failed. Please check the workflow configuration.',
                    'details': error_msg,
                    'n8n_status': resp.status_code
                }), 502
            
            return jsonify({
                'success': True,
                'message': 'Weekly test webhook triggered successfully',
                'webhook': {
                    'status_code': resp.status_code,
                    'url_used': webhook_url
                }
            })
            
        except requests.exceptions.Timeout as e:
            print(f"[trigger-weekly-test] Timeout: {e}")
            # Mark as error in status
            test_generation_status[clean_mobile] = {
                'status': 'error',
                'error_message': 'N8N service timeout. Please check if N8N is running.',
                'timestamp': datetime.now().isoformat()
            }
            return jsonify({
                'success': False,
                'error': 'N8N webhook timeout. The service might be down or slow.',
                'details': str(e)
            }), 504
        except requests.exceptions.ConnectionError as e:
            print(f"[trigger-weekly-test] Connection error: {e}")
            # Mark as error in status
            test_generation_status[clean_mobile] = {
                'status': 'error',
                'error_message': 'Cannot connect to N8N. Please check if N8N service is running.',
                'timestamp': datetime.now().isoformat()
            }
            return jsonify({
                'success': False,
                'error': 'Cannot connect to N8N. Please check if N8N service is running.',
                'details': str(e)
            }), 503
        except requests.exceptions.RequestException as e:
            print(f"[trigger-weekly-test] Request exception: {e}")
            # Mark as error in status
            test_generation_status[clean_mobile] = {
                'status': 'error',
                'error_message': 'N8N webhook request failed.',
                'timestamp': datetime.now().isoformat()
            }
            return jsonify({
                'success': False,
                'error': 'N8N webhook request failed.',
                'details': str(e)
            }), 502
            
    except Exception as e:
        print(f"[trigger-weekly-test] General exception: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# Store test generation status (mobile -> status info)
test_generation_status = {}


@app.route('/api/test-generation-status/<mobile>', methods=['GET'])
def get_test_generation_status(mobile):
    """Check if test generation failed or is in progress"""
    try:
        mobile = mobile.strip()
        status_info = test_generation_status.get(mobile, {})
        
        if status_info.get('status') == 'error':
            return jsonify({
                'success': False,
                'error_type': 'n8n_error',
                'error': status_info.get('error_message', 'Test generation failed'),
                'timestamp': status_info.get('timestamp')
            }), 500
        
        return jsonify({
            'success': True,
            'status': status_info.get('status', 'unknown'),
            'message': status_info.get('message', 'No status available')
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/report-test-error', methods=['POST'])
def report_test_error():
    """Endpoint for N8N to report test generation errors"""
    try:
        data = request.get_json() or {}
        mobile = data.get('mobile')
        error_message = data.get('error', 'Unknown error occurred')
        
        if not mobile:
            return jsonify({'success': False, 'error': 'mobile is required'}), 400
        
        # Store error status
        test_generation_status[mobile] = {
            'status': 'error',
            'error_message': error_message,
            'timestamp': datetime.now().isoformat()
        }
        
        print(f"[report-test-error] Received error for {mobile}: {error_message}")
        
        return jsonify({
            'success': True,
            'message': 'Error status recorded'
        }), 200
        
    except Exception as e:
        print(f"[report-test-error] Exception: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/health', methods=['GET'])
@handle_errors
def health_check():
    """Health check endpoint"""
    return {
        'status': 'healthy',
        'service': 'placement-prediction-api',
        'version': '1.0.0',
        'timestamp': datetime.now().isoformat()
    }


@app.route('/api/get-courses-for-topics', methods=['POST'])
def get_courses_for_topics():
    """
    Fetch Microsoft Learn courses that match given topics/skills.
    
    Request body: { "topics": ["Python", "React", "AWS"], "mobile": "+91...", "limit": 3 }
    Returns: { "success": true, "courses": {...}, "mobile": "..." }
    """
    try:
        payload = request.get_json() or {}
        topics = payload.get('topics', [])
        # Accept both '_id' (from n8n) and 'mobile' (legacy)
        user_id = payload.get('_id') or payload.get('mobile', '')
        limit_per_topic = payload.get('limit', 3)
        
        if not topics:
            return jsonify({'success': False, 'error': 'topics array is required'}), 400
        
        # Fetch Microsoft Learn catalog (cache this in production!)
        print(f"[get-courses] Fetching courses for topics: {topics} (user_id: {user_id})")
        catalog_url = 'https://learn.microsoft.com/api/catalog'
        
        try:
            catalog_resp = requests.get(catalog_url, timeout=10)
            catalog_resp.raise_for_status()
            catalog = catalog_resp.json()
        except Exception as e:
            return jsonify({'success': False, 'error': f'Failed to fetch Microsoft Learn catalog: {str(e)}'}), 502
        
        # Match topics to courses
        all_courses = catalog.get('courses', [])
        modules = catalog.get('modules', [])
        learning_paths = catalog.get('learningPaths', [])
        
        result = {}
        for topic in topics:
            topic_lower = topic.lower()
            
            # Extract key words from topic (ignore common words)
            stop_words = {'for', 'with', 'the', 'and', 'or', 'in', 'to', 'of', 'a', 'an', 'on', 'at', 'from', 'by'}
            keywords = [w for w in topic_lower.split() if w not in stop_words and len(w) > 2]
            
            # Find matching courses
            matching = []
            for course in all_courses:
                title = (course.get('title') or '').lower()
                summary = (course.get('summary') or '').lower()
                products = [p.lower() for p in (course.get('products') or [])]
                
                # Check if any keyword matches
                score = 0
                for keyword in keywords:
                    if keyword in title:
                        score += 3  # Title match is most important
                    elif keyword in summary:
                        score += 1  # Summary match is less important
                    elif any(keyword in p for p in products):
                        score += 2  # Product match is good
                
                if score > 0:
                    matching.append({
                        'type': 'course',
                        'title': course.get('title'),
                        'url': course.get('url'),
                        'summary': course.get('summary'),
                        'duration_minutes': course.get('duration_in_minutes'),
                        'level': course.get('levels', [''])[0] if course.get('levels') else 'intermediate',
                        'relevance_score': score
                    })
            
            # Also search modules for more granular content
            for module in modules[:500]:  # Increased limit for better coverage
                title = (module.get('title') or '').lower()
                summary = (module.get('summary') or '').lower()
                
                score = 0
                for keyword in keywords:
                    if keyword in title:
                        score += 3
                    elif keyword in summary:
                        score += 1
                
                if score > 0:
                    matching.append({
                        'type': 'module',
                        'title': module.get('title'),
                        'url': module.get('url'),
                        'summary': module.get('summary'),
                        'duration_minutes': module.get('duration_in_minutes'),
                        'level': module.get('levels', [''])[0] if module.get('levels') else 'beginner',
                        'relevance_score': score
                    })
            
            # Sort by relevance score (highest first)
            matching.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
            result[topic] = matching[:limit_per_topic]
        
        return jsonify({
            'success': True,
            '_id': user_id,
            'topics': topics,
            'courses': result,
            'total_topics': len(topics),
            'catalog_stats': {
                'total_courses': len(all_courses),
                'total_modules': len(modules),
                'total_paths': len(learning_paths)
            }
        })
        
    except Exception as e:
        print(f"[get-courses] Error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/get-all-courses', methods=['GET'])
def get_all_courses():
    """
    Fetch all courses from the MongoDB Course collection.
    
    Query params:
      - skill: optional skill name to filter by
      - limit: max number of courses per skill (default: all)
    
    Returns: { "success": true, "courses": {...}, "total": number }
    """
    try:
        db = get_db()
        course_collection = db['Course']
        
        # Get query parameters
        skill_filter = request.args.get('skill')
        limit_per_skill = request.args.get('limit', type=int)
        
        # Build query
        query = {}
        if skill_filter:
            query['skill'] = skill_filter
        
        # Fetch courses from MongoDB
        print(f"[get-all-courses] Fetching courses with query: {query}")
        courses_cursor = course_collection.find(query)
        
        # Group courses by skill
        courses_by_skill = {}
        total_courses = 0
        
        for course_doc in courses_cursor:
            skill = course_doc.get('skill', 'General')
            
            # Convert MongoDB document to dict
            course_info = {
                'skill': skill,
                'courses': course_doc.get('courses', [])
            }
            
            # Apply limit if specified
            if limit_per_skill and len(course_info['courses']) > limit_per_skill:
                course_info['courses'] = course_info['courses'][:limit_per_skill]
            
            courses_by_skill[skill] = course_info['courses']
            total_courses += len(course_info['courses'])
        
        return jsonify({
            'success': True,
            'courses': courses_by_skill,
            'total': total_courses,
            'skills_count': len(courses_by_skill)
        })
        
    except Exception as e:
        print(f"[get-all-courses] Error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/test-webhook', methods=['POST'])
def test_webhook():
    """Utility endpoint for debugging webhook forwarding.

    Accepts JSON: { which: 'roadmap'|'answer_response', mobile: '<mobile>' }
    Returns the response returned by the upstream webhook and logs details.
    """
    try:
        payload = request.get_json() or {}
        which = (payload.get('which') or 'answer_response').lower()
        mobile = payload.get('mobile') or payload.get('phone') or 'TEST_MOBILE'

        if which == 'roadmap':
            webhook_url = os.getenv('N8N_ROADMAP_WEBHOOK') or 'https://n8n23-80hw.onrender.com/webhook-test/e52661f1-2a51-40ec-90c6-35edb5eb00e2'
        else:
            webhook_url = os.getenv('N8N_TEST_ANSWER_RESPONSE_WEBHOOK') or 'https://n8n23-80hw.onrender.com/webhook/answer-response'

        import requests
        print(f"[test-webhook] testing webhook '{which}' -> {webhook_url} with mobile={mobile}")
        resp = requests.post(webhook_url, json={'mobile': mobile, 'test': True}, timeout=15)
        resp_text = resp.text[:2000] if resp.text else None
        print(f"[test-webhook] response status={resp.status_code} body={resp_text}")
        return jsonify({'success': True, 'status_code': resp.status_code, 'body': resp_text, 'url_used': webhook_url})
    except Exception as e:
        print(f"[test-webhook] exception: {e}")
        return jsonify({'success': False, 'error': str(e)}), 502

@app.route('/api/trigger-weekly-progress-webhook', methods=['POST', 'OPTIONS'])
def trigger_weekly_progress_webhook():
    """
    Endpoint to trigger weekly test analysis webhook
    First checks if analysis already exists in database
    If exists, returns existing data without triggering webhook
    If not exists, triggers webhook for analysis generation
    
    Accepts JSON: { mobile: '<mobile_number>', week: <week_number>, month: <month_number> }
    """
    # Handle OPTIONS request for CORS preflight
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200
    
    try:
        payload = request.get_json() or {}
        mobile = payload.get('mobile')
        week = payload.get('week')
        month = payload.get('month')
        
        print(f"[trigger-weekly-progress] Received request with payload: {payload}")
        
        if not mobile:
            print(f"[trigger-weekly-progress] ERROR: No mobile number provided")
            return jsonify({
                'success': False,
                'message': 'Mobile number is required'
            }), 400
        
        # ===== STEP 1: Check if analysis already exists in database =====
        print(f"[trigger-weekly-progress] 🔍 Checking if analysis already exists for mobile: {mobile}")
        
        try:
            mongo_uri = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
            db_name = os.getenv('MONGODB_DB', 'Placement_Ai')
            
            client = MongoClient(mongo_uri)
            db = client[db_name]
            collection = db['Weekly_test_analysis']
            
            # Normalize mobile number
            normalized_mobile = ''.join(filter(str.isdigit, mobile))
            mobile_10 = normalized_mobile[-10:] if len(normalized_mobile) >= 10 else normalized_mobile
            
            # Build search query for multiple mobile formats
            search_ids = [mobile, normalized_mobile, mobile_10]
            if len(normalized_mobile) == 10:
                search_ids.extend([f"91{normalized_mobile}", f"+91{normalized_mobile}"])
            
            # Search for existing analysis
            existing_analysis = None
            
            # If week and month are provided, search for specific week analysis
            if week is not None and month is not None:
                print(f"[trigger-weekly-progress] 🔍 Looking for Week {week}, Month {month} analysis")
                
                for search_id in search_ids:
                    # Search by _id and check analysis.week and analysis.month
                    found_doc = collection.find_one({
                        '_id': search_id,
                        'analysis.week': week,
                        'analysis.month': month
                    })
                    if found_doc:
                        existing_analysis = found_doc
                        print(f"[trigger-weekly-progress] ✅ Found existing analysis for Week {week}, Month {month}")
                        break
                
                # If not found by _id, try by mobile field
                if not existing_analysis:
                    for search_id in search_ids:
                        found_doc = collection.find_one({
                            'mobile': search_id,
                            'analysis.week': week,
                            'analysis.month': month
                        })
                        if found_doc:
                            existing_analysis = found_doc
                            print(f"[trigger-weekly-progress] ✅ Found existing analysis for Week {week}, Month {month} by mobile field")
                            break
            else:
                # If week/month not provided, just check if any analysis exists for this user
                print(f"[trigger-weekly-progress] 🔍 Looking for any existing analysis")
                
                for search_id in search_ids:
                    found_doc = collection.find_one({'_id': search_id})
                    if found_doc:
                        existing_analysis = found_doc
                        print(f"[trigger-weekly-progress] ✅ Found existing analysis")
                        break
                
                if not existing_analysis:
                    for search_id in search_ids:
                        found_doc = collection.find_one({'mobile': search_id})
                        if found_doc:
                            existing_analysis = found_doc
                            print(f"[trigger-weekly-progress] ✅ Found existing analysis by mobile field")
                            break
            
            # If analysis exists, return it without triggering webhook
            if existing_analysis:
                print(f"[trigger-weekly-progress] 📊 Analysis already exists in database - returning cached data")
                
                # Convert ObjectId to string if present
                if '_id' in existing_analysis:
                    existing_analysis['_id'] = str(existing_analysis['_id'])
                
                return jsonify({
                    'success': True,
                    'message': 'Analysis already exists in database',
                    'data': {
                        'status': 'exists',
                        'cached': True,
                        'mobile': mobile,
                        'analysis': existing_analysis.get('analysis', {}),
                        'redirect_to_progress': True
                    }
                }), 200
            
            print(f"[trigger-weekly-progress] ⚠️ No existing analysis found - will trigger webhook")
            
        except Exception as db_check_error:
            print(f"[trigger-weekly-progress] ⚠️ Error checking database: {str(db_check_error)}")
            print(f"[trigger-weekly-progress] Will proceed with webhook trigger")
        
        # ===== STEP 2: If no existing analysis, trigger webhook =====
        
        # Get webhook URL from environment
        webhook_url = os.getenv('N8N_PROGRESS_TRACKING_WEEKLY_WEBHOOK')
        
        print(f"[trigger-weekly-progress] Webhook URL from env: {webhook_url}")
        
        if not webhook_url:
            print(f"[trigger-weekly-progress] ERROR: Webhook URL not configured in .env")
            return jsonify({
                'success': False,
                'message': 'Weekly progress webhook URL not configured in environment variables'
            }), 500
        
        print(f"[trigger-weekly-progress] ✓ Triggering webhook for mobile: {mobile}")
        print(f"[trigger-weekly-progress] ✓ Webhook URL: {webhook_url}")
        
        # Send request to N8N webhook
        import requests
        webhook_payload = {'mobile': mobile}
        if week is not None:
            webhook_payload['week'] = week
        if month is not None:
            webhook_payload['month'] = month
            
        response = requests.post(
            webhook_url,
            json=webhook_payload,
            timeout=15
        )
        
        print(f"[trigger-weekly-progress] ✓ Webhook response status: {response.status_code}")
        print(f"[trigger-weekly-progress] ✓ Webhook response body: {response.text[:500]}")
        
        if response.status_code == 200 or response.status_code == 201:
            try:
                webhook_data = response.json()
                print(f"[trigger-weekly-progress] ✓ SUCCESS - Webhook data: {webhook_data}")
                return jsonify({
                    'success': True,
                    'message': 'Weekly test analysis triggered successfully',
                    'data': webhook_data
                }), 200
            except Exception as json_err:
                print(f"[trigger-weekly-progress] ⚠️ Could not parse JSON response: {json_err}")
                return jsonify({
                    'success': True,
                    'message': 'Weekly test analysis triggered successfully',
                    'data': {
                        'status': 'Processing',
                        'mobile': mobile,
                        'response': response.text[:200]
                    }
                }), 200
        else:
            print(f"[trigger-weekly-progress] ❌ Webhook returned non-200 status: {response.status_code}")
            return jsonify({
                'success': False,
                'message': f'Webhook returned status {response.status_code}',
                'details': response.text[:500]
            }), response.status_code
            
    except requests.Timeout:
        print(f"[trigger-weekly-progress] ❌ TIMEOUT - Webhook request timed out")
        return jsonify({
            'success': False,
            'message': 'Webhook request timeout. The service might be slow.'
        }), 504
    except Exception as e:
        print(f"[trigger-weekly-progress] ❌ EXCEPTION: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': 'Failed to trigger weekly progress webhook',
            'error': str(e)
        }), 500


@app.route('/api/weekly-test-analysis/<mobile>', methods=['GET'])
def get_weekly_test_analysis(mobile):
    """
    Fetch ALL Weekly Test Analysis data for a user from Weekly_test_analysis collection
    Returns data organized by month and week for hierarchical display
    
    Args:
        mobile: User's mobile number
    
    Returns:
        JSON with all user's weekly test analyses organized by month/week
    """
    try:
        print(f"[weekly-test-analysis] Fetching all analyses for mobile: {mobile}")
        
        if not mobile:
            return jsonify({
                'success': False,
                'message': 'Mobile number is required'
            }), 400
        
        # Normalize mobile number - keep only digits
        normalized_mobile = ''.join(filter(str.isdigit, mobile))
        
        # Try with last 10 digits (common format)
        mobile_10 = normalized_mobile[-10:] if len(normalized_mobile) >= 10 else normalized_mobile
        
        print(f"[weekly-test-analysis] Normalized mobile: {normalized_mobile}, 10-digit: {mobile_10}")
        
        # Connect to MongoDB
        mongo_uri = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
        db_name = os.getenv('MONGODB_DB', 'Placement_Ai')
        
        client = MongoClient(mongo_uri)
        db = client[db_name]
        collection = db['Weekly_test_analysis']
        
        # Build search query for multiple mobile formats
        search_ids = [mobile, normalized_mobile, mobile_10]
        if len(normalized_mobile) == 10:
            search_ids.extend([f"91{normalized_mobile}", f"+91{normalized_mobile}"])
        
        # Find ALL documents for this user (by _id or mobile field)
        documents = []
        
        # Search by _id
        for search_id in search_ids:
            found_docs = list(collection.find({'_id': search_id}))
            if found_docs:
                documents.extend(found_docs)
                print(f"[weekly-test-analysis] Found {len(found_docs)} document(s) with _id: {search_id}")
                break
        
        # If no documents found by _id, search by mobile field
        if not documents:
            for search_id in search_ids:
                found_docs = list(collection.find({'mobile': search_id}))
                if found_docs:
                    documents.extend(found_docs)
                    print(f"[weekly-test-analysis] Found {len(found_docs)} document(s) with mobile: {search_id}")
                    break
        
        # Also search by mobile field with regex for partial matches
        if not documents:
            import re
            for search_id in search_ids:
                # Escape special regex characters in the search_id
                escaped_search_id = re.escape(search_id)
                found_docs = list(collection.find({'mobile': {'$regex': escaped_search_id}}))
                if found_docs:
                    documents.extend(found_docs)
                    print(f"[weekly-test-analysis] Found {len(found_docs)} document(s) with mobile regex: {search_id}")
                    break
        
        if not documents:
            print(f"[weekly-test-analysis] No analysis found for mobile: {mobile}")
            return jsonify({
                'success': False,
                'message': 'No weekly test analysis found for this user. Please complete a weekly test first.'
            }), 404
        
        # Organize documents by month and week
        organized_data = {}
        
        for doc in documents:
            # Convert ObjectId to string if present
            if '_id' in doc:
                doc['_id'] = str(doc['_id'])
            
            # Extract month and week from analysis
            analysis = doc.get('analysis', {})
            month = analysis.get('month', 1)
            week = analysis.get('week', 1)
            
            month_key = f"month_{month}"
            week_key = f"week_{week}"
            
            if month_key not in organized_data:
                organized_data[month_key] = {
                    'month': month,
                    'month_label': f"Month {month}",
                    'weeks': {}
                }
            
            organized_data[month_key]['weeks'][week_key] = {
                'week': week,
                'week_label': f"Week {week}",
                'analysis': analysis,
                'mobile': doc.get('mobile'),
                '_id': doc.get('_id')
            }
        
        # Convert to sorted list format for easier frontend rendering
        months_list = []
        for month_key in sorted(organized_data.keys(), key=lambda x: int(x.split('_')[1])):
            month_data = organized_data[month_key]
            weeks_list = []
            for week_key in sorted(month_data['weeks'].keys(), key=lambda x: int(x.split('_')[1])):
                weeks_list.append(month_data['weeks'][week_key])
            
            months_list.append({
                'month': month_data['month'],
                'month_label': month_data['month_label'],
                'weeks': weeks_list
            })
        
        print(f"[weekly-test-analysis] Successfully organized {len(documents)} analyses into {len(months_list)} months")
        
        return jsonify({
            'success': True,
            'data': {
                'mobile': mobile,
                'total_analyses': len(documents),
                'months': months_list
            }
        }), 200
        
    except Exception as e:
        print(f"[weekly-test-analysis] Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': 'Failed to fetch weekly test analysis',
            'error': str(e)
        }), 500


@app.route('/api/record-roadmap-completion', methods=['POST'])
def record_roadmap_completion():
    """
    Record when a roadmap is first detected/generated.
    This is used for timer tracking before allowing first weekly test generation.
    """
    try:
        data = request.get_json()
        mobile = data.get('mobile')
        
        if not mobile:
            return jsonify({
                'success': False,
                'error': 'Missing required field: mobile'
            }), 400
        
        print(f"[record-roadmap] Recording roadmap completion for mobile: {mobile}")
        
        # Connect to MongoDB
        mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI")
        if not mongo_uri:
            return jsonify({
                'success': False,
                'error': 'Database connection not configured'
            }), 500
            
        client = MongoClient(mongo_uri)
        db = client[os.getenv("MONGODB_DB", "Placement_Ai")]
        tracking_collection = db["analysis_timer_tracking"]
        
        # Create unique ID for roadmap tracking
        tracking_id = f"{mobile}_roadmap"
        
        # Only insert if not exists (don't overwrite first detection time)
        existing = tracking_collection.find_one({'_id': tracking_id})
        
        if existing:
            print(f"[record-roadmap] Already recorded at: {existing.get('completed_at')}")
            client.close()
            return jsonify({
                'success': True,
                'message': 'Already recorded',
                'completed_at': str(existing.get('completed_at'))
            }), 200
        
        # Insert new record
        now = datetime.utcnow()
        tracking_collection.insert_one({
            '_id': tracking_id,
            'mobile': mobile,
            'type': 'roadmap',
            'completed_at': now
        })
        
        print(f"[record-roadmap] Recorded completion at: {now}")
        client.close()
        
        return jsonify({
            'success': True,
            'message': 'Recorded successfully',
            'completed_at': str(now)
        }), 200
        
    except Exception as e:
        print(f"[record-roadmap] Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/roadmap-timer-status/<mobile>', methods=['GET'])
def get_roadmap_timer_status(mobile):
    """
    Check the status of roadmap generation timer before allowing first weekly test.
    
    After roadmap is generated, there's a 5-minute timer before the first weekly test can be generated.
    This applies only to Week 1, Month 1 (the very first week).
    
    Returns:
    - roadmap_exists: bool (whether roadmap exists for this user)
    - roadmap_completed_at: timestamp (when roadmap was first detected)
    - timer_duration: int (total timer duration in seconds - 300 for 5 min)
    - timer_remaining: int (seconds remaining if timer active)
    - can_generate_test: bool (whether timer has passed and first test can be generated)
    """
    try:
        if not mobile:
            return jsonify({
                'success': False,
                'error': 'Mobile number is required'
            }), 400
        
        print(f"[roadmap-timer] Checking timer status for mobile: {mobile}")
        
        # Connect to MongoDB
        mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI")
        if not mongo_uri:
            return jsonify({
                'success': False,
                'error': 'Database connection not configured'
            }), 500
            
        client = MongoClient(mongo_uri)
        db = client[os.getenv("MONGODB_DB", "Placement_Ai")]
        
        # First check if roadmap exists
        roadmap_collection = db['Roadmap_Dashboard ']  # Note: trailing space
        
        # Normalize mobile number formats to search
        normalized_mobile = mobile.replace("+", "").replace(" ", "").replace("-", "")
        mobile_10 = normalized_mobile[-10:] if len(normalized_mobile) >= 10 else normalized_mobile
        
        search_ids = [mobile, normalized_mobile, mobile_10]
        if len(normalized_mobile) == 10:
            search_ids.extend([
                f"91{normalized_mobile}",
                f"+91{normalized_mobile}",
                f"+91 {mobile_10}"
            ])
        
        # Search for roadmap document
        roadmap_doc = None
        for search_id in search_ids:
            roadmap_doc = roadmap_collection.find_one({'_id': search_id})
            if roadmap_doc:
                print(f"[roadmap-timer] Found roadmap with _id: {search_id}")
                break
            roadmap_doc = roadmap_collection.find_one({'mobile': search_id})
            if roadmap_doc:
                print(f"[roadmap-timer] Found roadmap with mobile: {search_id}")
                break
        
        if not roadmap_doc:
            print(f"[roadmap-timer] No roadmap found")
            client.close()
            return jsonify({
                'success': True,
                'data': {
                    'mobile': mobile,
                    'roadmap_exists': False,
                    'roadmap_completed_at': None,
                    'timer_duration': 0,
                    'timer_remaining': 0,
                    'can_generate_test': False
                }
            }), 200
        
        # Roadmap exists - check tracking collection for timestamp
        tracking_collection = db["analysis_timer_tracking"]
        
        # Search for tracking record with any mobile format
        tracking_doc = None
        for search_id in search_ids:
            tracking_doc = tracking_collection.find_one({'_id': f"{search_id}_roadmap"})
            if tracking_doc:
                print(f"[roadmap-timer] Found tracking with _id: {search_id}_roadmap")
                break
        
        roadmap_completed_at = None
        timer_duration = 300  # 5 minutes
        
        if tracking_doc:
            roadmap_completed_at = tracking_doc.get('completed_at')
            print(f"[roadmap-timer] Found tracking timestamp: {roadmap_completed_at}")
        
        # Calculate timer status
        can_generate_test = False
        timer_remaining = 0
        
        if roadmap_completed_at:
            # Parse the timestamp
            if isinstance(roadmap_completed_at, str):
                try:
                    try:
                        from dateutil import parser as date_parser
                        completed_time = date_parser.parse(roadmap_completed_at)
                    except ImportError:
                        try:
                            completed_time = datetime.fromisoformat(roadmap_completed_at.replace('Z', '+00:00'))
                        except:
                            print(f"[roadmap-timer] Could not parse timestamp: {roadmap_completed_at}")
                            completed_time = datetime.utcnow()
                except Exception as e:
                    print(f"[roadmap-timer] Error parsing timestamp: {e}")
                    completed_time = datetime.utcnow()
            elif isinstance(roadmap_completed_at, datetime):
                completed_time = roadmap_completed_at
            else:
                print(f"[roadmap-timer] Unknown timestamp type: {type(roadmap_completed_at)}")
                completed_time = datetime.utcnow()
            
            # Make sure completed_time is naive for comparison
            if completed_time.tzinfo is not None:
                try:
                    utc_offset = completed_time.utcoffset()
                    if utc_offset is not None:
                        completed_time = (completed_time - utc_offset).replace(tzinfo=None)
                    else:
                        completed_time = completed_time.replace(tzinfo=None)
                except Exception as tz_err:
                    print(f"[roadmap-timer] Timezone conversion error: {tz_err}")
                    completed_time = completed_time.replace(tzinfo=None)
            
            # Calculate elapsed time
            elapsed_seconds = (datetime.utcnow() - completed_time).total_seconds()
            print(f"[roadmap-timer] Elapsed seconds since roadmap: {elapsed_seconds}")
            
            if elapsed_seconds >= timer_duration:
                can_generate_test = True
                timer_remaining = 0
            else:
                can_generate_test = False
                timer_remaining = int(timer_duration - elapsed_seconds)
        else:
            # No timestamp found - roadmap exists but we haven't recorded it yet
            # This means it's a new roadmap, timer should start now
            print(f"[roadmap-timer] No timestamp found, roadmap just detected - timer starts now")
            can_generate_test = False
            timer_remaining = timer_duration
        
        print(f"[roadmap-timer] can_generate_test: {can_generate_test}, timer_remaining: {timer_remaining}")
        
        client.close()
        
        return jsonify({
            'success': True,
            'data': {
                'mobile': mobile,
                'roadmap_exists': True,
                'roadmap_completed_at': str(roadmap_completed_at) if roadmap_completed_at else None,
                'timer_duration': timer_duration,
                'timer_remaining': timer_remaining,
                'can_generate_test': can_generate_test
            }
        }), 200
        
    except Exception as e:
        print(f"[roadmap-timer] Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/record-analysis-completion', methods=['POST'])
def record_analysis_completion():
    """
    Record when an analysis (weekly or monthly) is first detected/completed.
    This is used for timer tracking since analysis documents don't have timestamps.
    """
    try:
        data = request.get_json()
        mobile = data.get('mobile')
        analysis_type = data.get('type')  # 'weekly' or 'monthly'
        week = data.get('week')
        month = data.get('month')
        
        if not mobile or not analysis_type or not month:
            return jsonify({
                'success': False,
                'error': 'Missing required fields: mobile, type, month'
            }), 400
        
        print(f"[record-analysis] Recording {analysis_type} analysis completion for mobile: {mobile}")
        
        # Connect to MongoDB
        mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI")
        if not mongo_uri:
            return jsonify({
                'success': False,
                'error': 'Database connection not configured'
            }), 500
            
        client = MongoClient(mongo_uri)
        db = client[os.getenv("MONGODB_DB", "Placement_Ai")]
        tracking_collection = db["analysis_timer_tracking"]
        
        # Create unique ID based on analysis type
        if analysis_type == 'weekly':
            tracking_id = f"{mobile}_weekly_{week}_{month}"
        else:
            tracking_id = f"{mobile}_monthly_{month}"
        
        # Only insert if not exists (don't overwrite first detection time)
        existing = tracking_collection.find_one({'_id': tracking_id})
        
        if existing:
            print(f"[record-analysis] Already recorded at: {existing.get('completed_at')}")
            client.close()
            return jsonify({
                'success': True,
                'message': 'Already recorded',
                'completed_at': str(existing.get('completed_at'))
            }), 200
        
        # Insert new record
        now = datetime.utcnow()
        tracking_collection.insert_one({
            '_id': tracking_id,
            'mobile': mobile,
            'type': analysis_type,
            'week': week,
            'month': month,
            'completed_at': now
        })
        
        print(f"[record-analysis] Recorded completion at: {now}")
        client.close()
        
        return jsonify({
            'success': True,
            'message': 'Recorded successfully',
            'completed_at': str(now)
        }), 200
        
    except Exception as e:
        print(f"[record-analysis] Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/weekly-analysis-timer-status/<mobile>/<int:week>/<int:month>', methods=['GET'])
def get_weekly_analysis_timer_status(mobile, week, month):
    """
    Check the status of weekly test analysis completion and timer for generating next test.
    
    After weekly test analysis is completed:
    - For weeks 1, 2, 3 of a month cycle (not divisible by 4): 5 minute timer before next week test can be generated
    - For week 4, 8, 12 etc. (divisible by 4): 3 minute timer before monthly test can be generated
    
    After monthly test analysis is completed: 5 minute timer before next week test can be generated
    
    Returns:
    - analysis_exists: bool (whether analysis exists for this week)
    - analysis_completed_at: timestamp (when analysis was completed)
    - timer_duration: int (total timer duration in seconds - 300 for 5 min, 180 for 3 min)
    - timer_remaining: int (seconds remaining if timer active)
    - can_generate_next: bool (whether timer has passed and next test can be generated)
    - next_action: string ('generate_weekly_test' or 'generate_monthly_test')
    """
    try:
        if not mobile:
            return jsonify({
                'success': False,
                'error': 'Mobile number is required'
            }), 400
        
        print(f"[weekly-analysis-timer] Checking timer status for mobile: {mobile}, week: {week}, month: {month}")
        
        # Connect to MongoDB
        mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI")
        if not mongo_uri:
            return jsonify({
                'success': False,
                'error': 'Database connection not configured'
            }), 500
            
        client = MongoClient(mongo_uri)
        db = client[os.getenv("MONGODB_DB", "Placement_Ai")]
        analysis_collection = db["Weekly_test_analysis"]
        
        # Normalize mobile number formats to search
        normalized_mobile = mobile.replace("+", "").replace(" ", "").replace("-", "")
        mobile_10 = normalized_mobile[-10:] if len(normalized_mobile) >= 10 else normalized_mobile
        
        search_ids = [mobile, normalized_mobile, mobile_10]
        if len(normalized_mobile) == 10:
            search_ids.extend([
                f"91{normalized_mobile}",
                f"+91{normalized_mobile}",
                f"+91 {mobile_10}"
            ])
        
        # Search for analysis document for this specific week/month
        analysis_doc = None
        
        for search_id in search_ids:
            # Try by mobile field with analysis.week and analysis.month
            analysis_doc = analysis_collection.find_one({
                'mobile': search_id,
                'analysis.week': week,
                'analysis.month': month
            })
            if analysis_doc:
                print(f"[weekly-analysis-timer] Found analysis with mobile: {search_id}")
                break
            
            # Try by _id pattern: mobile_week_X
            analysis_doc = analysis_collection.find_one({
                '_id': f'{search_id}_week_{week}',
                'analysis.month': month
            })
            if analysis_doc:
                print(f"[weekly-analysis-timer] Found analysis with _id pattern: {search_id}_week_{week}")
                break
        
        if not analysis_doc:
            print(f"[weekly-analysis-timer] No analysis found for Week {week}, Month {month}")
            client.close()
            return jsonify({
                'success': True,
                'data': {
                    'mobile': mobile,
                    'week': week,
                    'month': month,
                    'analysis_exists': False,
                    'analysis_completed_at': None,
                    'timer_duration': 0,
                    'timer_remaining': 0,
                    'can_generate_next': False,
                    'next_action': None
                }
            }), 200
        
        # Analysis exists - check tracking collection for timestamp
        tracking_collection = db["analysis_timer_tracking"]
        tracking_id = f"{mobile}_weekly_{week}_{month}"
        tracking_doc = tracking_collection.find_one({'_id': tracking_id})
        
        analysis_completed_at = None
        if tracking_doc:
            analysis_completed_at = tracking_doc.get('completed_at')
            print(f"[weekly-analysis-timer] Found tracking timestamp: {analysis_completed_at}")
        
        # Fallback to analysis doc timestamps
        if not analysis_completed_at:
            analysis_completed_at = (
                analysis_doc.get('createdAt') or 
                analysis_doc.get('created_at') or
                analysis_doc.get('timestamp') or
                analysis_doc.get('analysis', {}).get('createdAt') or
                analysis_doc.get('analysis', {}).get('timestamp')
            )
        
        # If no timestamp field, try to get from ObjectId
        if not analysis_completed_at and '_id' in analysis_doc:
            try:
                from bson import ObjectId
                if isinstance(analysis_doc['_id'], ObjectId):
                    analysis_completed_at = analysis_doc['_id'].generation_time
                    print(f"[weekly-analysis-timer] Using ObjectId generation time: {analysis_completed_at}")
            except Exception as e:
                print(f"[weekly-analysis-timer] Could not get ObjectId generation time: {e}")
        
        # Determine timer duration based on week number
        # Week 4, 8, 12, etc. (divisible by 4) = 3 minutes before monthly test
        # All other weeks = 5 minutes before next weekly test
        is_month_end_week = (week % 4 == 0)
        timer_duration = 180 if is_month_end_week else 300  # 3 min or 5 min
        next_action = 'generate_monthly_test' if is_month_end_week else 'generate_weekly_test'
        
        print(f"[weekly-analysis-timer] Week {week} is {'month-end' if is_month_end_week else 'regular'} week")
        print(f"[weekly-analysis-timer] Timer duration: {timer_duration}s, Next action: {next_action}")
        
        # Calculate timer status
        can_generate_next = False
        timer_remaining = 0
        
        if analysis_completed_at:
            # Parse the timestamp
            if isinstance(analysis_completed_at, str):
                try:
                    try:
                        from dateutil import parser as date_parser
                        completed_time = date_parser.parse(analysis_completed_at)
                    except ImportError:
                        try:
                            completed_time = datetime.fromisoformat(analysis_completed_at.replace('Z', '+00:00'))
                        except:
                            print(f"[weekly-analysis-timer] Could not parse timestamp: {analysis_completed_at}")
                            completed_time = datetime.utcnow()
                except Exception as e:
                    print(f"[weekly-analysis-timer] Error parsing timestamp: {e}")
                    completed_time = datetime.utcnow()
            elif isinstance(analysis_completed_at, datetime):
                completed_time = analysis_completed_at
            else:
                print(f"[weekly-analysis-timer] Unknown timestamp type: {type(analysis_completed_at)}")
                completed_time = datetime.utcnow()
            
            # Make sure completed_time is naive for comparison
            if completed_time.tzinfo is not None:
                try:
                    utc_offset = completed_time.utcoffset()
                    if utc_offset is not None:
                        completed_time = (completed_time - utc_offset).replace(tzinfo=None)
                    else:
                        completed_time = completed_time.replace(tzinfo=None)
                except Exception as tz_err:
                    print(f"[weekly-analysis-timer] Timezone conversion error: {tz_err}")
                    completed_time = completed_time.replace(tzinfo=None)
            
            # Calculate elapsed time
            elapsed_seconds = (datetime.utcnow() - completed_time).total_seconds()
            print(f"[weekly-analysis-timer] Elapsed seconds since analysis: {elapsed_seconds}")
            
            if elapsed_seconds >= timer_duration:
                can_generate_next = True
                timer_remaining = 0
            else:
                can_generate_next = False
                timer_remaining = int(timer_duration - elapsed_seconds)
        else:
            # No timestamp found - allow generating immediately
            print(f"[weekly-analysis-timer] No timestamp found, allowing immediate generation")
            can_generate_next = True
            timer_remaining = 0
        
        print(f"[weekly-analysis-timer] can_generate_next: {can_generate_next}, timer_remaining: {timer_remaining}")
        
        client.close()
        
        return jsonify({
            'success': True,
            'data': {
                'mobile': mobile,
                'week': week,
                'month': month,
                'analysis_exists': True,
                'analysis_completed_at': str(analysis_completed_at) if analysis_completed_at else None,
                'timer_duration': timer_duration,
                'timer_remaining': timer_remaining,
                'can_generate_next': can_generate_next,
                'next_action': next_action,
                'is_month_end_week': is_month_end_week
            }
        }), 200
        
    except Exception as e:
        print(f"[weekly-analysis-timer] Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/monthly-analysis-timer-status/<mobile>/<int:month>', methods=['GET'])
def get_monthly_analysis_timer_status(mobile, month):
    """
    Check the status of monthly test analysis completion and timer for generating next week test.
    
    After monthly test analysis is completed: 5 minute timer before next week test can be generated
    
    Returns:
    - analysis_exists: bool (whether monthly analysis exists)
    - analysis_completed_at: timestamp (when analysis was completed)
    - timer_duration: int (300 seconds = 5 minutes)
    - timer_remaining: int (seconds remaining if timer active)
    - can_generate_next: bool (whether timer has passed and next week test can be generated)
    - next_week: int (the next week number to generate)
    """
    try:
        if not mobile:
            return jsonify({
                'success': False,
                'error': 'Mobile number is required'
            }), 400
        
        print(f"[monthly-analysis-timer] Checking timer status for mobile: {mobile}, month: {month}")
        
        # Connect to MongoDB
        mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI")
        if not mongo_uri:
            return jsonify({
                'success': False,
                'error': 'Database connection not configured'
            }), 500
            
        client = MongoClient(mongo_uri)
        db = client[os.getenv("MONGODB_DB", "Placement_Ai")]
        monthly_analysis_collection = db["monthly_test_analysis"]
        
        # Normalize mobile number formats to search
        normalized_mobile = mobile.replace("+", "").replace(" ", "").replace("-", "")
        mobile_10 = normalized_mobile[-10:] if len(normalized_mobile) >= 10 else normalized_mobile
        
        search_ids = [mobile, normalized_mobile, mobile_10]
        if len(normalized_mobile) == 10:
            search_ids.extend([
                f"91{normalized_mobile}",
                f"+91{normalized_mobile}",
                f"+91 {mobile_10}"
            ])
        
        # Search for monthly analysis document
        analysis_doc = None
        
        for search_id in search_ids:
            # Try by mobile field with month
            analysis_doc = monthly_analysis_collection.find_one({
                'mobile': search_id,
                'month': {'$in': [month, str(month)]}
            })
            if analysis_doc:
                print(f"[monthly-analysis-timer] Found analysis with mobile: {search_id}")
                break
            
            # Try by _id pattern: mobile_month_X
            analysis_doc = monthly_analysis_collection.find_one({
                '_id': f'{search_id}_month_{month}'
            })
            if analysis_doc:
                print(f"[monthly-analysis-timer] Found analysis with _id pattern")
                break
        
        # Calculate next week number (first week of next month)
        next_week = (month * 4) + 1
        
        if not analysis_doc:
            print(f"[monthly-analysis-timer] No monthly analysis found for Month {month}")
            client.close()
            return jsonify({
                'success': True,
                'data': {
                    'mobile': mobile,
                    'month': month,
                    'analysis_exists': False,
                    'analysis_completed_at': None,
                    'timer_duration': 0,
                    'timer_remaining': 0,
                    'can_generate_next': False,
                    'next_week': next_week
                }
            }), 200
        
        # Analysis exists - check tracking collection for timestamp
        tracking_collection = db["analysis_timer_tracking"]
        tracking_id = f"{mobile}_monthly_{month}"
        tracking_doc = tracking_collection.find_one({'_id': tracking_id})
        
        analysis_completed_at = None
        if tracking_doc:
            analysis_completed_at = tracking_doc.get('completed_at')
            print(f"[monthly-analysis-timer] Found tracking timestamp: {analysis_completed_at}")
        
        # Fallback to analysis doc timestamps
        if not analysis_completed_at:
            analysis_completed_at = (
                analysis_doc.get('analysisDate') or
                analysis_doc.get('createdAt') or 
                analysis_doc.get('created_at') or
                analysis_doc.get('timestamp') or
                analysis_doc.get('analysis', {}).get('createdAt') if isinstance(analysis_doc.get('analysis'), dict) else None
            )
        
        # If no timestamp field, try to get from ObjectId
        if not analysis_completed_at and '_id' in analysis_doc:
            try:
                from bson import ObjectId
                if isinstance(analysis_doc['_id'], ObjectId):
                    analysis_completed_at = analysis_doc['_id'].generation_time
            except Exception:
                pass
        
        # Timer is always 5 minutes (300 seconds) after monthly analysis
        timer_duration = 300
        
        # Calculate timer status
        can_generate_next = False
        timer_remaining = 0
        
        if analysis_completed_at:
            # Parse the timestamp
            if isinstance(analysis_completed_at, str):
                try:
                    try:
                        from dateutil import parser as date_parser
                        completed_time = date_parser.parse(analysis_completed_at)
                    except ImportError:
                        try:
                            completed_time = datetime.fromisoformat(analysis_completed_at.replace('Z', '+00:00'))
                        except:
                            completed_time = datetime.utcnow()
                except Exception:
                    completed_time = datetime.utcnow()
            elif isinstance(analysis_completed_at, datetime):
                completed_time = analysis_completed_at
            else:
                completed_time = datetime.utcnow()
            
            # Make sure completed_time is naive for comparison
            if completed_time.tzinfo is not None:
                try:
                    utc_offset = completed_time.utcoffset()
                    if utc_offset is not None:
                        completed_time = (completed_time - utc_offset).replace(tzinfo=None)
                    else:
                        completed_time = completed_time.replace(tzinfo=None)
                except Exception:
                    completed_time = completed_time.replace(tzinfo=None)
            
            # Calculate elapsed time
            elapsed_seconds = (datetime.utcnow() - completed_time).total_seconds()
            print(f"[monthly-analysis-timer] Elapsed seconds since analysis: {elapsed_seconds}")
            
            if elapsed_seconds >= timer_duration:
                can_generate_next = True
                timer_remaining = 0
            else:
                can_generate_next = False
                timer_remaining = int(timer_duration - elapsed_seconds)
        else:
            # No timestamp found - allow generating immediately
            can_generate_next = True
            timer_remaining = 0
        
        print(f"[monthly-analysis-timer] can_generate_next: {can_generate_next}, timer_remaining: {timer_remaining}")
        
        client.close()
        
        return jsonify({
            'success': True,
            'data': {
                'mobile': mobile,
                'month': month,
                'analysis_exists': True,
                'analysis_completed_at': str(analysis_completed_at) if analysis_completed_at else None,
                'timer_duration': timer_duration,
                'timer_remaining': timer_remaining,
                'can_generate_next': can_generate_next,
                'next_week': next_week
            }
        }), 200
        
    except Exception as e:
        print(f"[monthly-analysis-timer] Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/certifications/<mobile>', methods=['GET'])
def get_certifications(mobile):
    """
    Fetch certifications for a user based on their mobile number
    Returns free and paid certifications from the Certification collection
    
    Args:
        mobile: User's mobile number
    
    Returns:
        JSON with free and paid certifications
    """
    try:
        print(f"[certifications] Fetching certifications for mobile: {mobile}")
        
        if not mobile:
            return jsonify({
                'success': False,
                'message': 'Mobile number is required'
            }), 400
        
        db = get_db()
        certification_collection = db['Certification']
        
        # Normalize mobile number (add +91 prefix if not present)
        normalized_mobile = mobile if mobile.startswith('+91') else f'+91 {mobile}'
        
        # Try to find certification by mobile number
        certification_doc = certification_collection.find_one({
            '$or': [
                {'_id': normalized_mobile},
                {'mobile': normalized_mobile},
                {'_id': mobile},
                {'mobile': mobile}
            ]
        })
        
        if not certification_doc:
            print(f"[certifications] No certifications found for mobile: {mobile}")
            return jsonify({
                'success': False,
                'message': 'No certifications found for this user'
            }), 404
        
        # Extract free and paid certifications
        free_certifications = certification_doc.get('unpaid_courses', [])
        paid_certifications = certification_doc.get('paid_courses', [])
        top_recommendations = certification_doc.get('top_recommendations', [])
        job_role = certification_doc.get('job_role', '')
        
        print(f"[certifications] Found {len(free_certifications)} free and {len(paid_certifications)} paid certifications")
        
        return jsonify({
            'success': True,
            'data': {
                'job_role': job_role,
                'free_certifications': free_certifications,
                'paid_certifications': paid_certifications,
                'top_recommendations': top_recommendations
            }
        }), 200
        
    except Exception as e:
        print(f"[certifications] Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': 'Failed to fetch certifications',
            'error': str(e)
        }), 500


@app.route('/api/current-week-info/<mobile>', methods=['GET'])
def get_current_week_info(mobile):
    """
    Get current week and month info based on completed weekly test analyses
    Current week = highest analyzed week + 1 (next unlocked week)
    """
    try:
        print(f"[current-week-info] Fetching week info for mobile: {mobile}")
        
        # Normalize mobile number
        normalized_mobile = ''.join(filter(str.isdigit, mobile))
        mobile_10 = normalized_mobile[-10:] if len(normalized_mobile) >= 10 else normalized_mobile
        
        # Connect to MongoDB
        mongo_uri = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
        db_name = os.getenv('MONGODB_DB', 'Placement_Ai')
        
        client = MongoClient(mongo_uri)
        db = client[db_name]
        
        # Check Weekly_test_analysis collection to find completed analyses
        analysis_collection = db['Weekly_test_analysis']
        
        # Build search IDs
        search_ids = [mobile, normalized_mobile, mobile_10]
        if len(normalized_mobile) == 10:
            search_ids.extend([
                f"91{normalized_mobile}",
                f"+91{normalized_mobile}",
                f"+91 {mobile_10}"  # Format with space: "+91 1234567890"
            ])
        
        # Find all completed analyses for this user
        completed_weeks = []
        for search_id in search_ids:
            analyses = list(analysis_collection.find({'mobile': search_id}))
            if analyses:
                print(f"[current-week-info] Found {len(analyses)} completed analyses for {search_id}")
                for analysis in analyses:
                    # Check if analysis has week info
                    if 'analysis' in analysis and 'week' in analysis['analysis']:
                        week_num = analysis['analysis']['week']
                        completed_weeks.append(week_num)
                    # Also check top-level week field if present
                    elif 'week' in analysis:
                        completed_weeks.append(analysis['week'])
        
        # Determine current week based on completed analyses
        current_week = 1
        current_month = 1
        
        if completed_weeks:
            max_completed_week = max(completed_weeks)
            # Current week = next week after highest completed
            current_week = max_completed_week + 1 if max_completed_week < 12 else 12
            # Calculate month (4 weeks per month)
            current_month = ((current_week - 1) // 4) + 1
            
            print(f"[current-week-info] Completed weeks: {sorted(set(completed_weeks))}, Current week: {current_week}, Month: {current_month}")
        else:
            print(f"[current-week-info] No completed analyses found, defaulting to Week 1")
        
        return jsonify({
            'success': True,
            'data': {
                'week': current_week,
                'month': current_month,
                'test_title': f'Week {current_week} Test'
            }
        }), 200
            
    except Exception as e:
        print(f"[current-week-info] Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': 'Failed to fetch week info',
            'error': str(e)
        }), 500


@app.route('/api/get-unlocked-weeks/<mobile>', methods=['GET'])
def get_unlocked_weeks(mobile):
    """
    Get list of unlocked weeks based on completed weekly test analyses.
    Week 1 is always unlocked. Subsequent weeks unlock after previous week's test is completed.
    
    Args:
        mobile: User's mobile number
    
    Returns:
        JSON with unlocked weeks organized by month
    """
    try:
        print(f"[get-unlocked-weeks] Fetching unlocked weeks for mobile: {mobile}")
        
        if not mobile:
            return jsonify({
                'success': False,
                'message': 'Mobile number is required'
            }), 400
        
        # Normalize mobile number
        normalized_mobile = ''.join(filter(str.isdigit, mobile))
        mobile_10 = normalized_mobile[-10:] if len(normalized_mobile) >= 10 else normalized_mobile
        
        # Connect to MongoDB
        mongo_uri = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
        db_name = os.getenv('MONGODB_DB', 'Placement_Ai')
        
        client = MongoClient(mongo_uri)
        db = client[db_name]
        analysis_collection = db['Weekly_test_analysis']
        
        # Build search query for multiple mobile formats
        search_ids = [mobile, normalized_mobile, mobile_10]
        if len(normalized_mobile) == 10:
            search_ids.extend([f"91{normalized_mobile}", f"+91{normalized_mobile}", f"+91 {normalized_mobile}"])
        
        # Find all analysis documents for this user
        documents = []
        for search_id in search_ids:
            found_docs = list(analysis_collection.find({'$or': [{'_id': search_id}, {'mobile': search_id}]}))
            if found_docs:
                documents.extend(found_docs)
                break
        
        # Extract completed weeks
        completed_weeks = set()
        for doc in documents:
            analysis = doc.get('analysis', {})
            week = analysis.get('week')
            if week:
                try:
                    completed_weeks.add(int(week))
                except (ValueError, TypeError):
                    pass
        
        # Determine unlocked weeks
        # Week 1 is always unlocked
        # Week N+1 unlocks when Week N is completed
        unlocked_weeks = {1}  # Week 1 always unlocked
        
        if completed_weeks:
            max_completed = max(completed_weeks)
            # Unlock all weeks up to max_completed + 1
            for w in range(1, max_completed + 2):
                unlocked_weeks.add(w)
        
        # Organize by months (4 weeks per month)
        unlocked_by_month = {}
        for week in sorted(unlocked_weeks):
            month = ((week - 1) // 4) + 1
            month_key = f"month_{month}"
            if month_key not in unlocked_by_month:
                unlocked_by_month[month_key] = {
                    'month': month,
                    'unlocked_weeks': []
                }
            unlocked_by_month[month_key]['unlocked_weeks'].append(week)
        
        print(f"[get-unlocked-weeks] Completed weeks: {sorted(completed_weeks)}, Unlocked weeks: {sorted(unlocked_weeks)}")
        
        return jsonify({
            'success': True,
            'data': {
                'completed_weeks': sorted(list(completed_weeks)),
                'unlocked_weeks': sorted(list(unlocked_weeks)),
                'current_week': max(unlocked_weeks) if unlocked_weeks else 1,
                'months': unlocked_by_month
            }
        })
        
    except Exception as e:
        print(f"[get-unlocked-weeks] Error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/monthly-analysis/<mobile>', methods=['GET'])
def get_monthly_analysis(mobile):
    """
    Fetch all monthly test analysis for a user from monthly_test_analysis collection
    
    Args:
        mobile: User's mobile number
    
    Returns:
        JSON array with all monthly analyses sorted by month
    """
    try:
        print(f"[monthly-analysis] Fetching analyses for mobile: {mobile}")
        
        if not mobile:
            return jsonify({'error': 'Mobile number is required'}), 400
        
        # Normalize mobile number
        normalized_mobile = ''.join(filter(str.isdigit, mobile))
        mobile_10 = normalized_mobile[-10:] if len(normalized_mobile) >= 10 else normalized_mobile
        
        # Connect to MongoDB
        mongo_uri = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
        db_name = os.getenv('MONGODB_DB', 'Placement_Ai')
        
        client = MongoClient(mongo_uri)
        db = client[db_name]
        collection = db['monthly_test_analysis']
        
        # Build search patterns
        search_patterns = [mobile, normalized_mobile, mobile_10]
        if len(normalized_mobile) == 10:
            search_patterns.extend([f"91{normalized_mobile}", f"+91{normalized_mobile}"])
        
        # Find all analyses for this mobile number (including all test attempts)
        # Note: _id format is now mobile_month_testAttempt
        analyses = list(collection.find(
            {'mobile': {'$in': search_patterns}},
            {'_id': 1, 'mobile': 1, 'month': 1, 'testAttempt': 1, 'analysisDate': 1,
             'overallPerformance': 1, 'topicWiseAnalysis': 1, 'difficultyAnalysis': 1,
             'strengths': 1, 'weaknesses': 1, 'recommendations': 1, 'nextSteps': 1,
             'insights': 1, 'rawTestData': 1}
        ).sort([('month', 1), ('testAttempt', 1)]))  # Sort by month then test attempt
        
        print(f"[monthly-analysis] Found {len(analyses)} analysis document(s)")
        
        return jsonify(analyses), 200
        
    except Exception as e:
        print(f"[monthly-analysis] Error: {str(e)}")
        return jsonify({'error': 'Failed to fetch monthly analysis'}), 500


@app.route('/api/monthly-analysis/<mobile>/<int:month>', methods=['GET'])
def get_monthly_analysis_by_month(mobile, month):
    """
    Check if monthly analysis exists for specific month and latest test attempt
    
    Args:
        mobile: User's mobile number
        month: Month number (1, 2, 3)
    
    Returns:
        JSON with analysis data if exists for latest attempt, 404 if not found
    """
    try:
        print(f"[monthly-analysis-check] Checking for mobile: {mobile}, month: {month}")
        
        if not mobile:
            return jsonify({'error': 'Mobile number is required'}), 400
        
        # Normalize mobile number
        normalized_mobile = ''.join(filter(str.isdigit, mobile))
        mobile_10 = normalized_mobile[-10:] if len(normalized_mobile) >= 10 else normalized_mobile
        
        # Connect to MongoDB
        mongo_uri = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
        db_name = os.getenv('MONGODB_DB', 'Placement_Ai')
        
        client = MongoClient(mongo_uri)
        db = client[db_name]
        analysis_collection = db['monthly_test_analysis']
        result_collection = db['monthly_test_result']
        
        # Build search patterns
        search_patterns = [mobile, normalized_mobile, mobile_10]
        if len(normalized_mobile) == 10:
            search_patterns.extend([f"91{normalized_mobile}", f"+91{normalized_mobile}"])
        
        # STEP 1: Get the latest test attempt number from monthly_test_result
        # New format: _id is just mobile, filter by month field
        test_result = None
        
        # Try new format first (mobile as _id, filter by month)
        for pattern in search_patterns:
            test_result = result_collection.find_one({'_id': pattern, 'month': month})
            if test_result:
                break
        
        # Fallback: Try old format for backward compatibility
        if not test_result:
            result_id_candidates = [f"{pattern}_month_{month}" for pattern in search_patterns]
            for result_id in result_id_candidates:
                test_result = result_collection.find_one({'_id': result_id})
                if test_result:
                    break
        
        if not test_result:
            print(f"[monthly-analysis-check] No test result found for month {month}")
            return jsonify({'error': 'No test taken yet'}), 404
        
        # Get the current test attempt number
        current_test_attempt = test_result.get('testAttempt', 1)
        print(f"[monthly-analysis-check] Latest test attempt: {current_test_attempt}")
        
        # STEP 2: Check if analysis exists for this specific test attempt
        analysis = analysis_collection.find_one(
            {
                'mobile': {'$in': search_patterns},
                'month': month,
                'testAttempt': current_test_attempt
            },
            {'_id': 1, 'mobile': 1, 'month': 1, 'testAttempt': 1}
        )
        
        if analysis:
            print(f"[monthly-analysis-check] Found analysis: {analysis['_id']} for attempt {current_test_attempt}")
            return jsonify(analysis), 200
        else:
            print(f"[monthly-analysis-check] No analysis found for month {month}, attempt {current_test_attempt}")
            # Return the test attempt number so frontend can trigger webhook with it
            return jsonify({
                'error': 'Analysis not found',
                'testAttempt': current_test_attempt,
                'needsGeneration': True
            }), 404
            
    except Exception as e:
        print(f"[monthly-analysis-check] Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to check monthly analysis'}), 500


@app.route('/api/check-month-test-eligibility/<mobile>', methods=['GET'])
def check_month_test_eligibility(mobile):
    """
    Check if user is eligible for month test based on completed weekly tests
    A user can take a month test only if they've completed all 4 weeks of that month
    
    Args:
        mobile: User's mobile number
    
    Returns:
        JSON with month eligibility data showing which months are unlocked
    """
    try:
        print(f"[month-test-eligibility] Checking eligibility for mobile: {mobile}")
        
        if not mobile:
            return jsonify({
                'success': False,
                'message': 'Mobile number is required'
            }), 400
        
        # Normalize mobile number
        normalized_mobile = ''.join(filter(str.isdigit, mobile))
        mobile_10 = normalized_mobile[-10:] if len(normalized_mobile) >= 10 else normalized_mobile
        
        # Connect to MongoDB
        mongo_uri = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
        db_name = os.getenv('MONGODB_DB', 'Placement_Ai')
        
        client = MongoClient(mongo_uri)
        db = client[db_name]
        analysis_collection = db['Weekly_test_analysis']
        
        # Build search query for multiple mobile formats
        search_ids = [mobile, normalized_mobile, mobile_10]
        if len(normalized_mobile) == 10:
            search_ids.extend([
                f"91{normalized_mobile}", 
                f"+91{normalized_mobile}",
                f"+91 {mobile_10}"  # Add format with space after +91
            ])
        
        print(f"[month-test-eligibility] Searching with formats: {search_ids}")
        
        # Find all completed weekly tests for this user
        # Note: Weekly_test_analysis documents have _id like "+91 9084117332_week_1"
        # So we need to search by 'mobile' field, not '_id' field
        completed_tests = []
        for search_id in search_ids:
            found_docs = list(analysis_collection.find({'mobile': search_id}))
            if found_docs:
                print(f"[month-test-eligibility] Found {len(found_docs)} docs by mobile: {search_id}")
                completed_tests.extend(found_docs)
                break
        
        print(f"[month-test-eligibility] Total completed tests found: {len(completed_tests)}")
        
        # Track completed weeks by month
        month_completion = {}  # {1: [1, 2, 3, 4], 2: [5, 6, 7, 8], ...}
        
        for doc in completed_tests:
            analysis = doc.get('analysis', {})
            month = analysis.get('month', 1)
            week = analysis.get('week', 1)
            
            if month not in month_completion:
                month_completion[month] = []
            
            if week not in month_completion[month]:
                month_completion[month].append(week)
        
        # Check which months are unlocked (all 4 weeks completed)
        # IMPORTANT: Month 1 = weeks 1-4, Month 2 = weeks 5-8, Month 3 = weeks 9-12
        unlocked_months = []
        locked_months = []
        
        # Also check monthly test results to see if user failed (< 50%) and needs retake
        monthly_result_collection = db['monthly_test_result']
        
        # Check up to month 3 (12 weeks total = 3 months)
        for month_num in range(1, 4):
            completed_weeks = sorted(month_completion.get(month_num, []))
            
            # Determine expected weeks based on month
            if month_num == 1:
                expected_weeks = [1, 2, 3, 4]
            elif month_num == 2:
                expected_weeks = [5, 6, 7, 8]
            else:  # month 3
                expected_weeks = [9, 10, 11, 12]
            
            all_weeks_completed = len(completed_weeks) == 4 and completed_weeks == expected_weeks
            
            # Check if previous month test was passed (if not Month 1)
            can_unlock = all_weeks_completed
            blocked_by_previous_month = False
            
            if month_num > 1:
                # Check if previous month test was passed (>= 50%)
                prev_month = month_num - 1
                # Try different mobile formats
                candidates = [mobile, normalized_mobile, mobile_10]
                if len(normalized_mobile) == 10:
                    candidates.extend([f"91{normalized_mobile}", f"+91{normalized_mobile}", f"+91 {mobile_10}"])
                
                prev_month_passed = False
                
                # First, check if monthly analysis exists for previous month
                # Analysis can only exist if the test was passed, so it's proof of passing
                monthly_analysis_collection = db['monthly_test_analysis']
                for cand in candidates:
                    prev_analysis = monthly_analysis_collection.find_one({
                        'mobile': cand,
                        'month': prev_month
                    })
                    if prev_analysis:
                        prev_month_passed = True
                        break
                
                # Fallback: check monthly_test_result (may be overwritten by newer month)
                if not prev_month_passed:
                    for cand in candidates:
                        # Try new format first (mobile as _id, filter by month)
                        prev_result = monthly_result_collection.find_one({'_id': cand, 'month': prev_month})
                        # Fallback to old format
                        if not prev_result:
                            result_id = f"{cand}_month_{prev_month}"
                            prev_result = monthly_result_collection.find_one({'_id': result_id})
                        if prev_result:
                            # Support both new (scorePercentage) and old (percentage) field names
                            percentage = prev_result.get('scorePercentage') or prev_result.get('percentage', 0)
                            if percentage >= 50:
                                prev_month_passed = True
                            break
                
                # If previous month test not passed, block current month
                if not prev_month_passed:
                    can_unlock = False
                    blocked_by_previous_month = True
            
            month_data = {
                'month': month_num,
                'completed_weeks': completed_weeks,
                'expected_weeks': expected_weeks,
                'total_weeks': 4,
                'is_unlocked': can_unlock,
                'progress_percentage': (len(completed_weeks) / 4) * 100,
                'blocked_by_previous_month': blocked_by_previous_month
            }
            
            if can_unlock:
                # Check if test has been taken and passed - look for highest test_number (latest attempt)
                test_result = None
                test_passed = False
                test_percentage = None
                highest_test_number = 0
                
                for cand in candidates if month_num > 1 else [mobile, normalized_mobile, mobile_10]:
                    # Find all test results for this user and month, sorted by test_number descending
                    results = monthly_result_collection.find({
                        'mobile': cand,
                        'month': month_num
                    }).sort('testAttempt', -1).limit(1)
                    
                    for result in results:
                        test_result = result
                        # Support both new (scorePercentage) and old (percentage) field names
                        test_percentage = result.get('scorePercentage') or result.get('percentage', 0)
                        test_passed = test_percentage >= 50
                        highest_test_number = result.get('testAttempt', 1)
                        break
                    
                    if test_result:
                        break
                
                # Check if monthly analysis exists for this month
                monthly_analysis_collection = db['monthly_test_analysis']
                analysis_exists = False
                analysis_percentage = None
                
                for cand in candidates if month_num > 1 else [mobile, normalized_mobile, mobile_10]:
                    analysis_doc = monthly_analysis_collection.find_one({
                        'mobile': cand,
                        'month': month_num
                    })
                    if analysis_doc:
                        analysis_exists = True
                        # Extract score from rawTestData if available
                        raw_test_data = analysis_doc.get('rawTestData', {})
                        if isinstance(raw_test_data, dict):
                            analysis_percentage = raw_test_data.get('percentage') or raw_test_data.get('scorePercentage')
                        break
                
                # If analysis exists, it means test was passed (analysis can only be generated after passing)
                # This handles the case where result doc was overwritten by a newer month's test
                if analysis_exists:
                    test_taken = True
                    test_passed = True
                    # Use analysis percentage if result percentage is not available
                    if test_percentage is None and analysis_percentage is not None:
                        test_percentage = analysis_percentage
                else:
                    test_taken = test_result is not None
                
                month_data['test_taken'] = test_taken
                month_data['test_passed'] = test_passed
                month_data['test_percentage'] = test_percentage
                month_data['test_attempt'] = highest_test_number if test_result else 0
                month_data['analysis_completed'] = analysis_exists
                
                unlocked_months.append(month_data)
            else:
                locked_months.append(month_data)
        
        print(f"[month-test-eligibility] User has {len(unlocked_months)} unlocked months and {len(locked_months)} locked months")
        
        return jsonify({
            'success': True,
            'data': {
                'mobile': mobile,
                'unlocked_months': unlocked_months,
                'locked_months': locked_months,
                'total_completed_tests': len(completed_tests),
                'month_completion': month_completion
            }
        }), 200
        
    except Exception as e:
        print(f"[month-test-eligibility] Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': 'Failed to check month test eligibility',
            'error': str(e)
        }), 500


@app.route('/api/monthly-test-retake-status', methods=['POST'])
def monthly_test_retake_status():
    """
    Check if a user needs to retake a monthly test (score < 50%)
    
    Request body:
    {
        "mobile": "+91 9346333208",
        "month": 1
    }
    
    Returns:
    {
        "success": true,
        "needsRetake": true/false,
        "percentage": 45.5,
        "canRetake": true/false,
        "hoursRemaining": 12.5,
        "message": "..."
    }
    """
    try:
        data = request.get_json()
        mobile = data.get('mobile')
        month = data.get('month', 1)
        
        if not mobile:
            return jsonify({
                'success': False,
                'error': 'Mobile number is required'
            }), 400
        
        mobile = mobile.strip()
        
        # Connect to MongoDB
        mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI")
        if not mongo_uri:
            return jsonify({
                'success': False,
                'error': 'Database connection not configured'
            }), 500
            
        client = MongoClient(mongo_uri)
        db = client[os.getenv("MONGODB_DB", "Placement_Ai")]
        result_collection = db["monthly_test_result"]
        
        # Find the most recent test result for this user and month
        # Try different mobile formats
        candidates = [mobile]
        candidates.append(mobile.replace(' ', ''))
        candidates.append(mobile.replace('+', ''))
        digits = ''.join([c for c in mobile if c.isdigit()])
        candidates.append(digits)
        if len(digits) == 10:
            candidates.append(f"+91 {digits}")
            candidates.append(f"+91{digits}")
        
        test_result = None
        # Try new format first (mobile as _id, filter by month)
        for cand in candidates:
            test_result = result_collection.find_one({'_id': cand, 'month': month})
            if test_result:
                break
        
        # Fallback to old format for backward compatibility
        if not test_result:
            for cand in candidates:
                result_id = f"{cand}_month_{month}"
                test_result = result_collection.find_one({'_id': result_id})
                if test_result:
                    break
        
        if not test_result:
            return jsonify({
                'success': True,
                'needsRetake': False,
                'message': 'No test result found'
            }), 200
        
        # Support both new (scorePercentage) and old (percentage) field names
        percentage = test_result.get('scorePercentage') or test_result.get('percentage', 0)
        needs_retake = percentage < 50  # User must score 50% or higher to pass
        
        # If user passed (>= 50%), no retake needed - button will be hidden
        if not needs_retake:
            return jsonify({
                'success': True,
                'needsRetake': False,
                'percentage': percentage,
                'message': 'Test passed'
            }), 200
        
        # If user failed (< 50%), retake is required - button will show until they pass
        
        # Check current test attempt number
        current_attempt = test_result.get('testAttempt', 1)
        next_test_number = current_attempt + 1
        
        # Check if a new test with the next test_number already exists in monthly_test collection
        monthly_test_collection = db["monthly_test"]
        test_exists = False
        current_test = None
        
        for cand in candidates:
            current_test = monthly_test_collection.find_one({
                'mobile': cand, 
                'month': {'$in': [month, str(month)]},
                'test_number': next_test_number
            })
            if current_test:
                test_exists = True
                break
        
        # If test with next_test_number exists, user can start the test (don't show retake button)
        if test_exists:
            return jsonify({
                'success': True,
                'needsRetake': False,  # Hide retake button since test is ready
                'testReady': True,
                'percentage': percentage,
                'testAttempt': next_test_number,
                'message': f'Test {next_test_number} is ready to start'
            }), 200
        
        # Check if retake was triggered within last 24 hours
        can_retake = True
        hours_remaining = 0
        
        # Look for any test document for this month (regardless of test_number)
        if not current_test:
            for cand in candidates:
                current_test = monthly_test_collection.find_one({'mobile': cand, 'month': {'$in': [month, str(month)]}})
                if current_test:
                    break
        
        if current_test and current_test.get('retake_triggered_at'):
            triggered_at = current_test.get('retake_triggered_at')
            if isinstance(triggered_at, str):
                from datetime import datetime
                triggered_dt = datetime.fromisoformat(triggered_at)
                elapsed = datetime.now() - triggered_dt
                hours_elapsed = elapsed.total_seconds() / 3600
                
                if hours_elapsed < 24:
                    can_retake = False
                    hours_remaining = 24 - hours_elapsed
        
        return jsonify({
            'success': True,
            'needsRetake': True,
            'percentage': percentage,
            'canRetake': can_retake,
            'hoursRemaining': hours_remaining,
            'testAttempt': current_attempt,
            'nextTestNumber': next_test_number,
            'message': f'Score {percentage}% is below passing threshold of 50%. Retake required.'
        }), 200
        
    except Exception as e:
        print(f"❌ Error in monthly-test-retake-status: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/trigger-monthly-retake', methods=['POST'])
def trigger_monthly_retake():
    """
    Trigger regeneration of a monthly test via n8n webhook
    
    Request body:
    {
        "mobile": "+91 9346333208",
        "month": 1
    }
    """
    try:
        data = request.get_json()
        mobile = data.get('mobile')
        month = data.get('month', 1)
        
        if not mobile:
            return jsonify({
                'success': False,
                'error': 'Mobile number is required'
            }), 400
        
        mobile = mobile.strip()
        
        # Connect to MongoDB
        mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI")
        if not mongo_uri:
            return jsonify({
                'success': False,
                'error': 'Database connection not configured'
            }), 500
            
        client = MongoClient(mongo_uri)
        db = client[os.getenv("MONGODB_DB", "Placement_Ai")]
        monthly_test_collection = db["monthly_test"]
        result_collection = db["monthly_test_result"]
        
        # Check current test attempts - try new format first (mobile as _id)
        existing_result = result_collection.find_one({'_id': mobile, 'month': month})
        
        # Fallback to old format
        if not existing_result:
            result_id = f"{mobile}_month_{month}"
            existing_result = result_collection.find_one({'_id': result_id})
        
        current_attempt = 0
        if existing_result:
            current_attempt = existing_result.get('testAttempt', 0)
        
        # Calculate next test number
        next_test_number = current_attempt + 1
        
        print(f"\n{'='*60}")
        print(f"🔄 MONTHLY TEST RETAKE TRIGGERED")
        print(f"{'='*60}")
        print(f"Mobile: {mobile}")
        print(f"Month: {month}")
        print(f"Current Attempt: {current_attempt}")
        print(f"Next Test Number: {next_test_number}")
        print(f"{'='*60}\n")
        
        # Validate user hasn't exceeded maximum attempts
        if current_attempt >= 3:
            return jsonify({
                'success': False,
                'error': 'Maximum attempts (3) reached for this monthly test. You cannot retake anymore.',
                'attempts_taken': current_attempt
            }), 400
        
        # Validate the user has actually failed (score < 50)
        if existing_result:
            # Support both new (scorePercentage) and old (percentage) field names
            percentage = existing_result.get('scorePercentage') or existing_result.get('percentage', 0)
            if percentage >= 50:
                return jsonify({
                    'success': False,
                    'error': 'You have already passed this test (score >= 50%). Retake is only available for failed tests.',
                    'percentage': percentage
                }), 400
        
        print(f"📊 Current attempt: {current_attempt}, Next test number: {next_test_number}")
        
        # Mark the retake trigger timestamp
        from datetime import datetime
        monthly_test_collection.update_one(
            {'mobile': mobile, 'month': {'$in': [month, str(month)]}},
            {'$set': {
                'retake_triggered_at': datetime.now().isoformat(),
                'status': 'regenerating',  # Mark as being regenerated
                'next_test_number': next_test_number
            }},
            upsert=False
        )
        
        print(f"📝 Marked Month {month} test as 'regenerating' for {mobile}")
        
        # Trigger n8n webhook to regenerate the test
        # N8N will overwrite the existing test in monthly_test collection
        # After 24 hours, the new test will be ready for the user
        # User can then click "Start Monthly Test" to take the new test
        n8n_webhook = os.getenv('N8N_MONTHLY_TEST_WEBHOOK')
        
        if not n8n_webhook:
            return jsonify({
                'success': False,
                'error': 'N8N webhook not configured'
            }), 500
        
        import requests
        webhook_payload = {
            'mobile': mobile,
            'month': month,
            'retake': True,
            'test_number': next_test_number
        }
        
        print(f"\n{'='*60}")
        print(f"🔔 TRIGGERING MONTHLY TEST WEBHOOK (RETAKE)")
        print(f"{'='*60}")
        print(f"Mobile: {mobile}")
        print(f"Month: {month}")
        print(f"Test Number: {next_test_number}")
        print(f"Retake: True")
        print(f"{'='*60}\n")
        
        response = requests.post(
            n8n_webhook,
            json=webhook_payload,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        
        if response.status_code == 200:
            print(f"✅ Retake webhook triggered successfully")
            print(f"📝 N8N will regenerate the test and update monthly_test collection")
            print(f"⏰ After 24 hours, user can click 'Start Monthly Test' to take the new test")
            return jsonify({
                'success': True,
                'message': 'Monthly test retake triggered successfully. Test will be ready in 24 hours.',
                'info': 'After the countdown ends, click "Start Monthly Test" button to take your retake test.'
            }), 200
        else:
            print(f"⚠️ Webhook responded with status {response.status_code}")
            return jsonify({
                'success': False,
                'error': f'Webhook returned status {response.status_code}'
            }), 500
        
    except Exception as e:
        print(f"❌ Error in trigger-monthly-retake: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/monthly-test-status/<mobile>/<int:month>', methods=['GET'])
def get_monthly_test_status(mobile, month):
    """
    Check the status of a monthly test for a user
    Returns:
    - test_generated: bool (whether test exists in monthly_test collection)
    - test_generated_at: timestamp (when test was generated)
    - test_completed: bool (whether result exists in monthly_test_result collection)
    - can_start_test: bool (whether 5-minute timer has passed)
    - timer_remaining: int (seconds remaining if timer active)
    """
    try:
        if not mobile:
            return jsonify({
                'success': False,
                'error': 'Mobile number is required'
            }), 400
        
        mobile = mobile.strip()
        
        # Connect to MongoDB
        mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI")
        if not mongo_uri:
            return jsonify({
                'success': False,
                'error': 'Database connection not configured'
            }), 500
            
        client = MongoClient(mongo_uri)
        db = client[os.getenv("MONGODB_DB", "Placement_Ai")]
        monthly_test_collection = db["monthly_test"]
        result_collection = db["monthly_test_result"]
        
        # Normalize mobile number formats to search
        normalized_mobile = mobile.replace("+", "").replace(" ", "").replace("-", "")
        mobile_10 = normalized_mobile[-10:] if len(normalized_mobile) >= 10 else normalized_mobile
        
        search_ids = [mobile, normalized_mobile, mobile_10]
        if len(normalized_mobile) == 10:
            search_ids.extend([
                f"91{normalized_mobile}",
                f"+91{normalized_mobile}",
                f"+91 {mobile_10}"
            ])
        
        # Check if test exists
        # NOTE: N8N creates documents with _id = mobile (not mobile_month_X format)
        # So we search by mobile field + month field instead of _id pattern
        test_doc = None
        test_id = None
        
        # Try to find by mobile + month fields (this is how N8N stores it)
        for search_id in search_ids:
            test_doc = monthly_test_collection.find_one({"mobile": search_id, "month": {"$in": [month, str(month)]}})
            if test_doc:
                test_id = str(test_doc.get('_id'))
                print(f"[monthly-test-status] Found test with mobile: {search_id}, _id: {test_id}")
                break
        
        # Fallback: Try old format with _id = mobile_month_X (for backward compatibility)
        if not test_doc:
            for search_id in search_ids:
                test_id_variant = f"{search_id}_month_{month}"
                test_doc = monthly_test_collection.find_one({'_id': test_id_variant})
                if test_doc:
                    test_id = test_id_variant
                    print(f"[monthly-test-status] Found test with _id pattern: {test_id}")
                    break
        
        test_generated = test_doc is not None
        
        # Get timestamp - try multiple fields
        test_generated_at = None
        if test_doc:
            test_generated_at = (
                test_doc.get('createdAt') or 
                test_doc.get('timestamp') or 
                test_doc.get('created_at') or
                test_doc.get('_id').generation_time if hasattr(test_doc.get('_id', ''), 'generation_time') else None
            )
        
        print(f"[monthly-test-status] Test doc found: {test_generated}")
        print(f"[monthly-test-status] Test ID: {test_id if test_doc else 'None'}")
        print(f"[monthly-test-status] Test generated_at: {test_generated_at}")
        if test_doc:
            print(f"[monthly-test-status] Test doc keys: {list(test_doc.keys())}")
        
        # Check if test is completed - try new format first (mobile as _id)
        result_doc = None
        for search_id in search_ids:
            result_doc = result_collection.find_one({'_id': search_id, 'month': month})
            if result_doc:
                break
        
        # Fallback to old format for backward compatibility
        if not result_doc:
            result_id = f"{mobile}_month_{month}"
            result_doc = result_collection.find_one({'_id': result_id})
            
            if not result_doc:
                for search_id in search_ids:
                    result_id_variant = f"{search_id}_month_{month}"
                    result_doc = result_collection.find_one({'_id': result_id_variant})
                    if result_doc:
                        break
        
        test_completed = result_doc is not None
        
        print(f"[monthly-test-status] Test completed: {test_completed}")
        
        # Calculate timer status (5 minutes = 300 seconds)
        can_start_test = False
        timer_remaining = 0
        
        if test_generated:
            if test_generated_at:
                # Parse the timestamp
                if isinstance(test_generated_at, str):
                    try:
                        # Try parsing ISO format with dateutil if available
                        try:
                            from dateutil import parser as date_parser
                            generated_time = date_parser.parse(test_generated_at)
                        except ImportError:
                            # Fallback to manual parsing if dateutil not available
                            try:
                                # Try ISO format: 2024-01-15T10:30:00.000Z
                                generated_time = datetime.fromisoformat(test_generated_at.replace('Z', '+00:00'))
                            except:
                                # If all parsing fails, use current time (will show timer=300)
                                print(f"[monthly-test-status] Could not parse timestamp: {test_generated_at}, using current time")
                                generated_time = datetime.utcnow()
                    except Exception as e:
                        print(f"[monthly-test-status] Error parsing timestamp: {e}, using current time")
                        generated_time = datetime.utcnow()
                elif isinstance(test_generated_at, datetime):
                    generated_time = test_generated_at
                else:
                    print(f"[monthly-test-status] Unknown timestamp type: {type(test_generated_at)}, using current time")
                    generated_time = datetime.utcnow()
                
                # Make sure generated_time is naive (no timezone) for comparison with utcnow()
                if generated_time.tzinfo is not None:
                    # Convert timezone-aware datetime to UTC then make naive
                    # Using timedelta to adjust for UTC offset
                    try:
                        utc_offset = generated_time.utcoffset()
                        if utc_offset is not None:
                            generated_time = (generated_time - utc_offset).replace(tzinfo=None)
                        else:
                            generated_time = generated_time.replace(tzinfo=None)
                    except Exception as tz_err:
                        print(f"[monthly-test-status] Timezone conversion error: {tz_err}, stripping timezone")
                        generated_time = generated_time.replace(tzinfo=None)
                
                # Calculate elapsed time
                elapsed_seconds = (datetime.utcnow() - generated_time).total_seconds()
                print(f"[monthly-test-status] Elapsed seconds: {elapsed_seconds}")
                
                if elapsed_seconds >= 300:  # 5 minutes = 300 seconds
                    can_start_test = True
                    timer_remaining = 0
                else:
                    can_start_test = False
                    timer_remaining = int(300 - elapsed_seconds)
            else:
                # No timestamp found - test was generated by N8N without timestamp
                # Allow starting immediately since we can't determine when it was created
                print(f"[monthly-test-status] No timestamp found, allowing test to start immediately")
                can_start_test = True
                timer_remaining = 0
        
        print(f"[monthly-test-status] can_start_test: {can_start_test}, timer_remaining: {timer_remaining}")
        
        client.close()
        
        return jsonify({
            'success': True,
            'data': {
                'mobile': mobile,
                'month': month,
                'test_generated': test_generated,
                'test_generated_at': test_generated_at,
                'test_completed': test_completed,
                'can_start_test': can_start_test,
                'timer_remaining': timer_remaining
            }
        }), 200
        
    except Exception as e:
        print(f"❌ Error in get-monthly-test-status: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/db-health', methods=['GET'])
@handle_errors
def db_health_check():
    """Ping MongoDB to verify connectivity and auth."""
    try:
        db = get_db()
        # Ping command available in MongoDB 4.2+
        res = db.command('ping')
        return {
            'database': 'connected',
            'ping_result': res
        }
    except Exception as e:
        raise DatabaseError(
            message="Database connection failed",
            details={'error': str(e)}
        )

@app.route('/api/parse-resume', methods=['POST'])
@handle_errors
def parse_resume_endpoint():
    """Accept multipart file 'resume', parse via utils.parse_resume, and return JSON."""
    if 'resume' not in request.files:
        raise ValidationError(
            message="No file uploaded",
            details={'expected_field': 'resume'}
        )

    file = request.files['resume']
    if not file or file.filename == '':
        raise ValidationError(
            message="No file selected",
            details={'expected_field': 'resume'}
        )

    # Validate file type
    suffix = (os.path.splitext(file.filename)[1] or '').lower()
    allowed_types = {'.pdf', '.docx', '.doc', '.txt', '.text'}
    if suffix not in allowed_types:
        raise ValidationError(
            message=f"Unsupported file type: {suffix}",
            details={
                'allowed_types': list(allowed_types),
                'received_type': suffix
            }
        )

    # Save to a temporary file to support different formats (pdf/docx/txt)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            file.save(tmp.name)
            temp_path = tmp.name

        result = parse_resume_file(temp_path)
        if not isinstance(result, dict):
            raise ModelError("Resume parsing failed to return valid data")

        # Return dict directly - @handle_errors decorator will wrap it
        return result
    except Exception as e:
        log_error(e, request_obj=request)
        if isinstance(e, (ValidationError, ModelError)):
            raise
        raise ModelError(
            message="Resume parsing failed",
            details={'error': str(e)}
        )
    finally:
        # Clean up temporary file
        try:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception as cleanup_error:
            log_error(cleanup_error, severity='WARNING')


@app.errorhandler(413)
def too_large(_e):
    return jsonify({'success': False, 'error': 'File too large (max 10MB)'}), 413


@app.route('/api/domains', methods=['GET'])
def get_domains():
    """Get all available domains and their data"""
    try:
        domains = get_domain_data()
        return jsonify({
            'success': True,
            'data': domains
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/predict', methods=['POST'])
@handle_errors
def predict_placement():
    """Predict placement probability based on student data using ML model"""
    request_id = generate_request_id()
    data = request.get_json()
    
    if not data:
        raise ValidationError("No data provided in request body")
    
    # Validate input data
    is_valid, validation_errors = validate_prediction_input(data)
    if not is_valid:
        raise ValidationError(
            message="Input validation failed",
            details={'validation_errors': validation_errors}
        )
    
    # Sanitize text inputs
    if 'achievements' in data and data['achievements']:
        data['achievements'] = sanitize_text_input(data['achievements'])
    
    if 'certifications' in data and data['certifications']:
        data['certifications'] = sanitize_text_input(data['certifications'])
    
    # Deduplicate skills
    if 'selectedSkills' in data and isinstance(data['selectedSkills'], list):
        data['selectedSkills'] = deduplicate_skills(data['selectedSkills'])
    
    if 'skills' in data and isinstance(data['skills'], list):
        data['skills'] = deduplicate_skills(data['skills'])
    
    # Make ML prediction
    try:
        prediction_result = predictor.predict(data)
        if not prediction_result:
            raise ModelError("ML model failed to generate prediction")
    except Exception as e:
        log_error(e, request_obj=request, request_id=request_id)
        raise ModelError(
            message="Prediction generation failed",
            details={'error': str(e)}
        )

    # Persist AFTER prediction - ALWAYS save to MongoDB
    db_info = None
    is_personal_resume = data.get('isPersonalResume', False)
    
    print(f"[PREDICT] 🔍 isPersonalResume flag: {is_personal_resume}")
    print(f"[PREDICT] 📝 User data - Name: {data.get('name')}, Email: {data.get('email')}, Mobile: {data.get('mobile')}")
    print(f"[PREDICT] ✅ Saving to MongoDB (saving all predictions)...")
    
    try:
        db_info = save_candidate_prediction(data, prediction_result)
        db_info['saved'] = True
        db_info['isPersonalResume'] = is_personal_resume
        print(f"[PREDICT] ✅ Successfully saved to MongoDB! Doc ID: {db_info.get('_id')}")
    except Exception as se:
        # Log but don't fail the request if database save fails
        print(f"[PREDICT] ❌ Failed to save to MongoDB: {str(se)}")
        log_error(se, request_obj=request, request_id=request_id, severity='WARNING')
        db_info = {'saved': False, 'error': str(se)}

    # Send data to n8n webhook for student analysis processing - ASYNC (non-blocking)
    print(f"[PREDICT] 📤 Triggering N8N webhook asynchronously (non-blocking)...")
    def send_webhook_async():
        try:
            send_prediction_to_n8n(data, prediction_result, "prediction_completed")
            print(f"[PREDICT] ✅ N8N webhook triggered successfully (async)")
        except Exception as ne:
            print(f"[PREDICT] ⚠️ N8N webhook failed (async): {str(ne)}")
    
    # Run webhook in background thread - don't wait for response
    webhook_thread = threading.Thread(target=send_webhook_async, daemon=True)
    webhook_thread.start()

    # Return prediction result immediately - decorator will wrap it
    return prediction_result

@app.route('/api/predict/ml', methods=['POST'])
@handle_errors
def predict_placement_ml():
    """Dedicated endpoint for ML-based placement predictions"""
    request_id = generate_request_id()
    data = request.get_json()
    
    if not data:
        raise ValidationError("No data provided in request body")
    
    # Validate required fields for ML prediction
    required_fields = ['tenthPercentage', 'twelfthPercentage', 'collegeCGPA']
    validate_required_fields(data, required_fields)
    
    # Validate numeric ranges
    validate_numeric_range(data['tenthPercentage'], '10th percentage', 0, 100)
    validate_numeric_range(data['twelfthPercentage'], '12th percentage', 0, 100)
    validate_numeric_range(data['collegeCGPA'], 'College CGPA', 0, 10)
    
    # Make ML prediction
    try:
        prediction_result = predictor.predict(data)
        if not prediction_result:
            return jsonify({
                'success': False,
                'error': 'Failed to generate prediction'
            }), 500

        # Save to resumes collection - ALWAYS save all predictions
        db_info = None
        is_personal_resume = data.get('isPersonalResume', False)
        
        print(f"[PREDICT/ML] 🔍 isPersonalResume flag: {is_personal_resume}")
        print(f"[PREDICT/ML] 📝 User data - Name: {data.get('name')}, Email: {data.get('email')}, Mobile: {data.get('mobile')}")
        print(f"[PREDICT/ML] ✅ Saving to MongoDB (saving all predictions)...")
        
        try:
            # Save to resumes collection
            db_info = save_candidate_prediction(data, prediction_result)
            db_info['saved'] = True
            db_info['isPersonalResume'] = is_personal_resume
            print(f"[PREDICT/ML] ✅ Successfully saved to MongoDB! Doc ID: {db_info.get('_id')}")
        except Exception as e:
            print(f"[PREDICT/ML] ❌ Failed to save to MongoDB: {str(e)}")
            print(f"Error saving prediction data: {str(e)}")
            db_info = {'saved': False, 'error': str(e)}

        # Send data to n8n webhook for student analysis processing - ASYNC (non-blocking)
        print(f"[PREDICT/ML] 📤 Triggering N8N webhook asynchronously (non-blocking)...")
        def send_webhook_async():
            try:
                send_prediction_to_n8n(data, prediction_result, "ml_prediction_completed")
                print(f"[PREDICT/ML] ✅ N8N webhook triggered successfully (async)")
            except Exception as ne:
                print(f"[PREDICT/ML] ⚠️ N8N webhook failed (async): {str(ne)}")
        
        # Run webhook in background thread - don't wait for response
        webhook_thread = threading.Thread(target=send_webhook_async, daemon=True)
        webhook_thread.start()
        
        return jsonify({
            'success': True,
            'data': prediction_result,
            'db': db_info,
            'message': 'ML prediction completed and saved to MongoDB.'
        })
        
    except Exception as e:
        log_error(e, request_obj=request, request_id=request_id)
        raise ModelError(
            message="Prediction generation failed",
            details={'error': str(e)}
        )

@app.route('/api/check-resume', methods=['POST'])
def check_resume_exists():
    """Check if a resume exists for the given mobile number"""
    try:
        data = request.get_json()
        if not data or 'mobile' not in data:
            return jsonify({
                'success': False,
                'error': 'Mobile number is required'
            }), 400
        
        mobile = data['mobile'].strip()
        if not mobile:
            return jsonify({
                'success': False,
                'error': 'Mobile number cannot be empty'
            }), 400
        
        # Check both collections: Resume (main) and resume_temp (temporary)
        db = get_db()
        
        # Generate different phone number formats to search
        # Remove any non-digit characters for clean version
        clean_mobile = ''.join(filter(str.isdigit, mobile))
        
        # Get the last 10 digits (actual mobile number)
        last_10_digits = clean_mobile[-10:] if len(clean_mobile) >= 10 else clean_mobile
        
        # Create different search patterns including various formats with spaces
        search_patterns = [
            mobile,  # Original format as entered by user
            clean_mobile,  # Just digits
            last_10_digits,  # Last 10 digits only
            
            # With +91 (no space)
            f'+91{last_10_digits}',
            f'+91{clean_mobile}' if not clean_mobile.startswith('91') else f'+{clean_mobile}',
            
            # With +91 (with space) - This matches your database format!
            f'+91 {last_10_digits}',
            f'+91 {clean_mobile}' if not clean_mobile.startswith('91') else f'+ {clean_mobile}',
            
            # With 91 (no space)
            f'91{last_10_digits}',
            f'91{clean_mobile}' if not clean_mobile.startswith('91') else clean_mobile,
            
            # With 91 (with space)
            f'91 {last_10_digits}',
        ]
        
        # Remove duplicates while preserving order
        unique_patterns = []
        for pattern in search_patterns:
            if pattern not in unique_patterns:
                unique_patterns.append(pattern)
        
        # Search in main Resume collection with all patterns
        main_resume = None
        for pattern in unique_patterns:
            main_resume = db.Resume.find_one({'$or': [{'mobile': pattern}, {'phone': pattern}]})
            if main_resume:
                break
        
        # Search in temp resume collection with all patterns
        temp_resume = None
        if not main_resume:
            for pattern in unique_patterns:
                temp_resume = db.resume_temp.find_one({'$or': [{'mobile': pattern}, {'phone': pattern}]})
                if temp_resume:
                    break
        
        resume_found = main_resume or temp_resume
        collection_type = 'main' if main_resume else ('temp' if temp_resume else None)
        
        return jsonify({
            'success': True,
            'exists': bool(resume_found),
            'mobile': mobile,
            'collection': collection_type,
            'message': f'Resume {"found" if resume_found else "not found"} for mobile number {mobile}'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/link-resume-profile', methods=['POST'])
def link_resume_profile():
    """Link user profile with existing resume in database"""
    try:
        data = request.get_json()
        user_data = data.get('userData', {})
        mobile = data.get('mobile') or user_data.get('mobile') or user_data.get('phone')
        
        if not mobile:
            return jsonify({
                'success': False,
                'error': 'Mobile number is required'
            }), 400
        
        if not user_data:
            return jsonify({
                'success': False,
                'error': 'User data is required'
            }), 400
        
        db = get_db()
        
        # Generate different phone number formats to search
        # Remove any non-digit characters for clean version
        clean_mobile = ''.join(filter(str.isdigit, mobile))
        
        # Get the last 10 digits (actual mobile number)
        last_10_digits = clean_mobile[-10:] if len(clean_mobile) >= 10 else clean_mobile
        
        # Create different search patterns including various formats with spaces
        search_patterns = [
            mobile,  # Original format as entered by user
            clean_mobile,  # Just digits
            last_10_digits,  # Last 10 digits only
            
            # With +91 (no space)
            f'+91{last_10_digits}',
            f'+91{clean_mobile}' if not clean_mobile.startswith('91') else f'+{clean_mobile}',
            
            # With +91 (with space) - This matches your database format!
            f'+91 {last_10_digits}',
            f'+91 {clean_mobile}' if not clean_mobile.startswith('91') else f'+ {clean_mobile}',
            
            # With 91 (no space)
            f'91{last_10_digits}',
            f'91{clean_mobile}' if not clean_mobile.startswith('91') else clean_mobile,
            
            # With 91 (with space)
            f'91 {last_10_digits}',
        ]
        
        # Remove duplicates while preserving order
        unique_patterns = []
        for pattern in search_patterns:
            if pattern not in unique_patterns:
                unique_patterns.append(pattern)
        
        # Search in main Resume collection with all patterns
        main_resume = None
        for pattern in unique_patterns:
            main_resume = db.Resume.find_one({'$or': [{'mobile': pattern}, {'phone': pattern}]})
            if main_resume:
                break
        
        # Search in temp resume collection with all patterns
        temp_resume = None
        if not main_resume:
            for pattern in unique_patterns:
                temp_resume = db.resume_temp.find_one({'$or': [{'mobile': pattern}, {'phone': pattern}]})
                if temp_resume:
                    break
        
        if not main_resume and not temp_resume:
            return jsonify({
                'success': False,
                'error': f'No resume found for mobile number {mobile}'
            }), 404
        
        # Use main resume if available, otherwise temp resume
        existing_resume = main_resume or temp_resume
        collection_name = 'Resume' if main_resume else 'resume_temp'
        collection = db.Resume if main_resume else db.resume_temp
        
        # Update the resume document with user profile information
        update_data = {
            'userProfile': {
                'name': user_data.get('name', ''),
                'email': user_data.get('email', ''),
                'mobile': mobile,
                'linkedAt': datetime.now().isoformat(),
                'profileComplete': True
            },
            'lastUpdated': datetime.now().isoformat()
        }
        
        # If email is provided, also update the email field in the resume
        if user_data.get('email'):
            update_data['email'] = user_data.get('email')
        
        # Update the resume document
        result = collection.update_one(
            {'_id': existing_resume['_id']},
            {'$set': update_data}
        )
        
        if result.modified_count > 0:
            # Get the updated resume document
            updated_resume = collection.find_one({'_id': existing_resume['_id']})
            
            return jsonify({
                'success': True,
                'message': 'Resume successfully linked to user profile',
                'resumeId': str(existing_resume['_id']),
                'collection': collection_name,
                'userProfile': update_data['userProfile'],
                'resumeData': {
                    'name': updated_resume.get('name', ''),
                    'email': updated_resume.get('email', ''),
                    'mobile': updated_resume.get('mobile') or updated_resume.get('phone', ''),
                    'skills': updated_resume.get('skills', []),
                    'projects': updated_resume.get('projects', []),
                    'experience': updated_resume.get('experience', []) or updated_resume.get('internships', []),
                    'education': updated_resume.get('education', []),
                    'certifications': updated_resume.get('certifications', []),
                    'university': updated_resume.get('university', ''),
                    'degree': updated_resume.get('degree', ''),
                    'cgpa': updated_resume.get('cgpa', ''),
                    'tenthPercentage': updated_resume.get('tenthPercentage', ''),
                    'twelfthPercentage': updated_resume.get('twelfthPercentage', ''),
                    'jobSelection': updated_resume.get('jobSelection', {})
                }
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to update resume with profile information'
            }), 500
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/resume-choice', methods=['POST'])
def handle_resume_choice():
    """Handle user choice for resume linking (link_resume or upload_new)"""
    try:
        data = request.get_json()
        mobile = data.get('mobile')
        choice = data.get('choice')
        
        if not mobile:
            return jsonify({
                'success': False,
                'error': 'Mobile number is required'
            }), 400
        
        if not choice or choice not in ['link_resume', 'upload_new']:
            return jsonify({
                'success': False,
                'error': 'Invalid choice. Must be "link_resume" or "upload_new"'
            }), 400
        
        # Log the choice for tracking
        print(f"Resume choice received: {choice} for mobile: {mobile}")
        
        if choice == 'link_resume':
            # User wants to link existing resume
            return jsonify({
                'success': True,
                'message': 'Resume will be linked to your profile during prediction',
                'action': 'link_resume',
                'mobile': mobile,
                'nextStep': 'Continue to prediction form'
            })
        else:
            # User wants to upload new resume
            return jsonify({
                'success': True,
                'message': 'You can upload a new resume in the prediction form',
                'action': 'upload_new',
                'mobile': mobile,
                'nextStep': 'Upload new resume in prediction form'
            })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/update-resume-skills', methods=['POST'])
def update_resume_skills():
    """Update resume with selected job-related skills in database"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        mobile = data.get('mobile')
        selected_skills = data.get('selectedSkills', [])
        unselected_skills = data.get('unselectedSkills', [])
        job_domain = data.get('jobDomain', '')
        job_role = data.get('jobRole', '')
        
        print(f"\n{'='*80}")
        print(f"📥 RECEIVED UPDATE REQUEST")
        print(f"{'='*80}")
        print(f"Mobile: {mobile}")
        print(f"Selected Skills ({len(selected_skills)}): {selected_skills}")
        print(f"Unselected Skills ({len(unselected_skills)}): {unselected_skills}")
        print(f"Job Domain: {job_domain}")
        print(f"Job Role: {job_role}")
        print(f"{'='*80}\n")
        
        if not mobile:
            return jsonify({
                'success': False,
                'error': 'Mobile number is required'
            }), 400
        
        if not selected_skills:
            return jsonify({
                'success': False,
                'error': 'Selected skills are required'
            }), 400
        
        db = get_db()
        
        # Generate search patterns for mobile number (same logic as other endpoints)
        clean_mobile = ''.join(filter(str.isdigit, mobile))
        last_10_digits = clean_mobile[-10:] if len(clean_mobile) >= 10 else clean_mobile
        
        search_patterns = [
            mobile,
            clean_mobile,
            last_10_digits,
            f'+91{last_10_digits}',
            f'+91 {last_10_digits}',
            f'91{last_10_digits}',
            f'91 {last_10_digits}',
        ]
        
        # Remove duplicates
        unique_patterns = list(dict.fromkeys(search_patterns))
        
        # Search in Resume collection first
        resume_doc = None
        collection = None
        for pattern in unique_patterns:
            resume_doc = db.Resume.find_one({'$or': [{'mobile': pattern}, {'phone': pattern}]})
            if resume_doc:
                collection = db.Resume
                break
        
        # Search in resume_temp collection if not found in main collection
        if not resume_doc:
            for pattern in unique_patterns:
                resume_doc = db.resume_temp.find_one({'$or': [{'mobile': pattern}, {'phone': pattern}]})
                if resume_doc:
                    collection = db.resume_temp
                    break
        
        if not resume_doc:
            return jsonify({
                'success': False,
                'error': f'No resume found for mobile number {mobile}'
            }), 404
        
        # Prepare update data - integrate job role skills directly in resume
        update_data = {
            'jobSelection': {
                'selectedSkills': selected_skills,
                'unselectedSkills': unselected_skills,
                'jobDomain': job_domain,
                'jobRole': job_role,
                'updatedAt': datetime.now().isoformat(),
                'skillsCount': len(selected_skills),
                'unselectedSkillsCount': len(unselected_skills),
                'description': f'Skills you possess for {job_role} role in {job_domain.replace("_", " ").title()}',
                'isActive': True
            },
            'jobRoleSkills': {
                'current': selected_skills,
                'toLearn': unselected_skills,
                'domain': job_domain,
                'role': job_role,
                'lastUpdated': datetime.now().isoformat()
            },
            'lastUpdated': datetime.now().isoformat()
        }
        
        print(f"\n{'='*80}")
        print(f"💾 SAVING TO DATABASE")
        print(f"{'='*80}")
        print(f"Document ID: {resume_doc['_id']}")
        print(f"Collection: {collection.name}")
        print(f"jobSelection.selectedSkills: {update_data['jobSelection']['selectedSkills']}")
        print(f"jobSelection.unselectedSkills: {update_data['jobSelection']['unselectedSkills']}")
        print(f"jobRoleSkills.current: {update_data['jobRoleSkills']['current']}")
        print(f"jobRoleSkills.toLearn: {update_data['jobRoleSkills']['toLearn']}")
        print(f"{'='*80}\n")
        
        # Update the resume document
        result = collection.update_one(
            {'_id': resume_doc['_id']},
            {'$set': update_data}
        )
        
        print(f"✅ Database update result: modified_count = {result.modified_count}\n")
        
        if result.modified_count > 0:
            # Trigger external webhook to notify skill selection
            webhook_url = os.getenv('SKILLS_SELECTION_WEBHOOK') or 'https://n8n-1-2ldl.onrender.com/webhook-test/webhook/resume-test'
            webhook_info = None
            try:
                import requests
                payload = {
                    'mobile': mobile,
                    'selectedSkills': selected_skills,
                    'unselectedSkills': unselected_skills,
                    'jobDomain': job_domain,
                    'jobRole': job_role,
                    'timestamp': datetime.now().isoformat(),
                    'source': 'placement-ai'
                }
                resp = requests.post(webhook_url, json=payload, timeout=10)
                webhook_info = {'status_code': resp.status_code, 'text': resp.text[:1000]}
            except Exception as e:
                webhook_info = {'error': str(e)}

            return jsonify({
                'success': True,
                'message': f'Successfully updated resume with {len(selected_skills)} selected skills and {len(unselected_skills)} skills to develop',
                'data': {
                    'mobile': mobile,
                    'skillsUpdated': len(selected_skills),
                    'selectedSkills': selected_skills,
                    'unselectedSkills': unselected_skills,
                    'unselectedSkillsCount': len(unselected_skills),
                    'jobDomain': job_domain,
                    'jobRole': job_role,
                    'collection': 'Resume' if collection == db.Resume else 'resume_temp'
                },
                'webhook': webhook_info
            })
        else:
            return jsonify({
                'success': False,
                'error': 'No changes were made to the resume'
            }), 400
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/suggestions', methods=['POST'])
def suggestions_endpoint():
    """Generate structured resume improvement suggestions via Perplexity."""
    try:
        payload = request.get_json() or {}
        result = generate_suggestions(payload)
        code = 200 if result.get('success') else 502
        return jsonify(result), code
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/students', methods=['GET'])
def get_students():
    """Get all student applications (for admin dashboard)"""
    try:
        # In a real application, this would fetch from a database
        # For now, we'll return mock data
        students = [
            {
                'id': 1,
                'name': 'John Doe',
                'email': 'john.doe@example.com',
                'domain': 'Computer Science',
                'category': 'Data Science',
                'skills': ['Python', 'React', 'SQL'],
                'placementScore': 87,
                'date': '2025-05-15'
            },
            {
                'id': 2,
                'name': 'Jane Smith',
                'email': 'jane.smith@example.com',
                'domain': 'Computer Science',
                'category': 'Web Development',
                'skills': ['Java', 'Spring Boot', 'MySQL'],
                'placementScore': 92,
                'date': '2025-05-14'
            }
        ]
        
        return jsonify({
            'success': True,
            'data': students
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/statistics', methods=['GET'])
def get_statistics():
    """Get placement statistics for dashboard"""
    try:
        stats = {
            'totalStudents': 1500,
            'placedStudents': 1230,
            'averageSalary': '7.2 LPA',
            'highestSalary': '32 LPA',
            'topRecruiters': ['Microsoft', 'Amazon', 'TCS', 'Infosys', 'Wipro'],
            'domainStats': [
                {'name': 'Computer Science', 'openings2024': 26000},
                {'name': 'Mechanical', 'openings2024': 9500},
                {'name': 'Electrical', 'openings2024': 9000},
                {'name': 'Electronics', 'openings2024': 7500}
            ]
        }
        
        return jsonify({
            'success': True,
            'data': stats
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/ats-score', methods=['POST'])
def calculate_ats_score_endpoint():
    """Calculate ATS score for resume data"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No resume data provided'
            }), 400
        
        # Extract job description if provided (optional)
        job_description = data.pop('job_description', '') if 'job_description' in data else ''
        
        # Validate and sanitize input data
        # Ensure list fields are actually lists
        list_fields = ['skills', 'projects', 'internships', 'achievements']
        for field in list_fields:
            if field in data:
                if isinstance(data[field], str):
                    # Convert comma/newline separated strings to lists
                    data[field] = [x.strip() for x in data[field].replace('\n', ',').split(',') if x.strip()]
                elif not isinstance(data[field], list):
                    data[field] = []
        
        # Validate numeric fields
        numeric_fields = ['cgpa', 'tenthPercentage', 'twelfthPercentage', 'bachelorCGPA', 'mastersCGPA']
        for field in numeric_fields:
            if field in data and data[field] is not None:
                try:
                    data[field] = float(data[field])
                except (ValueError, TypeError):
                    data[field] = 0.0
        
        # Add job description to data for ATS analysis
        if job_description:
            data['job_description'] = job_description
        
        # Calculate ATS score
        ats_result = calculate_ats_score(data)
        
        return jsonify({
            'success': True,
            'data': ats_result
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/model-info', methods=['GET'])
def get_model_info():
    """Get information about the loaded ML model"""
    try:
        model_info = predictor.get_model_info()
        return jsonify({
            'success': True,
            'data': model_info
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/send-otp', methods=['POST'])
def send_otp():
    """Send OTP to user's email"""
    try:
        data = request.get_json()
        
        if not data or 'email' not in data:
            return jsonify({
                'success': False,
                'message': 'Email is required'
            }), 400
        
        email = data.get('email').strip().lower()
        user_name = data.get('firstName', 'User')
        
        # Basic email validation
        if '@' not in email or '.' not in email:
            return jsonify({
                'success': False,
                'message': 'Please enter a valid email address'
            }), 400
        
        # Send OTP
        result = active_otp_service.send_otp(email, user_name)
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error sending OTP: {str(e)}'
        }), 500

@app.route('/api/verify-otp', methods=['POST'])
def verify_otp():
    """Verify OTP entered by user"""
    try:
        data = request.get_json()
        
        if not data or 'email' not in data or 'otp' not in data:
            return jsonify({
                'success': False,
                'message': 'Email and OTP are required'
            }), 400
        
        email = data.get('email').strip().lower()
        otp = data.get('otp').strip()
        
        # Verify OTP
        result = active_otp_service.verify_otp(email, otp)
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error verifying OTP: {str(e)}'
        }), 500

@app.route('/api/save-registration', methods=['POST'])
def save_registration():
    """Save user registration data to MongoDB"""
    try:
        from utils.db import save_user_registration
        
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'message': 'Registration data is required'
            }), 400
        
        # Validate required fields
        required_fields = ['firstName', 'lastName', 'username', 'password', 'email']
        for field in required_fields:
            if not data.get(field):
                return jsonify({
                    'success': False,
                    'message': f'{field} is required'
                }), 400
        
        # Validate username format
        import re
        username = data.get('username', '').strip()
        if not re.match(r'^[a-zA-Z0-9_]+$', username):
            return jsonify({
                'success': False,
                'message': 'Username can only contain letters, numbers, and underscores'
            }), 400
        
        if len(username) < 3:
            return jsonify({
                'success': False,
                'message': 'Username must be at least 3 characters long'
            }), 400
        
        if len(username) > 20:
            return jsonify({
                'success': False,
                'message': 'Username must be less than 20 characters'
            }), 400
        
        # Validate password format
        password = data.get('password', '').strip()
        if len(password) < 8:
            return jsonify({
                'success': False,
                'message': 'Password must be at least 8 characters long'
            }), 400
        
        if not re.search(r'(?=.*[a-z])(?=.*[A-Z])(?=.*\d)', password):
            return jsonify({
                'success': False,
                'message': 'Password must contain at least one uppercase letter, one lowercase letter, and one number'
            }), 400
        
        # Check if username already exists (username is now the _id field)
        from utils.db import get_collection
        registration_col = get_collection("Registration")
        existing_username = registration_col.find_one({"_id": username})
        if existing_username:
            return jsonify({
                'success': False,
                'message': 'Username already exists. Please choose a different username.'
            }), 400
        
        # Save registration data
        result = save_user_registration(data)
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error saving registration: {str(e)}'
        }), 500

@app.route('/api/check-user', methods=['POST'])
def check_user():
    """Check if user exists in the database by email or username"""
    try:
        from utils.db import get_collection
        
        data = request.get_json()
        
        # Accept both 'email' and 'emailOrUsername' for backward compatibility
        email_or_username = data.get('emailOrUsername') or data.get('email', '')
        
        if not email_or_username:
            return jsonify({
                'success': False,
                'message': 'Email or Username is required'
            }), 400
        
        input_value = email_or_username.strip()
        
        # Check if user exists in Registration collection
        registration_col = get_collection("Registration")
        
        # Check if input looks like an email (contains @ symbol)
        if '@' in input_value:
            # Search by email
            user = registration_col.find_one({"email": input_value.lower()})
        else:
            # Search by username (which is stored as _id)
            user = registration_col.find_one({"_id": input_value})
        
        if user:
            return jsonify({
                'success': True,
                'exists': True,
                'message': 'User found',
                'user': {
                    'firstName': user.get('firstName', ''),
                    'lastName': user.get('lastName', ''),
                    'username': user.get('_id', ''),  # Username is now stored as _id
                    'email': user.get('email', ''),
                    'mobile': user.get('mobileNumber', ''),
                    'registrationDate': user.get('registrationDate')
                }
            })
        else:
            return jsonify({
                'success': True,
                'exists': False,
                'message': 'User not found'
            })
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error checking user: {str(e)}'
        }), 500

@app.route('/api/signin-password', methods=['POST'])
def signin_password():
    """Sign in user with email or username and password"""
    try:
        from utils.db import verify_user_password
        
        data = request.get_json()
        
        # Accept both 'email' and 'emailOrUsername' for backward compatibility
        email_or_username = data.get('emailOrUsername') or data.get('email', '')
        password = data.get('password', '')
        
        if not email_or_username or not password:
            return jsonify({
                'success': False,
                'message': 'Email/Username and password are required'
            }), 400
        
        # Verify user credentials
        result = verify_user_password(email_or_username, password)
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 401
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error during sign in: {str(e)}'
        }), 500

@app.route('/api/save-job-role-roadmap', methods=['POST'])
def save_job_role_roadmap():
    """
    Save job role skills to the roadmaps collection.
    
    Expected payload:
    {
        "mobile": "+91 9084117332",
        "jobDomain": "Data Science",
        "jobRole": "Data Analyst", 
        "selectedSkills": ["SQL", "Power BI", "Microsoft Excel"],
        "learningPath": {
            "recommendedSkills": ["Python", "Tableau"],
            "skillGaps": ["Machine Learning", "Statistics"],
            "courseSuggestions": ["Data Analysis with Python"],
            "timelineWeeks": 12
        }
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'message': 'No data provided'
            }), 400
        
        # Extract required fields
        mobile = data.get('mobile')
        job_domain = data.get('jobDomain')
        job_role = data.get('jobRole')
        selected_skills = data.get('selectedSkills', [])
        learning_path = data.get('learningPath')
        
        if not all([mobile, job_domain, job_role]):
            return jsonify({
                'success': False,
                'message': 'Mobile, jobDomain, and jobRole are required'
            }), 400
        
        if not selected_skills:
            return jsonify({
                'success': False,
                'message': 'At least one skill must be selected'
            }), 400
        
        # Roadmap functionality moved to resume integration
        return jsonify({
            'success': True,
            'message': 'Job role skills are now integrated directly in resume collection',
            'note': 'Use /api/update-resume-skills endpoint instead'
        })
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error saving job role roadmap: {str(e)}'
        }), 500


@app.route('/api/get-job-role-roadmap', methods=['POST'])
def get_job_role_roadmap():
    """
    Get job role skills roadmap from the roadmaps collection.
    
    Expected payload:
    {
        "mobile": "+91 9084117332",
        "jobDomain": "Data Science",  // optional
        "jobRole": "Data Analyst"     // optional
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'message': 'No data provided'
            }), 400
        
        mobile = data.get('mobile')
        job_domain = data.get('jobDomain')
        job_role = data.get('jobRole')
        
        if not mobile:
            return jsonify({
                'success': False,
                'message': 'Mobile number is required'
            }), 400
        
        # Job role skills now integrated in resume collection
        return jsonify({
            'success': True,
            'message': 'Job role skills are now integrated directly in resume collection',
            'note': 'Use /api/link-resume-profile endpoint to get job selection data'
        })
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error retrieving job role roadmap: {str(e)}'
        }), 500


@app.route('/api/get-all-roadmaps', methods=['POST'])
def get_all_roadmaps():
    """
    Get all roadmaps for a user from Roadmap_Dashboard collection.
    
    Expected payload:
    {
        "mobile": "+91 9084117332"
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'message': 'No data provided'
            }), 400
        
        mobile = data.get('mobile')
        
        if not mobile:
            return jsonify({
                'success': False,
                'message': 'Mobile number is required'
            }), 400
        
        print(f"\n=== Fetching roadmaps for mobile: {mobile} ===")
        
        # Get database connection
        db = get_db()
        # Note: Collection name has a trailing space
        roadmap_collection = db['Roadmap_Dashboard ']
        
        # Clean mobile number - remove all non-digits first
        clean_mobile = ''.join(filter(str.isdigit, mobile))
        
        # Try to find roadmaps for this user with various formats
        mobile_formats = [
            mobile,                    # Original format (e.g., "+91 8864862270")
            clean_mobile,              # Just digits (e.g., "918864862270")
            clean_mobile[-10:],        # Last 10 digits (e.g., "8864862270")
            f"+91 {clean_mobile[-10:]}", # +91 with space
            f"+91{clean_mobile[-10:]}"   # +91 without space
        ]
        
        # Remove duplicates while preserving order
        mobile_formats = list(dict.fromkeys(mobile_formats))
        
        print(f"🔍 Clean mobile (digits only): {clean_mobile}")
        print(f"📱 Last 10 digits: {clean_mobile[-10:]}")
        print(f"🔎 Trying mobile formats: {mobile_formats}")
        
        # Find all roadmaps for this user
        roadmaps = list(roadmap_collection.find({
            '_id': {'$in': mobile_formats}
        }))
        
        print(f"Found {len(roadmaps)} roadmaps")
        
        if not roadmaps:
            return jsonify({
                'success': False,
                'message': 'No roadmaps found for this user',
                'data': {
                    'roadmapsByDomain': {}
                }
            }), 404
        
        # Get user's job role from Resume collection
        resume_collection = db['Resume']
        user_resume = resume_collection.find_one({'_id': {'$in': mobile_formats}})
        user_job_role = None
        user_job_domain = None
        
        if user_resume:
            # Try to extract job role from nested structures
            job_selection = user_resume.get('jobSelection', {})
            job_role_skills = user_resume.get('jobRoleSkills', {})
            
            # Check nested jobSelection structure
            if isinstance(job_selection, dict):
                user_job_role = job_selection.get('jobRole')
                user_job_domain = job_selection.get('jobDomain')
            
            # If not found, check jobRoleSkills
            if not user_job_role and isinstance(job_role_skills, dict):
                user_job_role = job_role_skills.get('role')
                user_job_domain = job_role_skills.get('domain')
            
            # If still not found, check top-level fields
            if not user_job_role:
                user_job_role = user_resume.get('job_role') or user_resume.get('role')
            if not user_job_domain:
                user_job_domain = user_resume.get('domain') or user_resume.get('job_domain')
            
            # Format role and domain (convert from snake_case to Title Case)
            if user_job_role:
                user_job_role = user_job_role.replace('_', ' ').title()
            if user_job_domain:
                user_job_domain = user_job_domain.replace('_', ' ').title()
            
            print(f"📋 Found user's job role from Resume: {user_job_role}")
            print(f"📋 Found user's domain from Resume: {user_job_domain}")
        else:
            print(f"⚠️ No resume found for user, will use default role")
        
        # Process roadmaps and organize by domain/role
        roadmaps_by_domain = {}
        
        for roadmap in roadmaps:
            print(f"\n🔍 Processing roadmap document...")
            print(f"  - Keys: {list(roadmap.keys())}")
            print(f"  - Has 'roadmap' field: {'roadmap' in roadmap}")
            
            # Convert ObjectId to string for JSON serialization
            if '_id' in roadmap:
                roadmap['_id'] = str(roadmap['_id'])
            
            # Check if roadmap field exists and is a dict
            if 'roadmap' in roadmap:
                print(f"  - roadmap field type: {type(roadmap['roadmap'])}")
                if isinstance(roadmap['roadmap'], dict):
                    print(f"  - roadmap dict keys: {list(roadmap['roadmap'].keys())}")
            
            # Check if roadmap field contains nested structure (dict with Month keys)
            if 'roadmap' in roadmap and isinstance(roadmap['roadmap'], dict):
                # Extract nested roadmap structure
                roadmap_data = roadmap['roadmap']
                
                # Check if it has Month keys (Month 1, Month 2, etc.)
                month_keys = [k for k in roadmap_data.keys() if 'month' in k.lower()]
                
                if month_keys:
                    print(f"✅ Found {len(month_keys)} months in nested roadmap: {month_keys}")
                    
                    # Convert Month X to month_X format and preserve structure
                    months = {}
                    for key in month_keys:
                        month_num = ''.join(filter(str.isdigit, key))
                        if month_num:
                            month_data = roadmap_data[key]
                            
                            # If month data is a dict with structured fields, convert to text representation
                            if isinstance(month_data, dict):
                                # Format the structured data as readable text
                                text_parts = []
                                
                                if 'Skill Focus' in month_data:
                                    text_parts.append(f"**🎯 Skill Focus:** {month_data['Skill Focus']}\n")
                                
                                if 'Learning Goals' in month_data:
                                    text_parts.append("**💡 Learning Goals:**")
                                    for goal in month_data['Learning Goals']:
                                        text_parts.append(f"- {goal}")
                                    text_parts.append("")
                                
                                if 'Daily Plan (2 hours/day)' in month_data:
                                    text_parts.append("**📅 Daily Plan (2 hours/day):**")
                                    for plan in month_data['Daily Plan (2 hours/day)']:
                                        text_parts.append(f"- {plan}")
                                    text_parts.append("")
                                
                                if 'Mini Project' in month_data:
                                    text_parts.append(f"**🚀 Mini Project:** {month_data['Mini Project']}\n")
                                
                                if 'Expected Outcome' in month_data:
                                    text_parts.append(f"**✅ Expected Outcome:** {month_data['Expected Outcome']}")
                                
                                raw_text = '\n'.join(text_parts)
                            else:
                                raw_text = str(month_data)
                            
                            months[f'month_{month_num}'] = {'raw_text': raw_text}
                            print(f"  - Month {month_num}: {len(raw_text)} chars")
                    
                    # Extract metadata from roadmap_data or use defaults
                    # Use user's actual job role from Resume if available
                    role = (
                        roadmap_data.get('role') or 
                        roadmap_data.get('job_role') or 
                        user_job_role or 
                        'Data Analyst'
                    )
                    domain = (
                        roadmap_data.get('domain') or 
                        roadmap_data.get('job_domain') or 
                        user_job_domain or 
                        'Data Analysis'
                    )
                    duration = roadmap_data.get('duration', f'{len(months)} Months')
                    introduction = roadmap_data.get('introduction', f'Your personalized {len(months)}-month learning roadmap')
                    identified_gaps = roadmap_data.get('identified_gaps', [])
                    
                    # Organize into domain
                    if domain not in roadmaps_by_domain:
                        roadmaps_by_domain[domain] = []
                    
                    roadmap_obj = {
                        'role': role,
                        'duration': duration,
                        'introduction': introduction,
                        'next_steps': roadmap_data.get('next_steps', []),
                        'identified_gaps': identified_gaps if isinstance(identified_gaps, list) else [],
                        'category': 'Career Roadmap',
                        'total_months': len(months)
                    }
                    roadmap_obj.update(months)
                    roadmaps_by_domain[domain].append(roadmap_obj)
                    print(f"✅ Added roadmap to domain '{domain}': {role}, {len(months)} months")
                    continue
            
            # Check if roadmap_text field exists (alternate field name)
            if 'roadmap_text' in roadmap and isinstance(roadmap['roadmap_text'], str):
                print(f"✅ Found roadmap_text field!")
                roadmap_text = roadmap['roadmap_text']
                
                # Parse month sections (format: "Month 1:\n  Skill Focus: ...")
                import re
                month_pattern = r'Month\s+(\d+):(.*?)(?=Month\s+\d+:|$)'
                month_matches = re.findall(month_pattern, roadmap_text, re.DOTALL)
                
                if month_matches:
                    months = {}
                    for month_num, month_content in month_matches:
                        raw_text = month_content.strip()
                        months[f'month_{month_num}'] = {'raw_text': raw_text}
                        print(f"  - Month {month_num}: {len(raw_text)} chars")
                    
                    # Extract role and domain from other fields in the document or from Resume
                    role = roadmap.get('job_role') or roadmap.get('role')
                    domain = roadmap.get('job_domain') or roadmap.get('domain')
                    
                    # If not in roadmap doc, try to get from Resume collection
                    if not role or not domain:
                        resume_collection = db['Resume']
                        mobile_id = roadmap.get('_id')
                        resume_doc = resume_collection.find_one({'_id': mobile_id}) or resume_collection.find_one({'mobile': mobile_id})
                        
                        if resume_doc:
                            print(f"  📋 Found Resume document for {mobile_id}")
                            if not role:
                                # Try various role field names
                                role = (resume_doc.get('job_role') or 
                                       resume_doc.get('target_role') or 
                                       resume_doc.get('desired_role') or
                                       resume_doc.get('jobRole'))
                                
                                # Also check if it's stored in nested structures
                                if not role and 'jobSelection' in resume_doc:
                                    role = resume_doc['jobSelection'].get('jobRole')
                                    
                                print(f"  👤 Extracted role from Resume: {role}")
                            
                            if not domain:
                                domain = (resume_doc.get('job_domain') or 
                                         resume_doc.get('target_domain') or
                                         resume_doc.get('domain'))
                                
                                if not domain and 'jobSelection' in resume_doc:
                                    domain = resume_doc['jobSelection'].get('domain')
                                    
                                print(f"  🏢 Extracted domain from Resume: {domain}")
                    
                    # Try to extract from roadmap text if still not found
                    if not role or not domain:
                        # Try to find patterns like "Data Analyst", "Software Engineer", etc.
                        common_roles = {
                            r'\bdata\s+analyst\b': ('Data Analyst', 'Data Analysis'),
                            r'\bsoftware\s+engineer\b': ('Software Engineer', 'Software Engineering'),
                            r'\bweb\s+developer\b': ('Web Developer', 'Web Development'),
                            r'\bfull\s*stack\s+developer\b': ('Full Stack Developer', 'Full Stack Development'),
                            r'\bdata\s+scientist\b': ('Data Scientist', 'Data Science'),
                            r'\bmachine\s+learning\s+engineer\b': ('Machine Learning Engineer', 'Machine Learning'),
                            r'\bdevops\s+engineer\b': ('DevOps Engineer', 'DevOps'),
                            r'\bpython\s+developer\b': ('Python Developer', 'Python Development'),
                            r'\btableau\b.*\bvisualization\b': ('Data Analyst', 'Data Analytics'),
                            r'\bdata\s+visualization\b': ('Data Analyst', 'Data Analytics'),
                        }
                        
                        text_lower = roadmap_text.lower()
                        for pattern, (extracted_role, extracted_domain) in common_roles.items():
                            if re.search(pattern, text_lower, re.IGNORECASE):
                                if not role:
                                    role = extracted_role
                                    print(f"  🔍 Detected role from text: {role}")
                                if not domain:
                                    domain = extracted_domain
                                    print(f"  🔍 Detected domain from text: {domain}")
                                break
                    
                    # Clean up role and domain if they exist
                    if role:
                        role = role.replace('_', ' ').title()
                    elif user_job_role:
                        role = user_job_role.replace('_', ' ').title()
                    else:
                        role = 'Career Professional'
                    
                    if domain:
                        domain = domain.replace('_', ' ').title()
                    elif user_job_domain:
                        domain = user_job_domain.replace('_', ' ').title()
                    else:
                        domain = 'General'
                    
                    duration = f'{len(months)} Months'
                    introduction = f'Your personalized {len(months)}-month learning roadmap'
                    
                    # Organize into domain
                    if domain not in roadmaps_by_domain:
                        roadmaps_by_domain[domain] = []
                    
                    roadmap_obj = {
                        'role': role,
                        'duration': duration,
                        'introduction': introduction,
                        'next_steps': [],
                        'identified_gaps': [],
                        'category': 'Career Roadmap',
                        'total_months': len(months)
                    }
                    roadmap_obj.update(months)
                    roadmaps_by_domain[domain].append(roadmap_obj)
                    print(f"✅ Added roadmap from roadmap_text to domain '{domain}': {role}, {len(months)} months")
                    continue
            
            # Check if roadmap is in text format (single 'roadmap' field as string)
            if 'roadmap' in roadmap and isinstance(roadmap['roadmap'], str):
                # Parse text-based roadmap
                roadmap_text = roadmap['roadmap']
                
                # Extract role and domain - use user's actual role from Resume
                role = user_job_role or 'Data Analyst'  # Use user's job role from Resume
                domain = user_job_domain or 'Data Analysis'  # Use user's domain from Resume
                
                # Try to extract duration from text
                duration = '3-6 Months'  # Default from the text
                if 'month' in roadmap_text.lower():
                    import re
                    month_match = re.search(r'(\d+)\s*-?\s*(\d+)?\s*month', roadmap_text.lower())
                    if month_match:
                        if month_match.group(2):
                            duration = f"{month_match.group(1)}-{month_match.group(2)} Months"
                        else:
                            duration = f"{month_match.group(1)} Months"
                
                # Dynamically split roadmap into months based on detected weeks
                # Each month will contain 4 weeks
                
                def extract_week_range_content(text, start_week, end_week):
                    """Extract content for a specific week range"""
                    # Find all week section markers in the text
                    week_pattern = r'\*\*Week\s+(\d+)(?:-(\d+))?:'
                    matches = list(re.finditer(week_pattern, text, re.IGNORECASE))
                    
                    if not matches:
                        return None
                    
                    content_parts = []
                    found_start = False
                    
                    for i, match in enumerate(matches):
                        week_start = int(match.group(1))
                        week_end_num = int(match.group(2)) if match.group(2) else week_start
                        
                        # Stop if we've gone past our range
                        if week_start > end_week:
                            break
                        
                        # Check if this week falls within our range
                        # Include if week_start is in range OR week_end is in range OR range is contained within this week span
                        if (week_start >= start_week and week_start <= end_week) or \
                           (week_end_num >= start_week and week_end_num <= end_week) or \
                           (week_start <= start_week and week_end_num >= end_week):
                            
                            if not found_start:
                                found_start = True
                                # Include any preceding phase/skill focus header
                                section_start = match.start()
                                # Look back for phase header or skill focus
                                lines_before = text[:section_start].split('\n')
                                header_lines = []
                                for line in reversed(lines_before[-10:]):
                                    if '###' in line or '**🎯 Skill Focus:**' in line or '**💡 Learning Goals:**' in line:
                                        header_lines.insert(0, line)
                                    elif line.strip() == '' or line.strip() == '---':
                                        continue
                                    elif '###' not in line:
                                        break
                                
                                if header_lines:
                                    content_parts.append('\n'.join(header_lines) + '\n\n')
                            
                            # Find end of this week section (next week marker or end of text)
                            if i + 1 < len(matches):
                                # Check if next week is beyond our range
                                next_week_start = int(matches[i + 1].group(1))
                                if next_week_start > end_week:
                                    section_end = matches[i + 1].start()
                                else:
                                    section_end = matches[i + 1].start()
                            else:
                                section_end = len(text)
                            
                            week_content = text[match.start():section_end].strip()
                            content_parts.append(week_content)
                    
                    if content_parts:
                        return '\n\n'.join(content_parts)
                    return None
                
                def find_max_week(text):
                    """Find the maximum week number in the roadmap"""
                    week_pattern = r'\*\*Week\s+(\d+)(?:-(\d+))?:'
                    matches = re.findall(week_pattern, text, re.IGNORECASE)
                    max_week = 0
                    for match in matches:
                        week_start = int(match[0])
                        week_end = int(match[1]) if match[1] else week_start
                        max_week = max(max_week, week_end)
                    return max_week
                
                # Find the maximum week number to determine how many months we need
                max_week = find_max_week(roadmap_text)
                weeks_per_month = 4
                num_months = (max_week + weeks_per_month - 1) // weeks_per_month  # Ceiling division
                
                print(f"📊 Roadmap Analysis: {max_week} weeks detected, creating {num_months} months")
                
                # Dynamically extract months
                months = {}
                for month_num in range(1, num_months + 1):
                    start_week = (month_num - 1) * weeks_per_month + 1
                    end_week = min(month_num * weeks_per_month, max_week)
                    
                    month_content = extract_week_range_content(roadmap_text, start_week, end_week)
                    if month_content:
                        months[f'month_{month_num}'] = {'raw_text': month_content}
                        print(f"✅ Extracted Month {month_num} (Weeks {start_week}-{end_week}): {len(month_content)} chars")
                    else:
                        months[f'month_{month_num}'] = {}
                        print(f"⚠️  Month {month_num} (Weeks {start_week}-{end_week}): No content found")
                
                # Extract introduction (everything before Phase/Month 1)
                intro_match = re.search(r'^(.*?)(?=###\s*\*?\*?\s*(?:Phase|Month)\s*1)', roadmap_text, re.DOTALL | re.IGNORECASE)
                introduction = intro_match.group(1).strip() if intro_match else roadmap_text[:1000]
                print(f"✅ Extracted Introduction: {len(introduction)} chars")
                
                # Extract identified gaps/skills to focus on
                identified_gaps = []
                skill_focus_matches = re.findall(r'\*\*Skill Focus:\*\*([^\*]+)', roadmap_text, re.IGNORECASE)
                for match in skill_focus_matches:
                    skills = [s.strip() for s in match.split(',')]
                    identified_gaps.extend(skills[:3])  # Take first 3 from each phase
                
                # Create structured roadmap object
                role = roadmap.get('role', role)
                domain = roadmap.get('domain', domain)
                
            else:
                # Use existing structured format
                role = roadmap.get('role', 'Unknown Role')
                domain = roadmap.get('domain', 'General')
                duration = roadmap.get('duration', 'N/A')
                introduction = roadmap.get('introduction', '')
                identified_gaps = roadmap.get('identified_gaps', [])
                
                # Dynamically collect all month_X fields
                months = {}
                for key in roadmap.keys():
                    if key.startswith('month_'):
                        months[key] = roadmap.get(key, {})
            
            # Organize roadmaps
            if domain not in roadmaps_by_domain:
                roadmaps_by_domain[domain] = []
            
            # Build roadmap object with all months
            roadmap_obj = {
                'role': role,
                'duration': duration,
                'introduction': introduction,
                'next_steps': roadmap.get('next_steps', []),
                'identified_gaps': identified_gaps if isinstance(identified_gaps, list) else [],
                'category': roadmap.get('category', 'Career Roadmap'),
                'total_months': len(months) if months else 0
            }
            
            # Add all months dynamically
            roadmap_obj.update(months)
            
            roadmaps_by_domain[domain].append(roadmap_obj)
        
        print(f"Organized into domains: {list(roadmaps_by_domain.keys())}")
        
        # --- AUTO-GENERATE SKILL MAPPINGS IF MISSING ---
        # Check if skill mappings exist for this user, if not generate them
        try:
            skill_mapping_collection = db['skill_week_mapping']
            mobile_id = _normalize_mobile_id(mobile)
            
            existing_mapping = skill_mapping_collection.find_one({'_id': mobile_id})
            
            if not existing_mapping:
                print(f"\n🔧 No skill mappings found for user {mobile_id}")
                print(f"   Auto-generating skill mappings from roadmap...")
                
                # Get user's job role and skills from Resume collection
                job_role = None
                job_role_skills = None
                resume_collection = db['Resume']
                resume_doc = resume_collection.find_one({'_id': {'$in': mobile_formats}})
                if resume_doc:
                    # Try jobRoleSkills first (preferred)
                    job_role_skills_data = resume_doc.get('jobRoleSkills', {})
                    if job_role_skills_data:
                        job_role = job_role_skills_data.get('role')
                        job_domain = job_role_skills_data.get('domain')
                        current_skills = job_role_skills_data.get('current', [])
                        skills_to_learn = job_role_skills_data.get('skillsToLearn', [])
                        job_role_skills = current_skills + skills_to_learn
                    
                    # Fallback to jobSelection
                    if not job_role_skills:
                        job_selection = resume_doc.get('jobSelection', {})
                        job_role = job_selection.get('jobRole')
                        job_domain = job_selection.get('jobDomain')
                        selected_skills = job_selection.get('selectedSkills', [])
                        unselected_skills = job_selection.get('unselectedSkills', [])
                        job_role_skills = selected_skills + unselected_skills
                    
                    if job_role and job_role_skills:
                        print(f"   ✅ Found job selection: {job_domain}/{job_role}")
                        print(f"   Target skills: {job_role_skills}")
                
                # Generate mappings from Roadmap_Dashboard
                for roadmap in roadmaps:
                    if 'roadmap' in roadmap and isinstance(roadmap['roadmap'], dict):
                        roadmap_data = roadmap['roadmap']
                        
                        for month_key, month_data in roadmap_data.items():
                            # Extract month number from "Month 1", "Month 2", etc.
                            if not month_key.startswith('Month '):
                                continue
                            
                            try:
                                month_num = int(month_key.split(' ')[1])
                                
                                print(f"      Analyzing {month_key}...")
                                skill_mapping = _analyze_roadmap_dashboard_for_skills(month_data, job_role, job_role_skills)
                                
                                if skill_mapping:
                                    _save_skill_week_mapping(mobile, month_num, skill_mapping)
                                    print(f"      ✅ Generated mapping for Month {month_num}: {len(skill_mapping)} skills")
                            except (ValueError, IndexError) as e:
                                print(f"      ⚠️ Could not parse month number from '{month_key}': {e}")
                                continue
                
                print(f"   ✅ Skill mapping auto-generation complete")
            else:
                print(f"   ℹ️ Skill mappings already exist for user {mobile_id}")
        except Exception as mapping_error:
            print(f"   ⚠️ Error auto-generating skill mappings: {mapping_error}")
            # Don't fail the main request if mapping generation fails
        
        return jsonify({
            'success': True,
            'message': f'Found {len(roadmaps)} roadmap(s)',
            'data': {
                'roadmapsByDomain': roadmaps_by_domain,
                'totalRoadmaps': len(roadmaps)
            }
        })
            
    except Exception as e:
        print(f"Error in get_all_roadmaps: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error retrieving roadmaps: {str(e)}'
        }), 500

@app.route('/api/get-user-courses', methods=['POST'])
def get_user_courses():
    """
    Get recommended courses for a user from Course collection.
    
    Expected payload:
    {
        "mobile": "+91 9084117332"
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'message': 'No data provided'
            }), 400
        
        mobile = data.get('mobile')
        
        if not mobile:
            return jsonify({
                'success': False,
                'message': 'Mobile number is required'
            }), 400
        
        print(f"\n=== Fetching courses for mobile: {mobile} ===")
        
        # Get database connection
        db = get_db()
        courses_collection = db['Course']
        
        # Try multiple mobile number formats to find a match
        mobile_formats = [
            mobile,  # Exact as provided
            f'+91 {mobile}',  # Add +91 with space
            f'+91{mobile}',  # Add +91 without space
            mobile.replace('+91', '').strip(),  # Remove +91 prefix
            mobile.replace('+91 ', ''),  # Remove +91 with space
            mobile.replace('+91', ' ').strip(),  # Replace +91 with space
        ]
        
        # If mobile starts with +91, also try with space after it
        if mobile.startswith('+91') and not mobile.startswith('+91 '):
            mobile_formats.append(mobile.replace('+91', '+91 ', 1))
        
        # Remove duplicates while preserving order
        mobile_formats = list(dict.fromkeys(mobile_formats))
        
        print(f"Trying mobile formats: {mobile_formats}")
        
        user_courses = None
        matched_format = None
        
        for format_mobile in mobile_formats:
            user_courses = courses_collection.find_one({'_id': format_mobile})
            if user_courses:
                matched_format = format_mobile
                print(f"✅ Found courses with format: {matched_format}")
                break
        
        if not user_courses:
            return jsonify({
                'success': False,
                'message': 'No courses found for this user',
                'data': {
                    'courses': {},
                    'catalog_stats': {}
                }
            }), 404
        
        # Convert ObjectId to string for JSON serialization
        user_courses['_id'] = str(user_courses['_id'])
        
        # Get courses - check multiple field names for compatibility
        courses = user_courses.get('courses', {})
        
        # If 'courses' field is empty, merge from alternate fields (youtube_resources, professional_courses)
        if not courses or len(courses) == 0:
            print("📦 'courses' field is empty, checking alternate fields...")
            
            # Get array-based course data
            youtube_resources = user_courses.get('youtube_resources', [])
            professional_courses = user_courses.get('professional_courses', [])
            microsoft_learn = user_courses.get('microsoft_learn_courses', [])
            
            print(f"  - youtube_resources: {len(youtube_resources)} courses")
            print(f"  - professional_courses: {len(professional_courses)} courses")
            print(f"  - microsoft_learn_courses: {len(microsoft_learn)} courses")
            
            # Check if they are arrays (new format) or objects (old format)
            if isinstance(youtube_resources, list) or isinstance(professional_courses, list) or isinstance(microsoft_learn, list):
                print("  📋 Converting from array format to skill-keyed format...")
                
                # Convert array format to skill-keyed format
                merged_courses = {}
                
                # Process YouTube resources
                if isinstance(youtube_resources, list):
                    for course in youtube_resources:
                        skill = course.get('skill', 'Unknown')
                        if skill not in merged_courses:
                            merged_courses[skill] = []
                        merged_courses[skill].append(course)
                
                # Process professional courses
                if isinstance(professional_courses, list):
                    for course in professional_courses:
                        skill = course.get('skill', 'Unknown')
                        if skill not in merged_courses:
                            merged_courses[skill] = []
                        merged_courses[skill].append(course)
                
                # Process Microsoft Learn courses
                if isinstance(microsoft_learn, list):
                    for course in microsoft_learn:
                        skill = course.get('skill', 'Unknown')
                        if skill not in merged_courses:
                            merged_courses[skill] = []
                        merged_courses[skill].append(course)
                
                courses = merged_courses
                print(f"✅ Converted to {len(courses)} skills from array format")
            else:
                # Old format - already object-based
                merged_courses = {}
                
                # Get all unique skill names across all sources
                all_skills = set()
                all_skills.update(youtube_resources.keys() if isinstance(youtube_resources, dict) else [])
                all_skills.update(professional_courses.keys() if isinstance(professional_courses, dict) else [])
                all_skills.update(microsoft_learn.keys() if isinstance(microsoft_learn, dict) else [])
                
                for skill in all_skills:
                    skill_courses = []
                    
                    # Add YouTube courses
                    if isinstance(youtube_resources, dict) and skill in youtube_resources:
                        skill_courses.extend(youtube_resources[skill])
                    
                    # Add professional courses
                    if isinstance(professional_courses, dict) and skill in professional_courses:
                        skill_courses.extend(professional_courses[skill])
                    
                    # Add Microsoft Learn courses
                    if isinstance(microsoft_learn, dict) and skill in microsoft_learn:
                        skill_courses.extend(microsoft_learn[skill])
                    
                    if skill_courses:
                        merged_courses[skill] = skill_courses
                
                courses = merged_courses
                print(f"✅ Merged {len(courses)} skills from object format")
        
        catalog_stats = user_courses.get('catalog_stats', {})
        
        # Calculate stats if not present
        if not catalog_stats:
            total_courses = sum(len(course_list) for course_list in courses.values())
            catalog_stats = {
                'total_skills': len(courses),
                'total_courses': total_courses
            }
        
        print(f"Found {len(courses)} skills with courses")
        print(f"Catalog stats: {catalog_stats}")
        
        return jsonify({
            'success': True,
            'message': f'Found courses for {len(courses)} skills',
            'data': {
                'courses': courses,
                'catalog_stats': catalog_stats,
                'total_skills': len(courses)
            }
        })
            
    except Exception as e:
        print(f"Error in get_user_courses: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error retrieving courses: {str(e)}'
        }), 500


@app.route('/api/curate-learning-path', methods=['POST'])
def curate_learning_path():
    """
    Use Perplexity AI to curate courses into:
    1. Recommended Path (core courses to take in order)
    2. Alternative Options (other courses for same skill)
    
    Expected payload:
    {
        "skill": "Basic feature engineering",
        "courses": [
            {"title": "...", "url": "...", "provider": "..."},
            ...
        ],
        "context": "Data Analyst roadmap - Month 1"
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'message': 'No data provided'
            }), 400
        
        skill = data.get('skill')
        courses = data.get('courses', [])
        context = data.get('context', '')
        
        if not skill or not courses:
            return jsonify({
                'success': False,
                'message': 'Skill and courses are required'
            }), 400
        
        print(f"\n🎯 Curating learning path for: {skill}")
        print(f"   Available courses: {len(courses)}")
        
        # Get Perplexity API key
        perplexity_api_key = os.getenv('PERPLEXITY_API_KEY')
        
        if not perplexity_api_key:
            return jsonify({
                'success': False,
                'message': 'Perplexity API key not configured'
            }), 500
        
        # Format courses for Perplexity
        courses_list = "\n".join([
            f"{i+1}. {course.get('title', 'N/A')} - {course.get('provider', course.get('channel', 'N/A'))}"
            for i, course in enumerate(courses)
        ])
        
        # Create Perplexity prompt
        prompt = f"""You are an expert learning path curator. Given a skill topic and a list of available courses, organize them into an optimal learning path.

**Skill Topic:** {skill}
**Context:** {context}

**Available Courses:**
{courses_list}

**Task:** Analyze these courses and organize them into:
1. **Recommended Path** - Select 1-2 CORE courses that provide the best learning progression (beginner-friendly, comprehensive)
2. **Alternative Options** - List remaining courses as alternatives (different teaching styles, supplementary content)

**Output Format (JSON):**
{{
    "recommended_path": [1, 3],
    "alternatives": [2, 4, 5, 6],
    "reasoning": "Brief explanation of why the recommended courses are best for beginners"
}}

Return ONLY valid JSON. Use course numbers (1-{len(courses)}) from the list above."""

        # Call Perplexity API
        headers = {
            'Authorization': f'Bearer {perplexity_api_key}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            'model': 'sonar',
            'messages': [
                {
                    'role': 'system',
                    'content': 'You are a helpful learning path curator. Always return valid JSON.'
                },
                {
                    'role': 'user',
                    'content': prompt
                }
            ],
            'temperature': 0.3,
            'max_tokens': 500
        }
        
        print("📡 Calling Perplexity API...")
        response = requests.post(
            'https://api.perplexity.ai/chat/completions',
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"❌ Perplexity API error: {response.status_code}")
            print(f"Response: {response.text}")
            return jsonify({
                'success': False,
                'message': f'Perplexity API error: {response.status_code}'
            }), 500
        
        result = response.json()
        ai_content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
        
        print(f"🤖 Perplexity response: {ai_content[:200]}...")
        
        # Parse JSON from response
        import json
        import re
        
        # Extract JSON from response (handle markdown code blocks)
        json_match = re.search(r'```json\s*(.*?)\s*```', ai_content, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find JSON object directly
            json_match = re.search(r'\{.*\}', ai_content, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                json_str = ai_content
        
        try:
            curation = json.loads(json_str)
        except json.JSONDecodeError:
            print(f"⚠️ Failed to parse JSON, using fallback")
            # Fallback: recommend first 2, rest as alternatives
            curation = {
                'recommended_path': [1, 2] if len(courses) >= 2 else [1],
                'alternatives': list(range(3, len(courses) + 1)),
                'reasoning': 'Using default curation (first courses as recommended)'
            }
        
        # Map indices to actual courses
        recommended_courses = []
        alternative_courses = []
        
        for idx in curation.get('recommended_path', []):
            if 1 <= idx <= len(courses):
                recommended_courses.append(courses[idx - 1])
        
        for idx in curation.get('alternatives', []):
            if 1 <= idx <= len(courses):
                alternative_courses.append(courses[idx - 1])
        
        print(f"✅ Curated: {len(recommended_courses)} recommended, {len(alternative_courses)} alternatives")
        
        return jsonify({
            'success': True,
            'data': {
                'skill': skill,
                'recommended_path': recommended_courses,
                'alternatives': alternative_courses,
                'reasoning': curation.get('reasoning', 'Courses curated based on learning progression'),
                'total_recommended': len(recommended_courses),
                'total_alternatives': len(alternative_courses)
            }
        })
        
    except Exception as e:
        print(f"Error in curate_learning_path: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'Error curating learning path: {str(e)}'
        }), 500


@app.route('/api/organize-courses-by-week', methods=['POST', 'OPTIONS'])
def organize_courses_by_week():
    """
    Use Perplexity AI to organize monthly courses into weekly learning paths.
    For each topic, rank courses as "Best Course" and "Other Recommended Courses".
    
    NOW WITH CACHING: First checks MongoDB for existing weekly plan, generates if not found.
    
    Expected payload:
    {
        "month_data": {
            "month_number": 1,
            "topics": ["Basic feature engineering", "Data visualization basics"],
            "raw_text": "Month content..."
        },
        "all_courses": {
            "Basic feature engineering": [{...}, {...}],
            "Data visualization basics": [{...}, {...}]
        },
        "mobile": "optional - for caching per user"
    }
    """
    # Handle OPTIONS for CORS preflight
    if request.method == 'OPTIONS':
        return jsonify({'status': 'ok'}), 200
    
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400
        
        month_data = data.get('month_data', {})
        all_courses = data.get('all_courses', {})
        mobile = data.get('mobile', '')
        
        month_number = month_data.get('month_number', 1)
        topics = month_data.get('topics', [])
        raw_text = month_data.get('raw_text', '')
        
        if not topics or not all_courses:
            return jsonify({'success': False, 'message': 'Topics and courses are required'}), 400
        
        print(f"\n📅 Organizing Month {month_number} courses into weekly plan...")
        print(f"   Topics: {len(topics)}")
        print(f"   Mobile: {mobile if mobile else 'Not provided'}")
        
        # Generate lock key for preventing duplicate requests
        lock_key = f"{_normalize_mobile_id(mobile)}_month{month_number}"
        
        # --- CHECK CACHE FIRST ---
        cached_plan = _get_cached_weekly_plan(mobile, month_number)
        if cached_plan:
            print(f"✅ Found cached weekly plan for Month {month_number}")
            return jsonify({
                'success': True,
                'data': {
                    'month': month_number,
                    'weekly_plan': cached_plan,
                    'cached': True
                }
            })
        
        # --- CHECK IF ANOTHER REQUEST IS ALREADY GENERATING THIS PLAN ---
        with _weekly_plan_lock_mutex:
            if lock_key in _weekly_plan_locks:
                print(f"   ⏳ Another request is generating this plan, waiting...")
                lock = _weekly_plan_locks[lock_key]
            else:
                lock = threading.Lock()
                _weekly_plan_locks[lock_key] = lock
        
        # Wait for lock (if another request is generating)
        with lock:
            # Re-check cache after acquiring lock (might have been saved by another request)
            cached_plan = _get_cached_weekly_plan(mobile, month_number)
            if cached_plan:
                print(f"✅ Found cached weekly plan after waiting for Month {month_number}")
                # Clean up lock
                with _weekly_plan_lock_mutex:
                    _weekly_plan_locks.pop(lock_key, None)
                return jsonify({
                    'success': True,
                    'data': {
                        'month': month_number,
                        'weekly_plan': cached_plan,
                        'cached': True
                    }
                })
        
            print(f"   📋 No cache found, generating new weekly plan...")
        print(f"   Topics list: {topics[:5]}...")  # Show first 5 topics
        
        # Get Perplexity API key
        perplexity_api_key = os.getenv('PERPLEXITY_API_KEY')
        print(f"   🔑 Perplexity API key loaded: {'✅ Yes' if perplexity_api_key else '❌ No'}")
        if perplexity_api_key:
            print(f"   🔑 Key length: {len(perplexity_api_key)} chars")
            print(f"   🔑 Key starts with: {perplexity_api_key[:10]}...")
        
        if not perplexity_api_key:
            return jsonify({'success': False, 'message': 'Perplexity API key not configured'}), 500
        
        # Build topics list with course counts
        topics_summary = []
        for topic in topics:
            course_count = len(all_courses.get(topic, []))
            topics_summary.append(f"- {topic} ({course_count} courses)")
        
        topics_str = "\n".join(topics_summary)
        
        # Get month raw text for roadmap content
        month_raw_text = month_data.get('raw_text', '')
        
        print(f"   Month text length: {len(month_raw_text)} chars")
        
        # Create Perplexity prompt to parse and organize the existing roadmap by weeks
        prompt = f"""You are an expert curriculum organizer. Analyze this Month {month_number} learning roadmap and organize it into a 4-week structure.

**Original Month {month_number} Roadmap:**
{month_raw_text}

**Available Course Topics (for reference):**
{topics_str}

**Task:** Parse the existing roadmap content and organize it into 4 weeks. The roadmap already contains:
- 📅 Daily Plan (which weeks cover which topics)
- 🎨 Mini Project descriptions  
- 🎯 Skill Focus areas
- ✅ Expected Outcomes

For each week (1-4), extract and provide:
1. **learning_goal**: The main objective for this week (1-2 sentences)
2. **roadmap**: Detailed description of what to learn, practice, and build this week (3-5 sentences, include Daily Plan details, practice activities, mini projects if mentioned)
3. **topics**: List of skill/topic names that should be covered (extract from Skill Focus or relevant sections)

**IMPORTANT**: 
- If the Daily Plan mentions "Weeks 1-2: Excel" → put Excel-related content in week_1 and week_2
- If it mentions "Weeks 3-4: SQL" → put SQL-related content in week_3 and week_4
- Parse the actual activities, projects, and learning goals from the roadmap text
- Don't just list topics - include the actual learning plan and activities described

**Output Format (JSON):**
{{
    "week_1": {{
        "learning_goal": "What to achieve in week 1",
        "roadmap": "Detailed learning plan: what to study, practice, build in week 1 based on Daily Plan",
        "topics": ["topic1", "topic2"]
    }},
    "week_2": {{
        "learning_goal": "What to achieve in week 2",
        "roadmap": "Detailed learning plan for week 2",
        "topics": ["topic3"]
    }},
    "week_3": {{
        "learning_goal": "What to achieve in week 3",
        "roadmap": "Detailed learning plan for week 3",
        "topics": ["topic4", "topic5"]
    }},
    "week_4": {{
        "learning_goal": "What to achieve in week 4",  
        "roadmap": "Detailed learning plan for week 4",
        "topics": ["topic6"]
    }}
}}

Return ONLY valid JSON. Extract topics from the available course topics list above."""

        headers = {
            'Authorization': f'Bearer {perplexity_api_key}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            'model': 'sonar',
            'messages': [
                {'role': 'system', 'content': 'You are a curriculum designer. Always return valid JSON.'},
                {'role': 'user', 'content': prompt}
            ],
            'temperature': 0.2,
            'max_tokens': 800
        }
        
        print("📡 Calling Perplexity for weekly organization...")
        response = requests.post(
            'https://api.perplexity.ai/chat/completions',
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"❌ Perplexity API error: {response.status_code}")
            print(f"   Response: {response.text[:500]}")  # Print first 500 chars of error
            # Fallback: distribute topics evenly
            weekly_plan = _fallback_weekly_distribution(topics)
        else:
            result = response.json()
            ai_content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
            print(f"   🤖 AI Response length: {len(ai_content)} chars")
            print(f"   🤖 AI Response preview: {ai_content[:300]}...")
            weekly_plan = _parse_weekly_json(ai_content, topics)
            print(f"   📋 Parsed weekly plan keys: {list(weekly_plan.keys())}")
            for week_key in ['week_1', 'week_2', 'week_3', 'week_4']:
                if week_key in weekly_plan:
                    week_topics = weekly_plan[week_key].get('topics', []) if isinstance(weekly_plan[week_key], dict) else weekly_plan[week_key]
                    print(f"   📋 {week_key} topics: {week_topics}")
        
        print(f"✅ Weekly plan created")
        
        # Validate and fix empty weeks - ensure each week has topics from available list
        for week_num in range(1, 5):
            week_key = f"week_{week_num}"
            if week_key in weekly_plan:
                week_data = weekly_plan[week_key]
                if isinstance(week_data, dict):
                    week_topics = week_data.get('topics', [])
                    if not week_topics or len(week_topics) == 0:
                        # If week has no topics, add some from the available topics list
                        start_idx = (week_num - 1) * (len(topics) // 4)
                        end_idx = start_idx + max(1, len(topics) // 4)
                        fallback_topics = topics[start_idx:end_idx]
                        print(f"   ⚠️ {week_key} has no topics, adding fallback: {fallback_topics}")
                        weekly_plan[week_key]['topics'] = fallback_topics
        
        # Now rank courses for each topic using Perplexity
        organized_weeks = {}
        
        for week_num in range(1, 5):
            week_key = f"week_{week_num}"
            week_data = weekly_plan.get(week_key, {})
            
            # Handle both old format (list) and new format (dict with topics and learning_goal)
            if isinstance(week_data, list):
                week_topics = week_data
                learning_goal = ""
                roadmap = ""
            elif isinstance(week_data, dict):
                week_topics = week_data.get('topics', [])
                learning_goal = week_data.get('learning_goal', '')
                roadmap = week_data.get('roadmap', '')
            else:
                continue
            
            if not week_topics:
                continue
            
            organized_weeks[week_key] = {
                'topics': [],
                'learning_goal': learning_goal,
                'roadmap': roadmap
            }
            
            for topic in week_topics:
                topic_courses = all_courses.get(topic, [])
                
                # Include topic even if no courses found (so week doesn't appear empty)
                if not topic_courses:
                    print(f"      ⚠️ No courses found for topic '{topic}' in week {week_num}")
                    # Add topic with empty course lists
                    organized_weeks[week_key]['topics'].append({
                        'name': topic,
                        'best_course': None,
                        'other_courses': [],
                        'reasoning': f'No courses available for {topic} yet.'
                    })
                    continue
                
                # Rank courses for this topic
                ranked = _rank_courses_with_perplexity(
                    topic, 
                    topic_courses, 
                    perplexity_api_key,
                    f"Month {month_number}, Week {week_num}"
                )
                
                organized_weeks[week_key]['topics'].append({
                    'name': topic,
                    'best_course': ranked['best_course'],
                    'other_courses': ranked['other_courses'],
                    'reasoning': ranked.get('reasoning', '')
                })
        
        # --- SAVE TO CACHE ---
        _save_weekly_plan_to_cache(mobile, month_number, organized_weeks)
        
        # --- ANALYZE ROADMAP TO MAP SKILLS TO COMPLETION WEEKS ---
        print(f"\n🔍 Starting skill-week mapping analysis for Month {month_number}...")
        print(f"   Mobile: {mobile}")
        skill_week_mapping = _analyze_roadmap_for_skill_completion(organized_weeks, month_number)
        print(f"   Mapping result: {skill_week_mapping}")
        
        if skill_week_mapping and mobile:
            print(f"   💾 Saving skill-week mapping...")
            _save_skill_week_mapping(mobile, month_number, skill_week_mapping)
        elif not skill_week_mapping:
            print(f"   ⚠️ No skill mapping generated (empty result)")
        elif not mobile:
            print(f"   ⚠️ No mobile number provided, cannot save mapping")
        
        # Clean up lock
        with _weekly_plan_lock_mutex:
            _weekly_plan_locks.pop(lock_key, None)
        
        return jsonify({
            'success': True,
            'data': {
                'month': month_number,
                'weekly_plan': organized_weeks,
                'cached': False
            }
        })
        
    except Exception as e:
        print(f"Error in organize_courses_by_week: {str(e)}")
        import traceback
        traceback.print_exc()
        # Clean up lock on error too
        try:
            lock_key = f"{_normalize_mobile_id(data.get('mobile', ''))}_month{data.get('month_data', {}).get('month_number', 1)}"
            with _weekly_plan_lock_mutex:
                _weekly_plan_locks.pop(lock_key, None)
        except:
            pass
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500


def _get_weekly_plans_collection():
    """Get the weekly_plans collection from MongoDB"""
    try:
        mongo_uri = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
        db_name = os.getenv('MONGODB_DB', 'Placement_Ai')
        collection_name = os.getenv('MONGODB_COLLECTION_WEEKLY_PLANS', 'weekly_plans')
        
        client = MongoClient(mongo_uri)
        db = client[db_name]
        return db[collection_name]
    except Exception as e:
        print(f"❌ Error connecting to weekly_plans collection: {e}")
        return None


def _normalize_mobile_id(mobile):
    """Normalize mobile to a consistent ID (last 10 digits)"""
    if not mobile:
        return "global"
    digits = normalize_phone(mobile)
    # Use only the last 10 digits (actual phone number without country code)
    if len(digits) >= 10:
        return digits[-10:]
    return digits if digits else "global"


def _get_cached_weekly_plan(mobile, month_number):
    """Retrieve cached weekly plan from MongoDB if exists.
    
    New structure: One document per user with all months nested.
    {
        "_id": "8864862270",  # phone number as ID
        "months": {
            "month_1": { weekly_plan data },
            "month_2": { weekly_plan data },
            ...
        },
        "created_at": datetime,
        "updated_at": datetime
    }
    """
    try:
        collection = _get_weekly_plans_collection()
        if collection is None:
            print("   💾 No weekly_plans collection available")
            return None
        
        mobile_id = _normalize_mobile_id(mobile)
        month_key = f"month_{month_number}"
        
        print(f"   💾 Looking for user: {mobile_id}, month: {month_key}")
        
        # Find user's document
        user_doc = collection.find_one({'_id': mobile_id})
        
        if user_doc and 'months' in user_doc and month_key in user_doc['months']:
            print(f"   💾 ✅ Cache HIT for user {mobile_id}, {month_key}")
            return user_doc['months'][month_key]
        
        # Try legacy format (separate documents per month with cache_key)
        legacy_key = f"{mobile_id}_month{month_number}"
        legacy_doc = collection.find_one({'cache_key': legacy_key})
        if legacy_doc and 'weekly_plan' in legacy_doc:
            print(f"   💾 ✅ Cache HIT (legacy format): {legacy_key}")
            # Migrate to new format
            _save_weekly_plan_to_cache(mobile, month_number, legacy_doc['weekly_plan'])
            return legacy_doc['weekly_plan']
        
        # Also try with full digits (old legacy)
        if mobile:
            full_digits_key = f"{normalize_phone(mobile)}_month{month_number}"
            if full_digits_key != legacy_key:
                legacy_doc = collection.find_one({'cache_key': full_digits_key})
                if legacy_doc and 'weekly_plan' in legacy_doc:
                    print(f"   💾 ✅ Cache HIT (old legacy): {full_digits_key}")
                    _save_weekly_plan_to_cache(mobile, month_number, legacy_doc['weekly_plan'])
                    return legacy_doc['weekly_plan']
        
        print(f"   💾 ❌ Cache MISS for user {mobile_id}, {month_key}")
        return None
        
    except Exception as e:
        print(f"❌ Error retrieving cached weekly plan: {e}")
        return None


def _save_weekly_plan_to_cache(mobile, month_number, weekly_plan):
    """Save generated weekly plan to MongoDB cache.
    
    New structure: One document per user with all months nested.
    """
    try:
        collection = _get_weekly_plans_collection()
        if collection is None:
            print("   💾 No weekly_plans collection available for saving")
            return False
        
        mobile_id = _normalize_mobile_id(mobile)
        month_key = f"month_{month_number}"
        
        # Upsert: Update the specific month in the user's document
        result = collection.update_one(
            {'_id': mobile_id},
            {
                '$set': {
                    f'months.{month_key}': weekly_plan,
                    'updated_at': datetime.utcnow()
                },
                '$setOnInsert': {
                    'created_at': datetime.utcnow()
                }
            },
            upsert=True
        )
        
        print(f"   💾 Saved weekly plan for user {mobile_id}, {month_key}")
        return True
        
    except Exception as e:
        print(f"❌ Error saving weekly plan to cache: {e}")
        return False


def _analyze_roadmap_for_skill_completion(organized_weeks, month_number):
    """
    Use Perplexity AI to analyze the 4-week roadmap and determine 
    which skills are completed at which week.
    
    Returns: {"NLP": 2, "Transformers": 4, "Python": 1}
    Meaning: NLP completes at week 2, Transformers at week 4, Python at week 1
    """
    try:
        perplexity_api_key = os.getenv('PERPLEXITY_API_KEY')
        if not perplexity_api_key:
            print("⚠️ Perplexity API key not available for skill mapping")
            return {}
        
        # Extract roadmap details for all 4 weeks
        roadmap_summary = []
        all_topics = set()
        
        print(f"   📋 Extracting topics from organized_weeks structure...")
        
        for week_num in range(1, 5):
            week_key = f"week_{week_num}"
            week_data = organized_weeks.get(week_key, {})
            
            learning_goal = week_data.get('learning_goal', '')
            roadmap_text = week_data.get('roadmap', '')
            topics = week_data.get('topics', [])
            
            print(f"      Week {week_num}: {len(topics) if isinstance(topics, list) else 0} topics")
            
            # Extract topic names
            topic_names = []
            if isinstance(topics, list):
                for topic in topics:
                    if isinstance(topic, dict):
                        topic_names.append(topic.get('name', ''))
                    else:
                        topic_names.append(str(topic))
            
            for topic in topic_names:
                if topic:  # Only add non-empty topics
                    all_topics.add(topic)
            
            roadmap_summary.append(f"""
**Week {week_num}:**
- Learning Goal: {learning_goal}
- Roadmap: {roadmap_text}
- Topics Covered: {', '.join(topic_names)}
""")
        
        roadmap_text = "\n".join(roadmap_summary)
        topics_list = list(all_topics)
        
        print(f"   📊 Total unique topics extracted: {len(topics_list)}")
        print(f"   Topics: {topics_list[:5]}..." if len(topics_list) > 5 else f"   Topics: {topics_list}")
        
        # FALLBACK: If no topics found in topics array, extract from roadmap text
        if not topics_list:
            print("   ⚠️ No topics found in topics array, attempting to extract from roadmap text...")
            
            # Use Perplexity to extract skills from the roadmap text
            extraction_prompt = f"""Analyze this 4-week learning roadmap and extract the main skills/topics being taught each week.

{roadmap_text}

**Task:** Identify the key skills or topics that are COMPLETED by each week. Return a JSON mapping of skill names to their completion week (1-4).

**Rules:**
- If a skill spans multiple weeks (e.g., "Excel in weeks 1-2"), completion week is the LAST week
- Extract specific skill names mentioned in Learning Goals and Roadmap text
- Be specific: "Excel Basic Formulas", "Data Cleaning", "Pivot Tables" instead of just "Excel"

**Output Format (JSON only, no markdown):**
{{
  "Skill Name 1": 2,
  "Skill Name 2": 4,
  "Skill Name 3": 1
}}"""

            try:
                headers = {
                    'Authorization': f'Bearer {perplexity_api_key}',
                    'Content-Type': 'application/json'
                }
                
                payload = {
                    'model': 'sonar',
                    'messages': [
                        {'role': 'system', 'content': 'You are a curriculum expert. Always respond with valid JSON only.'},
                        {'role': 'user', 'content': extraction_prompt}
                    ],
                    'temperature': 0.2,
                    'max_tokens': 1000
                }
                
                print("      🔄 Calling Perplexity AI to extract skills from roadmap text...")
                response = requests.post(
                    'https://api.perplexity.ai/chat/completions',
                    headers=headers,
                    json=payload,
                    timeout=30
                )
                
                if response.status_code == 200:
                    ai_response = response.json()
                    ai_content = ai_response['choices'][0]['message']['content']
                    
                    # Parse JSON response
                    ai_content_clean = ai_content.strip()
                    if ai_content_clean.startswith('```'):
                        lines = ai_content_clean.split('\n')
                        ai_content_clean = '\n'.join([line for line in lines if not line.startswith('```')])
                    
                    skill_mapping = json.loads(ai_content_clean)
                    print(f"      ✅ Extracted skills from roadmap text: {skill_mapping}")
                    return skill_mapping
                else:
                    print(f"      ❌ Extraction failed: {response.status_code}")
                    return {}
            except Exception as extract_error:
                print(f"      ❌ Error extracting from roadmap text: {str(extract_error)}")
                return {}
        
        if not topics_list:
            print("   ⚠️ No topics found in roadmap for skill mapping")
            print(f"   Debug: organized_weeks keys = {list(organized_weeks.keys())}")
            print(f"   Debug: week_1 structure = {organized_weeks.get('week_1', {})}")
            return {}
        
        print(f"\n🤖 Analyzing Month {month_number} roadmap to map skills to completion weeks...")
        print(f"   Topics to analyze: {topics_list}")
        
        # Create prompt for Perplexity
        prompt = f"""You are an expert curriculum analyzer. Analyze this 4-week learning roadmap and determine AT WHICH WEEK each skill is FULLY COMPLETED.

**Month {month_number} Roadmap:**
{roadmap_text}

**All Topics/Skills:**
{', '.join(topics_list)}

**Task:** For each skill/topic, determine the week number (1, 2, 3, or 4) when that skill is FULLY COMPLETED based on the roadmap structure.

**Rules:**
1. If a skill spans multiple weeks (e.g., "Excel in Week 1-2"), the completion week is the LAST week (Week 2)
2. If a skill is only mentioned in one week, that's the completion week
3. Look at learning goals and roadmap descriptions to understand when mastery is achieved
4. Consider: "Basics" in Week 1, "Advanced" in Week 2 → Skill completes at Week 2

**IMPORTANT:** Return ONLY valid JSON mapping skill names to their completion week numbers (1-4).

**Example Output:**
{{
  "Excel Basics": 2,
  "SQL Fundamentals": 4,
  "Data Visualization": 3,
  "Python Programming": 1
}}

**Return only the JSON object, no markdown, no explanations.**"""

        headers = {
            'Authorization': f'Bearer {perplexity_api_key}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            'model': 'sonar',
            'messages': [
                {
                    'role': 'system',
                    'content': 'You are a curriculum analysis expert. Always respond with valid JSON only.'
                },
                {
                    'role': 'user',
                    'content': prompt
                }
            ],
            'temperature': 0.2,
            'max_tokens': 1000
        }
        
        print("   🔄 Calling Perplexity AI for skill-week mapping...")
        response = requests.post(
            'https://api.perplexity.ai/chat/completions',
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"   ❌ Perplexity API error: {response.status_code}")
            return {}
        
        ai_response = response.json()
        ai_content = ai_response['choices'][0]['message']['content']
        
        # Parse JSON response (remove markdown code blocks if present)
        ai_content_clean = ai_content.strip()
        if ai_content_clean.startswith('```'):
            lines = ai_content_clean.split('\n')
            ai_content_clean = '\n'.join([line for line in lines if not line.startswith('```')])
        
        skill_mapping = json.loads(ai_content_clean)
        
        print(f"   ✅ Skill-Week Mapping: {skill_mapping}")
        return skill_mapping
        
    except Exception as e:
        print(f"   ❌ Error analyzing roadmap for skills: {str(e)}")
        import traceback
        traceback.print_exc()
        return {}


def _save_skill_week_mapping(mobile, month_number, skill_mapping):
    """Save skill-to-week completion mapping in MongoDB"""
    try:
        mongo_uri = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
        db_name = os.getenv('MONGODB_DB', 'Placement_Ai')
        
        client = MongoClient(mongo_uri)
        db = client[db_name]
        collection = db['skill_week_mapping']
        
        mobile_id = _normalize_mobile_id(mobile)
        month_key = f"month_{month_number}"
        
        # Upsert: Save skill mapping for this user and month
        collection.update_one(
            {'_id': mobile_id},
            {
                '$set': {
                    f'months.{month_key}': skill_mapping,
                    'updated_at': datetime.utcnow()
                },
                '$setOnInsert': {
                    'created_at': datetime.utcnow()
                }
            },
            upsert=True
        )
        
        print(f"   💾 Saved skill-week mapping for user {mobile_id}, {month_key}")
        return True
        
    except Exception as e:
        print(f"   ❌ Error saving skill-week mapping: {e}")
        return False


def _analyze_roadmap_dashboard_for_skills(month_data, job_role=None, job_role_skills=None):
    """
    Analyze Roadmap_Dashboard month structure and extract skill-week mappings.
    
    Args:
        month_data: Month data from Roadmap_Dashboard
        job_role: User's selected job role (optional, for better matching)
        job_role_skills: List of exact skill names for the job role (optional)
    
    Roadmap_Dashboard structure:
    {
        "Skill Focus": "Microsoft Excel, Data Cleaning, Basic Data Analysis",
        "Learning Goals": ["...", "..."],
        "Daily Plan (2 hours/day)": [
            "Week 1: Excel formulas...",
            "Week 2: Data Cleaning...",
            "Week 3: Pivot Tables...",
            "Week 4: Charts and Reports..."
        ],
        "Mini Project": "...",
        "Expected Outcome": "..."
    }
    """
    try:
        perplexity_api_key = os.getenv('PERPLEXITY_API_KEY')
        if not perplexity_api_key:
            print("⚠️ Perplexity API key not available for skill mapping")
            return {}
        
        # Extract roadmap information
        skill_focus = month_data.get('Skill Focus', '')
        learning_goals = month_data.get('Learning Goals', [])
        daily_plan = month_data.get('Daily Plan (2 hours/day)', [])
        mini_project = month_data.get('Mini Project', '')
        expected_outcome = month_data.get('Expected Outcome', '')
        
        # Format for analysis
        goals_text = '\n'.join([f"- {goal}" for goal in learning_goals]) if isinstance(learning_goals, list) else str(learning_goals)
        weeks_text = '\n'.join(daily_plan) if isinstance(daily_plan, list) else str(daily_plan)
        
        roadmap_summary = f"""**Skill Focus:** {skill_focus}

**Learning Goals:**
{goals_text}

**Weekly Plan:**
{weeks_text}

**Mini Project:** {mini_project}

**Expected Outcome:** {expected_outcome}
"""
        
        print(f"\n🤖 Analyzing Roadmap_Dashboard month data for skill-week mapping...")
        print(f"   Skill Focus: {skill_focus}")
        print(f"   Weekly plan lines: {len(daily_plan)}")
        if job_role:
            print(f"   Job Role: {job_role}")
        if job_role_skills:
            print(f"   Target Skills: {job_role_skills}")
        
        # Build job role context
        job_role_context = ""
        if job_role_skills:
            skills_list = ', '.join([f'"{skill}"' for skill in job_role_skills])
            job_role_context = f"""
**CRITICAL: The user's job role requires these EXACT skills:**
{skills_list}

**YOU MUST:**
1. Map curriculum topics to these EXACT skill names (do not invent new names)
2. If curriculum teaches "Machine Learning Fundamentals", map it to "Machine Learning Models" (if that's in the list)
3. If curriculum teaches "Chatbots Basics", map it to "Chatbots" (if that's in the list)
4. Use ONLY the skill names from the list above - do not create variations
"""
        
        # Create prompt for Perplexity
        prompt = f"""You are an expert curriculum analyzer. Analyze this monthly learning roadmap and map curriculum content to the user's required job skills.

**Roadmap:**
{roadmap_summary}
{job_role_context}

**Task:** Map the curriculum weeks to the user's required job skills. For each skill, list ALL the weeks (1, 2, 3, or 4) where it's taught.

**Rules:**
1. **USE ONLY THE EXACT SKILL NAMES** from the "Target Skills" list provided above
2. Match curriculum topics to the closest job skill (e.g., "Machine Learning Fundamentals" → "Machine Learning Models")
3. Parse the "Daily Plan" to determine which weeks each skill appears in
4. Extract week numbers from text like "Week 1: ...", "Week 2: ...", etc.
5. If a skill spans multiple weeks, list ALL those weeks in the array
6. **A single week can contain MULTIPLE skills** - check each week for all relevant skills
7. Do NOT invent new skill names - only use names from the Target Skills list
8. If a curriculum topic doesn't match any Target Skills, skip it

**Example Input:**
Target Skills: "Python", "NumPy", "Pandas", "Machine Learning Models", "scikit-learn"
Weekly Plan: 
- Week 1: Python basics, NumPy arrays
- Week 2: Pandas DataFrames, Python functions
- Week 3: ML fundamentals with scikit-learn
- Week 4: Advanced ML models and scikit-learn

**Example Output:**
{{
  "Python": [1, 2],
  "NumPy": [1],
  "Pandas": [2],
  "Machine Learning Models": [3, 4],
  "scikit-learn": [3, 4]
}}

**Return only the JSON object, no markdown, no explanations.**"""

        headers = {
            'Authorization': f'Bearer {perplexity_api_key}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            'model': 'sonar',
            'messages': [
                {
                    'role': 'system',
                    'content': 'You are a curriculum analysis expert. Always respond with valid JSON only. Use EXACT skill names provided by the user.'
                },
                {
                    'role': 'user',
                    'content': prompt
                }
            ],
            'temperature': 0.2,
            'max_tokens': 1000
        }
        
        print("   🔄 Calling Perplexity AI for skill-week mapping...")
        response = requests.post(
            'https://api.perplexity.ai/chat/completions',
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"   ❌ Perplexity API error: {response.status_code}")
            try:
                error_detail = response.json()
                print(f"   Error detail: {error_detail}")
            except:
                print(f"   Response text: {response.text}")
            return {}
        
        ai_response = response.json()
        ai_content = ai_response['choices'][0]['message']['content']
        
        # Parse JSON response (remove markdown code blocks if present)
        ai_content_clean = ai_content.strip()
        if ai_content_clean.startswith('```'):
            lines = ai_content_clean.split('\n')
            ai_content_clean = '\n'.join([line for line in lines if not line.startswith('```')])
        
        skill_mapping = json.loads(ai_content_clean)
        
        print(f"   ✅ Skill-Week Mapping: {skill_mapping}")
        return skill_mapping
        
    except Exception as e:
        print(f"   ❌ Error analyzing Roadmap_Dashboard for skills: {str(e)}")
        import traceback
        traceback.print_exc()
        return {}


def _fallback_weekly_distribution(topics):
    """Distribute topics evenly across 4 weeks with default learning goals and roadmap"""
    topics_per_week = max(1, len(topics) // 4)
    
    weeks_data = {
        'week_1': {
            'topics': topics[0:topics_per_week],
            'learning_goal': 'Build foundational knowledge and core concepts',
            'roadmap': 'Focus on understanding fundamental principles and basic techniques. Practice with simple exercises and examples.'
        },
        'week_2': {
            'topics': topics[topics_per_week:topics_per_week*2],
            'learning_goal': 'Develop intermediate skills and practical understanding',
            'roadmap': 'Apply foundational concepts to real-world scenarios. Work on hands-on projects and practice problems.'
        },
        'week_3': {
            'topics': topics[topics_per_week*2:topics_per_week*3],
            'learning_goal': 'Apply advanced techniques and integrate concepts',
            'roadmap': 'Combine multiple concepts and techniques. Tackle complex problems and build comprehensive solutions.'
        },
        'week_4': {
            'topics': topics[topics_per_week*3:],
            'learning_goal': 'Master complex topics and real-world applications',
            'roadmap': 'Work on industry-level projects. Integrate all learned concepts and prepare for practical implementation.'
        }
    }
    
    return weeks_data


def _parse_weekly_json(ai_content, topics):
    """Parse weekly plan JSON from Perplexity response"""
    import json
    import re
    
    json_match = re.search(r'```json\s*(.*?)\s*```', ai_content, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        json_match = re.search(r'\{.*\}', ai_content, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
        else:
            return _fallback_weekly_distribution(topics)
    
    try:
        return json.loads(json_str)
    except:
        return _fallback_weekly_distribution(topics)


def _rank_courses_with_perplexity(topic, courses, api_key, context):
    """Rank courses for a topic as best + alternatives"""
    
    if len(courses) == 0:
        return {'best_course': None, 'other_courses': [], 'reasoning': ''}
    
    if len(courses) == 1:
        return {'best_course': courses[0], 'other_courses': [], 'reasoning': 'Only one course available'}
    
    # Format courses for Perplexity
    courses_list = "\n".join([
        f"{i+1}. {course.get('title', 'N/A')} - {course.get('provider', course.get('channel', 'N/A'))}"
        for i, course in enumerate(courses)
    ])
    
    prompt = f"""Select the BEST course for learning "{topic}" from these options:

**Context:** {context}

**Available Courses:**
{courses_list}

**Task:** Choose the single BEST course (most comprehensive, beginner-friendly) and list the rest as alternatives.

**Output Format (JSON):**
{{
    "best": 1,
    "alternatives": [2, 3, 4],
    "reason": "One-sentence why this is best"
}}

Return ONLY valid JSON with course numbers."""

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    payload = {
        'model': 'sonar',
        'messages': [
            {'role': 'system', 'content': 'You are a course evaluator. Always return valid JSON.'},
            {'role': 'user', 'content': prompt}
        ],
        'temperature': 0.2,
        'max_tokens': 300
    }
    
    try:
        response = requests.post(
            'https://api.perplexity.ai/chat/completions',
            headers=headers,
            json=payload,
            timeout=20
        )
        
        if response.status_code == 200:
            result = response.json()
            ai_content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
            
            import json
            import re
            
            json_match = re.search(r'```json\s*(.*?)\s*```', ai_content, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_match = re.search(r'\{.*\}', ai_content, re.DOTALL)
                json_str = json_match.group(0) if json_match else ai_content
            
            ranking = json.loads(json_str)
            
            best_idx = ranking.get('best', 1) - 1
            alt_indices = [i - 1 for i in ranking.get('alternatives', [])]
            
            return {
                'best_course': courses[best_idx] if 0 <= best_idx < len(courses) else courses[0],
                'other_courses': [courses[i] for i in alt_indices if 0 <= i < len(courses)],
                'reasoning': ranking.get('reason', '')
            }
    except:
        pass
    
    # Fallback: first as best, rest as alternatives
    return {
        'best_course': courses[0],
        'other_courses': courses[1:],
        'reasoning': 'Default ranking'
    }


# ===========================
# TEST QUESTIONS ENDPOINTS (In-Memory Storage Only - No Database)
# ===========================

# In-memory storage for SKILLS test questions (session-based, data lost on server restart)
# Used by: /api/generate-test, /api/get-test-questions, /api/submit-test-answers (for skills tests)
test_questions_storage = {}

# SEPARATE in-memory storage for WEEKLY test questions (no conflicts with skills tests)
# Used by: /api/weekly-test-generator, /api/submit-test-answers (for weekly tests)
weekly_test_storage = {}

# SEPARATE in-memory storage for MONTHLY test questions
# Used by: /api/monthly-test-fetcher, /api/submit-test-answers (for monthly tests)
monthly_test_storage = {}


@app.route('/api/check-quiz-test/<mobile>', methods=['GET'])
def check_quiz_test(mobile):
    """
    Check if test data exists in the quiz_test collection (n8n database)
    Returns True if test exists, False otherwise
    
    This endpoint is used by the frontend to check if a test already exists
    before triggering the webhook to generate a new one.
    """
    try:
        # Connect to n8n database
        mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI")
        if not mongo_uri:
            return jsonify({
                'success': False,
                'exists': False,
                'error': 'MongoDB URI not configured'
            }), 500
            
        client = MongoClient(mongo_uri)
        db = client[os.getenv("MONGODB_DB_N8N", "n8n")]
        collection = db[os.getenv("MONGODB_COLLECTION_QUIZ", "quiz_test")]
        
        # Try multiple common variants of mobile number
        candidates = []
        orig = mobile
        candidates.append(orig)
        # remove spaces
        candidates.append(orig.replace(' ', ''))
        # remove plus signs
        candidates.append(orig.replace('+', ''))
        # digits only
        digits = ''.join([c for c in orig if c.isdigit()])
        candidates.append(digits)
        
        # Add last 10 digits (phone number without country code)
        if len(digits) >= 10:
            last10 = digits[-10:]
            candidates.append(last10)
            candidates.append(f"+91 {last10}")
            candidates.append(f"+91{last10}")
            candidates.append(f"91{last10}")
            candidates.append(f"91 {last10}")
        
        # make unique while preserving order
        seen = set()
        uniq = []
        for c in candidates:
            if c not in seen:
                seen.add(c)
                uniq.append(c)

        # Check if any variant exists in the collection
        test_doc = None
        matched_variant = None
        for cand in uniq:
            test_doc = collection.find_one({"_id": cand})
            if test_doc:
                matched_variant = cand
                break

        if test_doc:
            print(f"✅ Quiz test exists in database for {mobile} (matched _id: {matched_variant})")
            return jsonify({
                'success': True,
                'exists': True,
                'testId': str(test_doc.get('_id')),
                'message': 'Test already exists in database'
            }), 200
        else:
            print(f"❌ No quiz test found in database for {mobile}")
            return jsonify({
                'success': True,
                'exists': False,
                'message': 'No test found in database'
            }), 200
        
    except Exception as e:
        print(f"❌ Error checking quiz_test collection: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'exists': False,
            'error': str(e)
        }), 500


@app.route('/api/generate-test', methods=['POST'])
def generate_test():
    """
    Trigger test generation by calling n8n webhook from backend
    This avoids CORS issues when frontend calls n8n directly
    
    Request body:
    {
        "mobile": "+91 9084113772",
        "skills": ["Python", "SQL"],
        "testType": "quick"
    }
    """
    try:
        data = request.get_json()
        
        mobile = data.get('mobile')
        skills = data.get('skills', [])
        test_type = data.get('testType', 'quick')
        
        if not mobile:
            return jsonify({
                'success': False,
                'error': 'Mobile number is required'
            }), 400
        
        if not skills or len(skills) == 0:
            return jsonify({
                'success': False,
                'error': 'At least one skill is required'
            }), 400
        
        print(f"\n{'='*60}")
        print(f"🎯 TRIGGERING TEST GENERATION")
        print(f"{'='*60}")
        print(f"📱 Mobile: {mobile}")
        print(f"📝 Skills: {', '.join(skills)}")
        print(f"📊 Test Type: {test_type}")
        print(f"{'='*60}\n")
        
        # Get n8n webhook URL from environment
        n8n_webhook_url = os.getenv('N8N_TEST_GENERATION_WEBHOOK')
        
        if not n8n_webhook_url:
            return jsonify({
                'success': False,
                'error': 'Test generation webhook not configured'
            }), 500
        
        # Call n8n webhook
        import requests
        
        print(f"📤 Calling n8n webhook: {n8n_webhook_url}")
        
        n8n_payload = {
            'mobile': mobile,
            'skills': skills,
            'testType': test_type
        }
        
        n8n_response = requests.post(
            n8n_webhook_url,
            json=n8n_payload,
            headers={'Content-Type': 'application/json'},
            timeout=30
        )

        # If n8n returns a non-200, include status and a short snippet of response text
        if n8n_response.status_code != 200:
            resp_text = n8n_response.text or ''
            snippet = resp_text[:1000]
            print(f"❌ n8n webhook failed: {n8n_response.status_code} - {snippet}")
            error_message = (
                f'n8n workflow not configured or returned error {n8n_response.status_code}. '
                'Please check the n8n workflow and ensure it returns HTTP 200.'
            )

            return jsonify({
                'success': False,
                'error': error_message,
                'n8n_status': n8n_response.status_code,
                'n8n_response_snippet': snippet
            }), 500
        
        print(f"✅ n8n webhook called successfully")
        
        # Wait a moment for n8n to process and send questions back
        time.sleep(2)
        
        # Check if test is now available in storage
        if mobile in test_questions_storage:
            test_data = test_questions_storage[mobile]
            print(f"✅ Test questions received and stored")
            
            return jsonify({
                'success': True,
                'message': 'Test generated successfully',
                'data': {
                    'testId': test_data['testId'],
                    'totalQuestions': test_data['totalQuestions'],
                    'skills': test_data.get('skills', [])
                }
            }), 200
        else:
            print(f"⚠️ Test generated but questions not received yet")
            return jsonify({
                'success': True,
                'message': 'Test generation initiated. Please check back in a moment.',
                'data': {
                    'mobile': mobile,
                    'status': 'processing'
                }
            }), 202
        
    except requests.exceptions.Timeout:
        print(f"❌ n8n webhook timeout")
        return jsonify({
            'success': False,
            'error': 'Test generation timed out. Please try again.'
        }), 504
    except Exception as e:
        print(f"❌ Error in generate-test: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/receive-test-questions', methods=['POST'])
def receive_test_questions():
    """
    Endpoint for n8n workflow to send test questions
    Stores questions in memory (RAM) only - NO DATABASE STORAGE
    
    n8n Webhook URL: http://localhost:5000/api/receive-test-questions
    
    Expected JSON from n8n:
    {
        "mobile": "+91 9084113772",
        "testType": "quick",
        "skills": ["Python", "SQL"],
        "questions": [
            {
                "question": "What is Python?",
                "options": ["A programming language", "A snake", "A framework", "A database"],
                "correctAnswer": 0,
                "skill": "Python",
                "difficulty": "easy"
            }
        ]
    }
    """
    try:
        data = request.get_json()
        
        # 🔍 DEBUG: Log the raw data received from n8n
        print(f"\n{'='*60}")
        print(f"🔍 DEBUG: RAW DATA RECEIVED FROM N8N")
        print(f"{'='*60}")
        print(f"Full payload: {json.dumps(data, indent=2)}")
        print(f"{'='*60}\n")
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No JSON data provided'
            }), 400
        
        # Extract required fields
        mobile = data.get('mobile')
        test_type = data.get('testType', 'quick')
        skills = data.get('skills', [])
        questions = data.get('questions', [])
        
        if not mobile:
            return jsonify({
                'success': False,
                'error': 'Mobile number is required'
            }), 400
        
        if not questions or len(questions) == 0:
            return jsonify({
                'success': False,
                'error': 'Questions array is required and must not be empty'
            }), 400
        
        # Validate questions structure
        for idx, q in enumerate(questions):
            if 'question' not in q or 'options' not in q or 'correctAnswer' not in q:
                return jsonify({
                    'success': False,
                    'error': f'Question at index {idx} is missing required fields (question, options, correctAnswer)'
                }), 400
        
        # Store questions in memory with timestamp
        test_id = f"{mobile}_{test_type}_{int(time.time())}"
        test_questions_storage[mobile] = {
            'testId': test_id,
            'mobile': mobile,
            'testType': test_type,
            'skills': skills,
            'questions': questions,
            'totalQuestions': len(questions),
            'createdAt': datetime.now().isoformat(),
            'status': 'pending'
        }
        
        print(f"\n{'='*60}")
        print(f"✅ TEST QUESTIONS RECEIVED (Stored in Memory)")
        print(f"{'='*60}")
        print(f"📱 Mobile: {mobile}")
        print(f"📝 Test Type: {test_type}")
        print(f"🎯 Skills: {', '.join(skills) if skills else 'N/A'}")
        print(f"❓ Total Questions: {len(questions)}")
        print(f"🔑 Test ID: {test_id}")
        print(f"💾 Storage: RAM (In-Memory) - NOT SAVED TO DATABASE")
        print(f"{'='*60}\n")
        
        return jsonify({
            'success': True,
            'message': 'Test questions received and stored in memory (not in database)',
            'data': {
                'testId': test_id,
                'mobile': mobile,
                'testType': test_type,
                'skills': skills,
                'totalQuestions': len(questions),
                'createdAt': test_questions_storage[mobile]['createdAt'],
                'storage': 'memory'
            }
        }), 200
        
    except Exception as e:
        print(f"❌ Error in receive-test-questions: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/get-weekly-test-questions/<mobile>', methods=['GET'])
def get_weekly_test_questions(mobile):
    """
    Get pending weekly test questions for a user.
    First checks memory, then tries to reload from MongoDB with any saved answers.
    Used by TestResults.js to get test data with user answers intact.
    """
    try:
        mobile = mobile.strip()
        
        # Check weekly_test_storage first
        if mobile in weekly_test_storage:
            test_data = weekly_test_storage[mobile]
            
            # If memory has no answers, try to load from MongoDB
            if not test_data.get('userAnswers'):
                try:
                    mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI")
                    if mongo_uri:
                        client = MongoClient(mongo_uri)
                        db = client[os.getenv("MONGODB_DB", "Placement_Ai")]
                        answers_collection = db["week_test_answers"]
                        
                        # Try to find saved answers with week number in _id
                        week_number = test_data.get('week', 1)
                        week_id = f"{mobile}_week_{week_number}"
                        week_id_no_space = f"{mobile.replace(' ', '')}_week_{week_number}"
                        
                        answers_doc = answers_collection.find_one({"_id": week_id})
                        if not answers_doc:
                            answers_doc = answers_collection.find_one({"_id": week_id_no_space})
                        # Fallback to old format for backward compatibility
                        if not answers_doc:
                            answers_doc = answers_collection.find_one({"_id": mobile})
                        if not answers_doc:
                            answers_doc = answers_collection.find_one({"_id": mobile.replace(' ', '')})
                        
                        if answers_doc and answers_doc.get('userAnswers'):
                            test_data['userAnswers'] = answers_doc.get('userAnswers', [])
                            print(f"📖 Loaded {len(test_data['userAnswers'])} saved answers from MongoDB")
                except Exception as db_err:
                    print(f"⚠️ Could not load answers from MongoDB: {str(db_err)}")
            
            # Don't send correct answers to frontend (security)
            questions_without_answers = []
            for q in test_data.get('questions', []):
                question_text = q.get('question') or q.get('question_text') or q.get('questionText') or ''
                question_copy = {
                    'question': question_text,
                    'options': q.get('options', []),
                    'skill': q.get('skill', q.get('topic', 'General')),
                    'difficulty': q.get('difficulty', 'medium')
                }
                questions_without_answers.append(question_copy)
            
            print(f"📖 Retrieving WEEKLY test questions from MEMORY for {mobile} (has {len(test_data.get('userAnswers', []))} answers)")
            
            return jsonify({
                'success': True,
                'data': {
                    'testId': test_data.get('testId'),
                    'testType': 'weekly',
                    'testTitle': test_data.get('testTitle', 'Weekly Test'),
                    'week': test_data.get('week'),
                    'month': test_data.get('month'),
                    'totalQuestions': test_data.get('totalQuestions', len(questions_without_answers)),
                    'questions': questions_without_answers,
                    'createdAt': test_data.get('createdAt'),
                    'status': test_data.get('status', 'pending'),
                    'storage': 'memory',
                    'answersCount': len(test_data.get('userAnswers', []))
                }
            }), 200
        
        # Not in memory - try to load from MongoDB
        print(f"⚠️ Weekly test not in memory for {mobile}, trying MongoDB...")
        try:
            mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI")
            if mongo_uri:
                client = MongoClient(mongo_uri)
                db = client[os.getenv("MONGODB_DB", "Placement_Ai")]
                
                # Load test from week_test collection
                test_collection = db["week_test"]
                test_doc = test_collection.find_one({"_id": mobile})
                if not test_doc:
                    test_doc = test_collection.find_one({"_id": mobile.replace(' ', '')})
                
                if test_doc:
                    # Extract questions - prioritize nested weekly_tests structure (new format)
                    questions = []
                    test_title = test_doc.get('test_title', 'Weekly Test')
                    week_number = test_doc.get('week', 1)
                    month_number = test_doc.get('month', 1)
                    
                    # Check nested weekly_tests array first (new structure - expected for all new users)
                    if 'weekly_tests' in test_doc and test_doc['weekly_tests']:
                        weekly_tests = test_doc['weekly_tests']
                        # Merge questions from ALL elements in the weekly_tests array
                        questions = []
                        for i, wt in enumerate(weekly_tests):
                            if isinstance(wt, dict):
                                wt_questions = wt.get('questions', [])
                                questions.extend(wt_questions)
                                # Try to get week/month from the first element if available
                                if i == 0:
                                    if 'week_number' in wt:
                                        week_number = wt['week_number']
                                    if 'month' in wt:
                                        month_number = wt['month']
                        print(f"✅ Found {len(questions)} questions from {len(weekly_tests)} weekly_tests elements (new format)")
                    # Fallback to top-level questions for backward compatibility (old structure)
                    elif 'questions' in test_doc and test_doc['questions']:
                        questions = test_doc['questions']
                        print(f"✅ Found {len(questions)} questions at top level (old format)")
                    
                    # Load saved answers with week number in _id
                    saved_answers = []
                    answers_collection = db["week_test_answers"]
                    week_id = f"{mobile}_week_{week_number}"
                    week_id_no_space = f"{mobile.replace(' ', '')}_week_{week_number}"
                    
                    answers_doc = answers_collection.find_one({"_id": week_id})
                    if not answers_doc:
                        answers_doc = answers_collection.find_one({"_id": week_id_no_space})
                    # Fallback to old format for backward compatibility
                    if not answers_doc:
                        answers_doc = answers_collection.find_one({"_id": mobile})
                    if not answers_doc:
                        answers_doc = answers_collection.find_one({"_id": mobile.replace(' ', '')})
                    
                    if answers_doc and answers_doc.get('userAnswers'):
                        saved_answers = answers_doc.get('userAnswers', [])
                    
                    # IMPORTANT: Preserve existing in-memory answers if more complete
                    existing_memory = weekly_test_storage.get(mobile, {})
                    existing_answers = existing_memory.get('userAnswers', [])
                    
                    # Use whichever source has more answers
                    if len(existing_answers) > len(saved_answers):
                        final_answers = existing_answers
                        print(f"🔄 Preserving {len(existing_answers)} in-memory answers (DB had {len(saved_answers)})")
                    else:
                        final_answers = saved_answers
                    
                    # Store in memory for future use (with merged answers)
                    weekly_test_storage[mobile] = {
                        'testId': str(test_doc.get('_id')),
                        'mobile': mobile,
                        'testType': 'weekly',
                        'testTitle': test_title,
                        'week': week_number,
                        'month': month_number,
                        'questions': questions,
                        'totalQuestions': len(questions),
                        'createdAt': test_doc.get('created_at'),
                        'status': 'pending',
                        'userAnswers': final_answers
                    }
                    
                    # Format questions for response
                    questions_without_answers = []
                    for q in questions:
                        question_text = q.get('question') or q.get('question_text') or q.get('questionText') or ''
                        question_copy = {
                            'question': question_text,
                            'options': q.get('options', []),
                            'skill': q.get('skill', q.get('topic', 'General')),
                            'difficulty': q.get('difficulty', 'medium')
                        }
                        questions_without_answers.append(question_copy)
                    
                    print(f"📖 Loaded weekly test from MongoDB for {mobile} (has {len(saved_answers)} answers)")
                    
                    return jsonify({
                        'success': True,
                        'data': {
                            'testId': str(test_doc.get('_id')),
                            'testType': 'weekly',
                            'testTitle': test_title,
                            'week': week_number,
                            'month': month_number,
                            'totalQuestions': len(questions_without_answers),
                            'questions': questions_without_answers,
                            'status': 'pending',
                            'storage': 'mongodb',
                            'answersCount': len(saved_answers)
                        }
                    }), 200
        except Exception as db_err:
            print(f"❌ Error loading from MongoDB: {str(db_err)}")
        
        return jsonify({
            'success': False,
            'message': 'No weekly test found'
        }), 404
        
    except Exception as e:
        print(f"❌ Error in get-weekly-test-questions: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/get-test-questions/<mobile>', methods=['GET'])
def get_test_questions(mobile):
    """
    Get pending test questions for a user (SKILLS TEST ONLY - not weekly test)
    First checks memory, then falls back to MongoDB (n8n database)
    """
    try:
        mobile = mobile.strip()
        
        # Skills Test endpoint - ONLY checks test_questions_storage (NOT weekly_test_storage)
        # Weekly tests have their own endpoint: /api/weekly-test-generator
        if mobile in test_questions_storage:
            test_data = test_questions_storage[mobile]
            
            # Don't send correct answers to frontend (security)
            questions_without_answers = []
            for q in test_data.get('questions', []):
                # support both legacy 'question' and new 'question_text' fields
                question_text = q.get('question') or q.get('question_text') or ''
                question_copy = {
                    'question': question_text,
                    'options': q.get('options', []),
                    'skill': q.get('skill', q.get('topic', 'General')),
                    'difficulty': q.get('difficulty', 'medium')
                }
                questions_without_answers.append(question_copy)
            
            print(f"📖 Retrieving SKILLS test questions from MEMORY for {mobile}")
            
            return jsonify({
                'success': True,
                'data': {
                    'testId': test_data['testId'],
                    'testType': test_data['testType'],
                    'skills': test_data.get('skills', []),
                    'totalQuestions': test_data['totalQuestions'],
                    'questions': questions_without_answers,
                    'createdAt': test_data.get('createdAt'),
                    'status': test_data.get('status', 'pending'),
                    'storage': 'memory'
                }
            }), 200
        
        # If not in memory, try MongoDB (n8n database - quiz_test collection)
        print(f"🔍 Skills test not in memory, checking quiz_test collection for {mobile}")
        
        # Connect to n8n database
        mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI")
        if not mongo_uri:
            print("❌ No MongoDB URI found in MONGO_URI or MONGODB_URI")
            return jsonify({
                'success': False,
                'message': 'No pending test found (MongoDB URI missing)'
            }), 404
            
        client = MongoClient(mongo_uri)
        db = client[os.getenv("MONGODB_DB_N8N", "n8n")]
        collection = db[os.getenv("MONGODB_COLLECTION_QUIZ", "quiz_test")]
        
        # Find test by mobile number (stored as _id)
        # Try multiple common variants to be tolerant of formatting differences
        candidates = []
        orig = mobile
        candidates.append(orig)
        # remove spaces
        candidates.append(orig.replace(' ', ''))
        # remove plus signs
        candidates.append(orig.replace('+', ''))
        # digits only
        digits = ''.join([c for c in orig if c.isdigit()])
        candidates.append(digits)
        
        # Add last 10 digits (phone number without country code) - IMPORTANT!
        if len(digits) >= 10:
            last10 = digits[-10:]
            candidates.append(last10)
            candidates.append(f"+91 {last10}")
            candidates.append(f"+91{last10}")
            candidates.append(f"91{last10}")
            candidates.append(f"91 {last10}")
        
        # make unique while preserving order
        seen = set()
        uniq = []
        for c in candidates:
            if c not in seen:
                seen.add(c)
                uniq.append(c)

        test_doc = None
        matched_variant = None
        for cand in uniq:
            test_doc = collection.find_one({"_id": cand})
            if test_doc:
                matched_variant = cand
                break

        if not test_doc:
            print(f"❌ No test found in MongoDB for {mobile} (tried variants: {uniq})")
            return jsonify({
                'success': False,
                'message': 'No pending test found',
                'error_type': 'test_not_ready',
                'hint': 'Test may still be generating. Please wait...'
            }), 404

        print(f"✅ Found test in quiz_test collection for {mobile} (matched _id: {matched_variant})")
        
        # Format questions (remove correct answers for security)
        questions_without_answers = []
        for q in test_doc.get('questions', []):
            # tolerate multiple possible field names used historically
            question_text = q.get('question') or q.get('question_text') or q.get('questionText') or ''
            options = q.get('options') or q.get('choices') or []
            skill = q.get('skill') or q.get('topic') or q.get('subject') or 'General'
            difficulty = q.get('difficulty', 'medium')
            marks = q.get('marks', q.get('score', 5))
            qnum = q.get('question_number') or q.get('questionNumber') or q.get('qno')

            question_copy = {
                'question': question_text,
                'options': options,
                'skill': skill,
                'difficulty': difficulty,
                'marks': marks,
                'questionNumber': qnum
            }
            questions_without_answers.append(question_copy)
        
        # Store in memory for faster subsequent access
        test_questions_storage[mobile] = {
            'testId': str(test_doc.get('_id')),
            'mobile': mobile,
            'testType': test_doc.get('testType', 'quick'),
            'skills': test_doc.get('skills', []),
            'questions': test_doc.get('questions', []),  # Keep full questions with answers in memory
            'totalQuestions': len(test_doc.get('questions', [])),
            'createdAt': test_doc.get('createdAt'),
            'status': 'pending',
            'userAnswers': []
        }
        
        return jsonify({
            'success': True,
            'data': {
                'testId': str(test_doc.get('_id')),
                'testType': test_doc.get('testType', 'quick'),
                'skills': test_doc.get('skills', []),
                'totalQuestions': len(questions_without_answers),
                'questions': questions_without_answers,
                'status': 'pending',
                'storage': 'quiz_test'
            }
        }), 200
        
    except Exception as e:
        print(f"❌ Error in get-test-questions: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'Error retrieving test: {str(e)}'
        }), 500


@app.route('/api/weekly-test-info/<mobile>', methods=['GET'])
def get_weekly_test_info(mobile):
    """
    Get current week and month info for a user's weekly test
    Returns the week and month number from the week_test collection
    """
    try:
        if not mobile:
            return jsonify({
                'success': False,
                'message': 'Mobile number is required'
            }), 400
        
        mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI")
        client = MongoClient(mongo_uri)
        db = client[os.getenv("MONGODB_DB", "Placement_Ai")]
        collection = db["week_test"]
        
        # Try multiple mobile number format variants
        digits = ''.join([c for c in mobile if c.isdigit()])
        candidates = [mobile, mobile.replace(' ', ''), f"+91 {digits[-10:]}", f"+91{digits[-10:]}", digits[-10:]]
        
        test_doc = None
        for cand in candidates:
            test_doc = collection.find_one({"_id": cand})
            if test_doc:
                break
            test_doc = collection.find_one({"mobile": cand})
            if test_doc:
                break
        
        if test_doc:
            return jsonify({
                'success': True,
                'data': {
                    'week': test_doc.get('week', 1),
                    'month': test_doc.get('month', 1),
                    'test_title': test_doc.get('test_title', f"Week {test_doc.get('week', 1)} Test"),
                    'has_test': True
                }
            }), 200
        else:
            # No test found, return default week 1
            return jsonify({
                'success': True,
                'data': {
                    'week': 1,
                    'month': 1,
                    'test_title': 'Week 1 Test',
                    'has_test': False
                }
            }), 200
            
    except Exception as e:
        print(f"❌ Error in weekly-test-info: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/weekly-test-generator', methods=['POST'])
def weekly_test_generator():
    """
    Get weekly test from week_test collection in Placement_Ai database
    ONLY fetches existing test - does NOT trigger n8n webhook
    
    Request body:
    {
        "mobile": "+91 8864862270"
    }
    
    Response:
    - If test exists: returns test data with status 'ready'
    - If test not found: returns error message
    """
    try:
        data = request.get_json()
        
        mobile = data.get('mobile')
        
        if not mobile:
            return jsonify({
                'success': False,
                'error': 'Mobile number is required'
            }), 400
        
        mobile = mobile.strip()
        
        print(f"\n{'='*60}")
        print(f"📱 WEEKLY TEST FETCH REQUEST")
        print(f"{'='*60}")
        print(f"Mobile: {mobile}")
        print(f"{'='*60}\n")
        
        # Connect to Placement_Ai database
        mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI")
        if not mongo_uri:
            print("❌ No MongoDB URI found")
            return jsonify({
                'success': False,
                'error': 'Database connection not configured'
            }), 500
            
        client = MongoClient(mongo_uri)
        db = client[os.getenv("MONGODB_DB", "Placement_Ai")]
        collection = db["week_test"]
        
        # Try multiple mobile number format variants
        candidates = []
        orig = mobile
        candidates.append(orig)
        candidates.append(orig.replace(' ', ''))
        candidates.append(orig.replace('+', ''))
        candidates.append(''.join([c for c in orig if c.isdigit()]))
        
        digits = ''.join([c for c in orig if c.isdigit()])
        if len(digits) == 10:
            candidates.append(f"+91 {digits}")
            candidates.append(f"+91{digits}")
        
        # Remove duplicates while preserving order
        seen = set()
        uniq = []
        for c in candidates:
            if c not in seen:
                seen.add(c)
                uniq.append(c)

        test_doc = None
        matched_variant = None
        for cand in uniq:
            test_doc = collection.find_one({"_id": cand})
            if test_doc:
                matched_variant = cand
                break

        if not test_doc:
            # TEST NOT FOUND - Return error (no webhook trigger)
            print(f"⚠️ No weekly test found for {mobile}")
            return jsonify({
                'success': False,
                'error': 'No weekly test found. Please generate a test first using "Generate Weekly Test" button.',
                'error_type': 'test_not_found'
            }), 404

        print(f"✅ Found weekly test in week_test collection for {mobile} (matched _id: {matched_variant})")
        
        # Extract questions - prioritize nested weekly_tests structure (new format)
        questions = []
        test_title = test_doc.get('test_title', 'Weekly Test')
        week_number = test_doc.get('week', 1)
        month_number = test_doc.get('month', 1)
        
        # Check nested weekly_tests array first (new structure - expected for all new users)
        if 'weekly_tests' in test_doc and test_doc['weekly_tests']:
            weekly_tests = test_doc['weekly_tests']
            # Merge questions from ALL elements in the weekly_tests array
            questions = []
            for i, wt in enumerate(weekly_tests):
                if isinstance(wt, dict):
                    wt_questions = wt.get('questions', [])
                    questions.extend(wt_questions)
                    # Try to get week/month from the first element if available
                    if i == 0:
                        if 'week_number' in wt:
                            week_number = wt['week_number']
                        if 'month' in wt:
                            month_number = wt['month']
            print(f"✅ Found {len(questions)} questions from {len(weekly_tests)} weekly_tests elements (new format)")
        # Fallback to top-level questions for backward compatibility (old structure)
        elif 'questions' in test_doc and test_doc['questions']:
            questions = test_doc['questions']
            print(f"✅ Found {len(questions)} questions at top level (old format)")
        
        # Format questions (remove correct answers for security)
        questions_without_answers = []
        for q in questions:
            question_text = q.get('question') or q.get('question_text') or q.get('questionText') or ''
            options = q.get('options') or q.get('choices') or []
            skill = q.get('skill') or q.get('topic') or q.get('subject') or 'General'
            difficulty = q.get('difficulty', 'medium')
            marks = q.get('marks', q.get('score', 5))
            qnum = q.get('question_number') or q.get('questionNumber') or q.get('qno')

            question_copy = {
                'question': question_text,
                'options': options,
                'skill': skill,
                'difficulty': difficulty,
                'marks': marks,
                'questionNumber': qnum
            }
            questions_without_answers.append(question_copy)
        
        # Store in SEPARATE weekly test memory (not test_questions_storage)
        # This prevents conflicts with skills tests
        weekly_test_storage[mobile] = {
            'testId': str(test_doc.get('_id')),
            'mobile': mobile,
            'testType': 'weekly',
            'testTitle': test_title,
            'week': week_number,
            'month': month_number,
            'questions': questions,
            'totalQuestions': len(questions),
            'createdAt': test_doc.get('created_at'),
            'status': 'pending',
            'userAnswers': []
        }
        
        return jsonify({
            'success': True,
            'status': 'ready',
            'message': 'Weekly test loaded successfully',
            'data': {
                'testId': str(test_doc.get('_id')),
                'testType': 'weekly',
                'testTitle': test_title,
                'week': week_number,
                'month': month_number,
                'totalQuestions': len(questions_without_answers),
                'questions': questions_without_answers,
                'status': 'pending',
                'storage': 'week_test'
            }
        }), 200
        
    except Exception as e:
        print(f"❌ Error in weekly-test-generator: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/monthly-test-fetcher', methods=['POST'])
def monthly_test_fetcher():
    """
    Get monthly test from monthly_test collection in Placement_Ai database
    ONLY fetches existing test - does NOT trigger n8n webhook
    
    Request body:
    {
        "mobile": "+91 8864862270",
        "month": 1
    }
    
    Response:
    - If test exists: returns test data with status 'ready'
    - If test not found: returns error message
    """
    try:
        data = request.get_json()
        
        mobile = data.get('mobile')
        month = data.get('month', 1)
        
        if not mobile:
            return jsonify({
                'success': False,
                'error': 'Mobile number is required'
            }), 400
        
        mobile = mobile.strip()
        
        print(f"\n{'='*60}")
        print(f"📱 MONTHLY TEST FETCH REQUEST")
        print(f"{'='*60}")
        print(f"Mobile: {mobile}")
        print(f"Month: {month}")
        print(f"{'='*60}\n")
        
        # Connect to Placement_Ai database
        mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI")
        if not mongo_uri:
            print("❌ No MongoDB URI found")
            return jsonify({
                'success': False,
                'error': 'Database connection not configured'
            }), 500
            
        client = MongoClient(mongo_uri)
        db = client[os.getenv("MONGODB_DB", "Placement_Ai")]
        collection = db["monthly_test"]
        
        # Try to find test by mobile and month (month can be string or int)
        test_doc = collection.find_one({"mobile": mobile, "month": {"$in": [month, str(month)]}})
        
        if not test_doc:
            # Try with different mobile formats
            candidates = []
            orig = mobile
            candidates.append(orig)
            candidates.append(orig.replace(' ', ''))
            candidates.append(orig.replace('+', ''))
            candidates.append(''.join([c for c in orig if c.isdigit()]))
            
            digits = ''.join([c for c in orig if c.isdigit()])
            if len(digits) == 10:
                candidates.append(f"+91 {digits}")
                candidates.append(f"+91{digits}")
            
            # Remove duplicates
            seen = set()
            uniq = []
            for c in candidates:
                if c not in seen:
                    seen.add(c)
                    uniq.append(c)
            
            for cand in uniq:
                test_doc = collection.find_one({"mobile": cand, "month": {"$in": [month, str(month)]}})
                if test_doc:
                    mobile = cand
                    break

        if not test_doc:
            print(f"⚠️ No monthly test found for {mobile}, Month {month}")
            return jsonify({
                'success': False,
                'error': f'No monthly test found for Month {month}. Please generate the test first.',
                'error_type': 'test_not_found'
            }), 404

        # Check if test is being regenerated (retake in progress)
        test_status = test_doc.get('status', '')
        if test_status == 'regenerating':
            print(f"⏰ Test is being regenerated for {mobile}, Month {month}")
            return jsonify({
                'success': False,
                'error': f'Monthly test for Month {month} is being regenerated. Please wait for the countdown timer to complete.',
                'error_type': 'test_regenerating',
                'status': 'regenerating'
            }), 400

        print(f"✅ Found monthly test for {mobile}, Month {month}")
        
        # Check if user has reached maximum attempts (3)
        result_collection = db["monthly_test_result"]
        # Try new format first (mobile as _id)
        existing_result = result_collection.find_one({'_id': mobile, 'month': month})
        # Fallback to old format
        if not existing_result:
            result_id = f"{mobile}_month_{month}"
            existing_result = result_collection.find_one({'_id': result_id})
        
        if existing_result:
            test_attempt = existing_result.get('testAttempt', 0)
            if test_attempt >= 3:
                print(f"⚠️ User has already taken 3 attempts for Month {month}")
                return jsonify({
                    'success': False,
                    'error': 'You have reached the maximum number of attempts (3) for this monthly test.',
                    'error_type': 'max_attempts_reached',
                    'attempts_taken': test_attempt
                }), 400
        
        # Collect all questions from all weeks
        all_questions = []
        week_keys = ['week1', 'week2', 'week3', 'week4']
        
        for week_key in week_keys:
            week_data = test_doc.get(week_key, {})
            questions = week_data.get('questions', [])
            
            for q in questions:
                question_text = q.get('question', '')
                options = q.get('options', {})
                difficulty = q.get('difficulty', 'medium')
                marks = q.get('marks', 1.5)
                topic = q.get('topic', week_data.get('topic', ''))
                
                # Convert options dict to array format
                options_array = [
                    options.get('A', ''),
                    options.get('B', ''),
                    options.get('C', ''),
                    options.get('D', '')
                ]
                
                question_copy = {
                    'question': question_text,
                    'options': options_array,
                    'skill': topic,
                    'difficulty': difficulty,
                    'marks': marks
                }
                all_questions.append(question_copy)
        
        # Store in monthly test memory
        monthly_test_storage[mobile] = {
            'testId': str(test_doc.get('_id')),
            'mobile': mobile,
            'testType': 'monthly',
            'testTitle': test_doc.get('test_title', f'Month {month} Test'),
            'month': test_doc.get('month', month),
            'questions': test_doc,  # Store full doc for answer checking
            'totalQuestions': len(all_questions),
            'createdAt': test_doc.get('generated_at'),
            'status': 'pending',
            'userAnswers': []
        }
        
        return jsonify({
            'success': True,
            'status': 'ready',
            'message': 'Monthly test loaded successfully',
            'data': {
                'testId': str(test_doc.get('_id')),
                'testType': 'monthly',
                'testTitle': test_doc.get('test_title', f'Month {month} Test'),
                'month': test_doc.get('month', month),
                'totalQuestions': len(all_questions),
                'questions': all_questions,
                'status': 'pending'
            }
        }), 200
        
    except Exception as e:
        print(f"❌ Error in monthly-test-fetcher: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/submit-monthly-test', methods=['POST'])
def submit_monthly_test():
    """
    Submit monthly test answers and calculate score
    
    Request body:
    {
        "mobile": "+91 8864862270",
        "month": 1,
        "answers": [0, 1, 2, 3, ...]  // Array of selected option indices
    }
    
    Response:
    {
        "success": true,
        "score": {
            "totalQuestions": 80,
            "correctAnswers": 65,
            "wrongAnswers": 15,
            "totalMarks": 140,
            "scoredMarks": 112.5,
            "percentage": 80.36,
            "details": [...]
        }
    }
    """
    try:
        data = request.get_json()
        
        mobile = data.get('mobile')
        month = data.get('month', 1)
        user_answers = data.get('answers', [])
        
        if not mobile:
            return jsonify({
                'success': False,
                'error': 'Mobile number is required'
            }), 400
        
        if not user_answers:
            return jsonify({
                'success': False,
                'error': 'Answers are required'
            }), 400
        
        mobile = mobile.strip()
        
        print(f"\n{'='*60}")
        print(f"📝 MONTHLY TEST SUBMISSION")
        print(f"{'='*60}")
        print(f"Mobile: {mobile}")
        print(f"Month: {month}")
        print(f"Answers Count: {len(user_answers)}")
        print(f"{'='*60}\n")
        
        # Connect to MongoDB
        mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI")
        if not mongo_uri:
            return jsonify({
                'success': False,
                'error': 'Database connection not configured'
            }), 500
            
        client = MongoClient(mongo_uri)
        db = client[os.getenv("MONGODB_DB", "Placement_Ai")]
        collection = db["monthly_test"]
        
        # Find test document
        test_doc = collection.find_one({"mobile": mobile, "month": {"$in": [month, str(month)]}})
        
        if not test_doc:
            # Try with different mobile formats
            candidates = []
            orig = mobile
            candidates.append(orig)
            candidates.append(orig.replace(' ', ''))
            candidates.append(orig.replace('+', ''))
            candidates.append(''.join([c for c in orig if c.isdigit()]))
            
            digits = ''.join([c for c in orig if c.isdigit()])
            if len(digits) == 10:
                candidates.append(f"+91 {digits}")
                candidates.append(f"+91{digits}")
            
            seen = set()
            uniq = []
            for c in candidates:
                if c not in seen:
                    seen.add(c)
                    uniq.append(c)
            
            for cand in uniq:
                test_doc = collection.find_one({"mobile": cand, "month": {"$in": [month, str(month)]}})
                if test_doc:
                    mobile = cand
                    break

        if not test_doc:
            return jsonify({
                'success': False,
                'error': f'No monthly test found for Month {month}'
            }), 404

        # Collect all questions with correct answers
        all_questions = []
        week_keys = ['week1', 'week2', 'week3', 'week4']
        
        for week_key in week_keys:
            week_data = test_doc.get(week_key, {})
            questions = week_data.get('questions', [])
            
            for q in questions:
                all_questions.append({
                    'question': q.get('question', ''),
                    'correctAnswer': q.get('correctAnswer', ''),
                    'difficulty': q.get('difficulty', 'medium'),
                    'marks': q.get('marks', 1.5),
                    'topic': q.get('topic', week_data.get('topic', '')),
                    'explanation': q.get('explanation', ''),
                    'options': q.get('options', {})
                })
        
        # Calculate score (same structure as week_test_result)
        total_questions = len(all_questions)
        correct_count = 0
        total_score = 0
        max_possible_score = 0
        detailed_results = []
        skill_wise_score = {}
        
        option_map = {'A': 0, 'B': 1, 'C': 2, 'D': 3}
        
        for i, question in enumerate(all_questions):
            user_answer_index = user_answers[i] if i < len(user_answers) else None
            correct_answer_letter = question['correctAnswer']
            correct_answer_index = option_map.get(correct_answer_letter, -1)
            
            # Get skill/topic for skill-wise tracking
            skill = question.get('topic', 'General') or 'General'
            
            # Get difficulty and marks
            difficulty = question.get('difficulty', 'medium').lower()
            marks_for_question = question.get('marks', 1.5)
            max_possible_score += marks_for_question
            
            is_correct = user_answer_index == correct_answer_index
            marks_earned = marks_for_question if is_correct else 0
            total_score += marks_earned
            
            if is_correct:
                correct_count += 1
            
            # Track skill-wise performance (same as week_test_result)
            if skill not in skill_wise_score:
                skill_wise_score[skill] = {'correct': 0, 'total': 0, 'score': 0, 'maxScore': 0}
            skill_wise_score[skill]['total'] += 1
            skill_wise_score[skill]['maxScore'] += marks_for_question
            if is_correct:
                skill_wise_score[skill]['correct'] += 1
                skill_wise_score[skill]['score'] += marks_for_question
            
            # Convert options dict to array format (same as week_test_result)
            options_dict = question.get('options', {})
            if isinstance(options_dict, dict):
                options_array = [
                    options_dict.get('A', ''),
                    options_dict.get('B', ''),
                    options_dict.get('C', ''),
                    options_dict.get('D', '')
                ]
                # Keep the dict format for frontend compatibility
                options_for_frontend = options_dict
            else:
                options_array = options_dict if isinstance(options_dict, list) else []
                # Convert array to dict for frontend
                options_for_frontend = {
                    'A': options_array[0] if len(options_array) > 0 else '',
                    'B': options_array[1] if len(options_array) > 1 else '',
                    'C': options_array[2] if len(options_array) > 2 else '',
                    'D': options_array[3] if len(options_array) > 3 else ''
                }
            
            # Get user answer text
            user_answer_text = None
            if user_answer_index is not None and 0 <= user_answer_index < len(options_array):
                user_answer_text = options_array[user_answer_index]
            
            # Get correct answer text
            correct_answer_text = correct_answer_letter
            if 0 <= correct_answer_index < len(options_array):
                correct_answer_text = options_array[correct_answer_index]
            
            # Format detailedResults same as week_test_result
            detailed_results.append({
                'questionNumber': i + 1,  # Added for frontend compatibility
                'question': question['question'],
                'skill': skill,
                'difficulty': difficulty,
                'marks': marks_for_question,
                'marksEarned': marks_earned,
                'scoredMarks': marks_earned,  # Added for frontend compatibility
                'userAnswer': user_answer_index,  # Changed to index for frontend compatibility
                'userAnswerText': user_answer_text,  # Keep text version for display
                'correctAnswer': correct_answer_text,
                'correctAnswerLetter': correct_answer_letter,  # Added for frontend expanded view
                'isCorrect': is_correct,
                'options': options_for_frontend,  # Changed to dict format for frontend (detail.options['A'])
                'optionsArray': options_array,  # Keep array format if needed
                'explanation': question.get('explanation', '')  # Added for frontend expanded view
            })
        
        # Calculate percentage based on weighted score
        score_percentage = (total_score / max_possible_score * 100) if max_possible_score > 0 else 0
        
        # Calculate skill-wise percentages (same as week_test_result)
        skill_performance = {}
        for skill, scores in skill_wise_score.items():
            skill_performance[skill] = {
                'correct': scores['correct'],
                'total': scores['total'],
                'score': round(scores['score'], 2),
                'maxScore': round(scores['maxScore'], 2),
                'percentage': round((scores['score'] / scores['maxScore']) * 100, 2) if scores['maxScore'] > 0 else 0
            }
        
        # Result object (same structure as week_test_result)
        result = {
            'totalQuestions': total_questions,
            'correctAnswers': correct_count,
            'incorrectAnswers': total_questions - correct_count,
            'wrongAnswers': total_questions - correct_count,  # Added for frontend compatibility
            'totalScore': round(total_score, 2),
            'scoredMarks': round(total_score, 2),  # Added for frontend compatibility
            'maxPossibleScore': round(max_possible_score, 2),
            'totalMarks': round(max_possible_score, 2),  # Added for frontend compatibility
            'scorePercentage': round(score_percentage, 2),
            'percentage': round(score_percentage, 2),  # Added for frontend compatibility
            'passed': score_percentage >= 50,  # 50% pass threshold for monthly
            'skillPerformance': skill_performance,
            'detailedResults': detailed_results,
            'details': detailed_results  # Added for frontend compatibility (View Detailed Results)
        }
        
        print(f"✅ Score calculated: {total_score}/{max_possible_score} ({score_percentage:.2f}%)")
        
        # Save result to monthly_test_result collection
        try:
            result_collection = db["monthly_test_result"]
            
            # Use mobile as _id (same structure as week_test_result)
            result_id = mobile
            
            # Get test_number from monthly_test document
            test_number = test_doc.get('test_number', 1)
            print(f"📋 Retrieved test_number from monthly_test: {test_number}")
            
            # Get existing result to determine test attempt number
            # Try new format first
            existing_result = result_collection.find_one({'_id': result_id, 'month': month})
            # Fallback to old format
            if not existing_result:
                old_result_id = f"{mobile}_month_{month}"
                existing_result = result_collection.find_one({'_id': old_result_id})
            
            test_attempt = 1  # Default to first attempt
            
            if existing_result:
                # If result exists, increment attempt number
                test_attempt = existing_result.get('testAttempt', 1) + 1
                # Cap at 3 attempts maximum
                if test_attempt > 3:
                    test_attempt = 3
            
            result_document = {
                'testId': mobile,  # Same as week_test_result
                'mobile': mobile,
                'month': month,
                'test_number': test_number,  # Get test_number from monthly_test
                'testTitle': test_doc.get('test_title', f'Month {month} Test'),
                'testType': 'monthly',
                'totalQuestions': total_questions,
                'correctAnswers': correct_count,
                'incorrectAnswers': total_questions - correct_count,
                'totalScore': round(total_score, 2),
                'maxPossibleScore': round(max_possible_score, 2),
                'scorePercentage': round(score_percentage, 2),
                'passed': score_percentage >= 50,  # 50% pass threshold for monthly
                'skillPerformance': skill_performance,
                'detailedResults': detailed_results,
                'completedAt': datetime.now().isoformat(),
                'savedAt': datetime.now().isoformat(),
                'testAttempt': test_attempt  # Track attempt number (1, 2, or 3)
            }
            
            # Use update_one with upsert to replace if exists (mobile as _id)
            result_collection.update_one(
                {'_id': result_id},
                {
                    '$set': result_document,
                    '$setOnInsert': {'createdAt': datetime.now().isoformat()}
                },
                upsert=True
            )
            
            print(f"✅ Result saved to monthly_test_result collection with _id: {result_id}")
            print(f"📊 Test Attempt Number: {test_attempt}")
            print(f"📋 Test Number stored: {test_number}")
            print(f"📄 Document saved with fields: {list(result_document.keys())}")
            
            # Trigger N8N Monthly Analysis Webhook
            try:
                n8n_analysis_webhook = os.getenv('N8N_MONTHLY_ANALYSIS_WEBHOOK')
                
                if n8n_analysis_webhook:
                    import requests
                    analysis_payload = {
                        'mobile': mobile,
                        'month': month,
                        'test_number': test_attempt
                    }
                    
                    print(f"\n{'='*60}")
                    print(f"🔔 TRIGGERING MONTHLY ANALYSIS WEBHOOK")
                    print(f"{'='*60}")
                    print(f"Mobile: {mobile}")
                    print(f"Month: {month}")
                    print(f"Test Number: {test_attempt}")
                    print(f"{'='*60}\n")
                    
                    webhook_response = requests.post(
                        n8n_analysis_webhook,
                        json=analysis_payload,
                        headers={'Content-Type': 'application/json'},
                        timeout=10
                    )
                    
                    if webhook_response.status_code == 200:
                        print(f"✅ Monthly analysis webhook triggered successfully")
                    else:
                        print(f"⚠️ Analysis webhook returned status {webhook_response.status_code}")
                else:
                    print(f"⚠️ N8N_MONTHLY_ANALYSIS_WEBHOOK not configured")
                    
            except Exception as webhook_error:
                print(f"⚠️ Failed to trigger analysis webhook: {str(webhook_error)}")
                # Don't fail the submission if webhook fails
            
        except Exception as save_error:
            print(f"⚠️ Warning: Failed to save result to database: {str(save_error)}")
            # Don't fail the request if saving fails
        
        return jsonify({
            'success': True,
            'score': result
        }), 200
        
    except Exception as e:
        print(f"❌ Error in submit-monthly-test: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/submit-test-answers', methods=['POST'])
def submit_test_answers():
    """
    Submit test answers and get immediate score calculation
    
    Expected JSON:
    {
        "mobile": "+91 9084113772",
        "testId": "test_123",
        "answers": [0, 2, 1, 3, ...]
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No JSON data provided'
            }), 400
        
        mobile = data.get('mobile')
        test_id = data.get('testId')
        user_answers = data.get('answers', [])
        
        if not mobile or not test_id:
            return jsonify({
                'success': False,
                'error': 'Mobile and testId are required'
            }), 400
        
        # Get test from memory - check BOTH storages based on testType
        # First check weekly_test_storage, then test_questions_storage
        test_data = None
        if mobile in weekly_test_storage:
            test_data = weekly_test_storage[mobile]
            print(f"📖 Found test in WEEKLY storage for {mobile}")
        elif mobile in test_questions_storage:
            test_data = test_questions_storage[mobile]
            print(f"📖 Found test in SKILLS storage for {mobile}")
        
        if not test_data:
            return jsonify({
                'success': False,
                'error': 'Test not found or expired'
            }), 404
        
        questions = test_data['questions']

        # If caller did not provide answers array (possible when using single-question submits),
        # fall back to answers collected in-memory from per-question submissions.
        if (not user_answers) and test_data.get('userAnswers'):
            # Build a list aligned with question indices
            stored = test_data.get('userAnswers', [])
            ua_by_index = {entry.get('questionIndex'): entry.get('userAnswer') for entry in stored}
            user_answers = [ua_by_index.get(i) for i in range(len(questions))]
        
        # Calculate score with weighted marks based on difficulty
        correct_count = 0
        total_score = 0  # Weighted score
        max_possible_score = 0  # Maximum possible weighted score
        total_questions = len(questions)
        detailed_results = []
        skill_wise_score = {}
        
        # Marks distribution by difficulty
        difficulty_marks = {
            'easy': 1.0,
            'medium': 1.5,
            'hard': 2.0
        }
        
        # Robust comparison helper (support snake_case and camelCase, index or text answers)
        def normalize_text(val):
            try:
                s = str(val)
            except Exception:
                s = ''
            s = re.sub(r'<[^>]*>', '', s)
            s = ' '.join(s.split())
            return s.strip().lower()

        for idx, question in enumerate(questions):
            user_answer = user_answers[idx] if idx < len(user_answers) else None
            # Support both correctAnswer and correct_answer
            correct_answer = (
                question.get('correctAnswer')
                if question.get('correctAnswer') is not None
                else question.get('correct_answer')
            )

            options = question.get('options', []) or []

            # Pre-normalize
            normalized_options = [normalize_text(o) for o in options]
            normalized_correct = normalize_text(correct_answer)

            # Try parse ints but only treat as index when within options range
            try:
                ua_int_candidate = int(user_answer) if (isinstance(user_answer, (int, str)) and str(user_answer).lstrip().rstrip().lstrip('+').isdigit()) else None
            except Exception:
                ua_int_candidate = None

            try:
                ca_int_candidate = int(correct_answer) if (isinstance(correct_answer, (int, str)) and str(correct_answer).lstrip().rstrip().lstrip('+').isdigit()) else None
            except Exception:
                ca_int_candidate = None

            ua_is_index = (ua_int_candidate is not None) and (0 <= ua_int_candidate < len(options))
            ca_is_index = (ca_int_candidate is not None) and (0 <= ca_int_candidate < len(options))

            is_correct = False
            if ua_is_index and ca_is_index:
                is_correct = (ua_int_candidate == ca_int_candidate)
            elif ua_is_index and not ca_is_index:
                try:
                    is_correct = normalized_options[ua_int_candidate] == normalized_correct
                except Exception:
                    is_correct = False
            elif not ua_is_index and ca_is_index:
                try:
                    is_correct = normalize_text(user_answer) == normalized_options[ca_int_candidate]
                except Exception:
                    is_correct = False
            else:
                # Fallback: both appear to be text; compare normalized strings
                # Special handling: if correct_answer is a single letter (A, B, C, D) and user_answer starts with that letter
                # Example: correct_answer="A", user_answer="A) =" should match
                try:
                    normalized_user = normalize_text(user_answer)
                    
                    # Check if correct_answer is a single letter (A-Z) and user answer starts with it
                    if len(str(correct_answer).strip()) == 1 and str(correct_answer).strip().upper() in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
                        letter = str(correct_answer).strip().upper()
                        # Check if user answer starts with "A)", "a)", etc.
                        if normalized_user.startswith(letter.lower() + ')') or normalized_user.startswith(letter.lower() + ' '):
                            is_correct = True
                        # Also check if any option starts with this letter and matches user answer
                        elif not is_correct:
                            for opt in options:
                                if normalize_text(opt).startswith(letter.lower() + ')') and normalize_text(opt) == normalized_user:
                                    is_correct = True
                                    break
                            else:
                                is_correct = normalized_user == normalized_correct
                        else:
                            is_correct = normalized_user == normalized_correct
                    else:
                        is_correct = normalized_user == normalized_correct
                except Exception:
                    is_correct = False

            # Get skill/topic (support multiple field names)
            skill = (
                question.get('skill') or 
                question.get('topic') or 
                question.get('domain') or 
                'General'
            )
            
            # Get difficulty level
            difficulty = question.get('difficulty', 'medium').lower()
            marks_for_question = difficulty_marks.get(difficulty, 1.5)  # Default to medium
            max_possible_score += marks_for_question
            
            # Calculate marks earned
            marks_earned = marks_for_question if is_correct else 0
            total_score += marks_earned

            if is_correct:
                correct_count += 1

            # Track skill-wise performance
            if skill not in skill_wise_score:
                skill_wise_score[skill] = {'correct': 0, 'total': 0, 'score': 0, 'maxScore': 0}
            skill_wise_score[skill]['total'] += 1
            skill_wise_score[skill]['maxScore'] += marks_for_question
            if is_correct:
                skill_wise_score[skill]['correct'] += 1
                skill_wise_score[skill]['score'] += marks_for_question

            # Get question text (support multiple field names)
            question_text = (
                question.get('question') or 
                question.get('question_text') or 
                question.get('questionText') or 
                ''
            )

            # Convert correct_answer to full option text
            correct_answer_text = correct_answer
            try:
                # If correct_answer is a single letter (A-D), find the matching option
                if isinstance(correct_answer, str) and len(correct_answer.strip()) == 1 and correct_answer.strip().upper() in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
                    letter = correct_answer.strip().upper()
                    # Find option that starts with this letter
                    for opt in options:
                        if opt.strip().upper().startswith(letter + ')'):
                            correct_answer_text = opt
                            break
                # If correct_answer is a numeric index
                elif isinstance(correct_answer, int) or (isinstance(correct_answer, str) and correct_answer.isdigit()):
                    idx = int(correct_answer)
                    if 0 <= idx < len(options):
                        correct_answer_text = options[idx]
            except Exception:
                correct_answer_text = correct_answer

            detailed_results.append({
                'question': question_text,
                'skill': skill,
                'difficulty': difficulty,
                'marks': marks_for_question,
                'marksEarned': marks_earned,
                'userAnswer': user_answer,
                'correctAnswer': correct_answer_text,
                'isCorrect': is_correct,
                'options': options
            })
        
        # Calculate percentage based on weighted score
        score_percentage = (total_score / max_possible_score * 100) if max_possible_score > 0 else 0
        
        # Update test status to completed in the CORRECT storage
        if mobile in weekly_test_storage:
            weekly_test_storage[mobile]['status'] = 'completed'
        elif mobile in test_questions_storage:
            test_questions_storage[mobile]['status'] = 'completed'
        
        # Calculate skill-wise percentages with weighted scoring
        skill_performance = {}
        for skill, scores in skill_wise_score.items():
            skill_performance[skill] = {
                'correct': scores['correct'],
                'total': scores['total'],
                'score': round(scores['score'], 2),
                'maxScore': round(scores['maxScore'], 2),
                'percentage': round((scores['score'] / scores['maxScore']) * 100, 2) if scores['maxScore'] > 0 else 0
            }
        
        result = {
            'testId': test_id,
            'mobile': mobile,
            'totalQuestions': total_questions,
            'correctAnswers': correct_count,
            'incorrectAnswers': total_questions - correct_count,
            'totalScore': round(total_score, 2),
            'maxPossibleScore': round(max_possible_score, 2),
            'scorePercentage': round(score_percentage, 2),
            'passed': score_percentage >= 60,
            'skillPerformance': skill_performance,
            'detailedResults': detailed_results,
            'completedAt': datetime.now().isoformat()
        }
        
        print(f"\n{'='*60}")
        print(f"✅ TEST COMPLETED")
        print(f"{'='*60}")
        print(f"📱 Mobile: {mobile}")
        print(f"📊 Score: {round(total_score, 2)}/{round(max_possible_score, 2)} ({score_percentage:.2f}%)")
        print(f"✅ Correct: {correct_count}/{total_questions} questions")
        print(f"{'='*60}\n")
        
        # Send results to n8n webhook for database storage
        try:
            n8n_answer_webhook = os.getenv('N8N_TEST_ANSWER_WEBHOOK')
            if n8n_answer_webhook:
                print(f"📤 Sending test results to n8n for database storage...")
                
                n8n_payload = {
                    'mobile': mobile,
                    'testId': test_id,
                    'testType': test_data.get('testType', 'quick'),
                    'skills': test_data.get('skills', []),
                    'totalQuestions': total_questions,
                    'correctAnswers': correct_count,
                    'incorrectAnswers': total_questions - correct_count,
                    'totalScore': round(total_score, 2),
                    'maxPossibleScore': round(max_possible_score, 2),
                    'scorePercentage': round(score_percentage, 2),
                    'passed': score_percentage >= 60,
                    'skillPerformance': skill_performance,
                    'answers': user_answers,
                    'detailedResults': detailed_results,
                    'completedAt': datetime.now().isoformat(),
                    'createdAt': test_data.get('createdAt')
                }
                
                import requests
                n8n_response = requests.post(
                    n8n_answer_webhook,
                    json=n8n_payload,
                    headers={'Content-Type': 'application/json'},
                    timeout=10
                )
                
                if n8n_response.status_code == 200:
                    print(f"✅ Test results sent to n8n successfully")
                else:
                    print(f"⚠️ n8n webhook responded with status {n8n_response.status_code}")
            else:
                print(f"⚠️ N8N_TEST_ANSWER_WEBHOOK not configured in .env")
        except Exception as n8n_error:
            print(f"⚠️ Failed to send to n8n (non-critical): {str(n8n_error)}")
            # Don't fail the whole request if n8n fails

        
        # Persist result into MongoDB collection based on test type
        # Weekly tests go to 'week_test_result' in Placement_Ai database
        # Other tests go to 'quiz_result' in default database
        try:
            test_type = test_data.get('testType', 'quick')
            
            if test_type == 'weekly':
                # Save to week_test_result collection in Placement_Ai database
                mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI")
                client = MongoClient(mongo_uri)
                db = client[os.getenv("MONGODB_DB", "Placement_Ai")]
                weekly_result_col = db['week_test_result']
                
                # Normalize mobile to consistent _id format
                phone_digits = normalize_phone(mobile)
                mobile_id = format_phone_id(phone_digits) if phone_digits else mobile
                
                # Use mobile as _id (no week number suffix)
                result_id = mobile_id
                
                # Build document to upsert
                doc = result.copy()
                doc['mobile'] = format_phone_id(phone_digits) if phone_digits else mobile
                doc['testType'] = 'weekly'
                doc['testTitle'] = test_data.get('testTitle')
                doc['week'] = test_data.get('week')
                doc['month'] = test_data.get('month')
                doc['savedAt'] = datetime.now().isoformat()
                
                # Remove unnecessary fields (questions array is redundant with detailedResults)
                doc.pop('questions', None)
                doc.pop('storage', None)
                doc.pop('skills', None)
                
                # Upsert using mobile as _id
                # Use $unset to remove questions field if it exists from previous saves
                weekly_result_col.update_one(
                    {'_id': result_id},
                    {
                        '$set': doc,
                        '$unset': {'questions': '', 'storage': '', 'skills': ''},
                        '$setOnInsert': {'createdAt': datetime.now().isoformat()}
                    },
                    upsert=True
                )
                print(f"✅ Saved weekly test result to week_test_result with _id={result_id}")
                
            else:
                # Save to quiz_result collection (original behavior for skills tests)
                db = get_db()
                quiz_col = db['quiz_result']

                # Normalize mobile to consistent _id format (use utils.db helpers)
                phone_digits = normalize_phone(mobile)
                mobile_id = format_phone_id(phone_digits) if phone_digits else mobile

                # Prefer username from request if provided, else test_data
                username = None
                try:
                    if isinstance(data, dict):
                        username = data.get('username')
                except Exception:
                    username = None
                if not username and isinstance(test_data, dict):
                    username = test_data.get('username')

                # Build document to upsert (keep result details)
                doc = result.copy()
                # Store normalized mobile for readability and lookup
                doc['mobile'] = format_phone_id(phone_digits) if phone_digits else mobile
                if username:
                    doc['username'] = username
                doc['savedAt'] = datetime.now().isoformat()

                # Upsert using normalized mobile as _id (this will overwrite previous entry for same mobile)
                quiz_col.update_one(
                    {'_id': mobile_id},
                    {'$set': doc, '$setOnInsert': {'createdAt': datetime.now().isoformat()}},
                    upsert=True
                )
                print(f"✅ Saved test result to quiz_result with _id={mobile_id}")
                
        except Exception as db_err:
            print(f"⚠️ Failed to save test result to MongoDB: {str(db_err)}")

        return jsonify({
            'success': True,
            'message': 'Test submitted successfully',
            'data': result
        }), 200
        
    except Exception as e:
        print(f"❌ Error in submit-test-answers: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/submit-single-answer', methods=['POST'])
def submit_single_answer():
    """
    Submit answer for a single question and get next question or test end status
    
    Request body:
    {
        "mobile": "+91 1234567890",
        "testId": "testId_here",
        "questionIndex": 0,
        "answer": 2,
        "timeSpent": 45
    }
    
    Response from n8n:
    {
        "status": "next" | "test_end",
        "nextQuestion": {...},
        "questionNumber": 2,
        "totalQuestions": 10,
        "message": "Test completed"
    }
    """
    try:
        data = request.get_json()
        
        mobile = data.get('mobile')
        test_id = data.get('testId')
        question_index = data.get('questionIndex')
        user_answer = data.get('answer')
        time_spent = data.get('timeSpent', 0)
        
        print(f"\n{'='*60}")
        print(f"📝 SINGLE ANSWER SUBMISSION")
        print(f"{'='*60}")
        print(f"📱 Mobile: {mobile}")
        print(f"🆔 Test ID: {test_id}")
        print(f"❓ Question Index: {question_index}")
        print(f"✍️ User Answer: {user_answer}")
        print(f"⏱️ Time Spent: {time_spent}s")
        print(f"{'='*60}\n")
        
        # Validate required fields
        if not all([mobile, test_id is not None, question_index is not None, user_answer is not None]):
            return jsonify({
                'success': False,
                'error': 'Missing required fields: mobile, testId, questionIndex, answer'
            }), 400
        
        # Get test from storage - check BOTH storages and match by testId
        # Weekly tests are in weekly_test_storage, skills tests in test_questions_storage
        test_data = None
        storage_type = None
        
        # Check weekly test storage first
        weekly_data = weekly_test_storage.get(mobile)
        if weekly_data and weekly_data.get('testId') == test_id:
            test_data = weekly_data
            storage_type = 'weekly'
            print(f"📖 Found test in WEEKLY storage for {mobile}")
        
        # Check skills test storage if not found in weekly
        if not test_data:
            skills_data = test_questions_storage.get(mobile)
            if skills_data and skills_data.get('testId') == test_id:
                test_data = skills_data
                storage_type = 'skills'
                print(f"📖 Found test in SKILLS storage for {mobile}")
        
        if not test_data:
            # Fallback: check if any test exists but testId doesn't match
            if weekly_data or test_questions_storage.get(mobile):
                return jsonify({
                    'success': False,
                    'error': 'Test ID mismatch. The test may have been restarted.'
                }), 400
            return jsonify({
                'success': False,
                'error': 'Test not found. Please start a new test.'
            }), 404
        
        # Check if question index is valid
        questions = test_data.get('questions', [])
        if question_index >= len(questions):
            return jsonify({
                'success': False,
                'error': 'Invalid question index'
            }), 400
        
        # Get the current question
        current_question = questions[question_index]
        # Support multiple possible key names coming from different sources (n8n or MongoDB)
        correct_answer = (
            current_question.get('correctAnswer')
            if current_question.get('correctAnswer') is not None
            else current_question.get('correct_answer')
        )

        # Determine correctness robustly: support index (int), index-as-string, or option text
        options = current_question.get('options', []) or []

        # Normalization helper: strip HTML tags, collapse whitespace, and lowercase for comparison
        def normalize_text(val):
            try:
                s = str(val)
            except Exception:
                s = ''
            # Remove simple HTML tags
            s = re.sub(r'<[^>]*>', '', s)
            # Collapse whitespace
            s = ' '.join(s.split())
            return s.strip().lower()

        # Pre-normalize correct answer and options for robust comparison
        normalized_options = [normalize_text(o) for o in options]
        normalized_correct = normalize_text(correct_answer)
        is_correct = False

        # Helper: try parse ints but only treat as index when within options range
        try:
            ua_int_candidate = int(user_answer) if (isinstance(user_answer, (int, str)) and str(user_answer).lstrip().rstrip().lstrip('+').isdigit()) else None
        except Exception:
            ua_int_candidate = None

        try:
            ca_int_candidate = int(correct_answer) if (isinstance(correct_answer, (int, str)) and str(correct_answer).lstrip().rstrip().lstrip('+').isdigit()) else None
        except Exception:
            ca_int_candidate = None

        # Determine whether parsed ints represent valid indices into options
        ua_is_index = (ua_int_candidate is not None) and (0 <= ua_int_candidate < len(options))
        ca_is_index = (ca_int_candidate is not None) and (0 <= ca_int_candidate < len(options))

        if ua_is_index and ca_is_index:
            # both are indices: compare numeric indices
            is_correct = (ua_int_candidate == ca_int_candidate)
        elif ua_is_index and not ca_is_index:
            # user sent an index, correct_answer is option text
            try:
                is_correct = normalized_options[ua_int_candidate] == normalized_correct
            except Exception:
                is_correct = False
        elif not ua_is_index and ca_is_index:
            # user sent option text (or numeric-text that's not a valid index), correct_answer is index
            try:
                is_correct = normalize_text(user_answer) == normalized_options[ca_int_candidate]
            except Exception:
                is_correct = False
        else:
            # Fallback: both appear to be text; compare normalized strings
            # Special handling: if correct_answer is a single letter (A, B, C, D) and user_answer starts with that letter
            # Example: correct_answer="A", user_answer="A) =" should match
            try:
                normalized_user = normalize_text(user_answer)
                
                # Check if correct_answer is a single letter (A-Z) and user answer starts with it
                if len(str(correct_answer).strip()) == 1 and str(correct_answer).strip().upper() in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
                    letter = str(correct_answer).strip().upper()
                    # Check if user answer starts with "A)", "a)", etc.
                    if normalized_user.startswith(letter.lower() + ')') or normalized_user.startswith(letter.lower() + ' '):
                        is_correct = True
                    # Also check if any option starts with this letter and matches user answer
                    elif not is_correct:
                        for opt in options:
                            if normalize_text(opt).startswith(letter.lower() + ')') and normalize_text(opt) == normalized_user:
                                is_correct = True
                                break
                    else:
                        is_correct = normalized_user == normalized_correct
                else:
                    is_correct = normalized_user == normalized_correct
            except Exception:
                is_correct = False
        
        # Store the user's answer
        if 'userAnswers' not in test_data:
            test_data['userAnswers'] = []
        
        answer_entry = {
            'questionIndex': question_index,
            'userAnswer': user_answer,
            'correctAnswer': correct_answer,
            'isCorrect': is_correct,
            'timeSpent': time_spent,
            'skill': current_question.get('skill'),
            'difficulty': current_question.get('difficulty')
        }
        
        test_data['userAnswers'].append(answer_entry)
        
        # Track when this test was last answered (for determining which test to show results for)
        test_data['lastAnsweredAt'] = datetime.now().isoformat()
        
        # Also persist to MongoDB so answers survive server restarts
        # For weekly tests, store in Placement_Ai.week_test_answers
        # For skills tests, store in n8n.quiz_test_answers
        try:
            mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI")
            if mongo_uri:
                client = MongoClient(mongo_uri)
                
                # Determine which database/collection based on test type
                # Use storage_type as fallback to ensure correct collection
                test_type = test_data.get('testType', 'skills')
                if storage_type == 'weekly' or test_type == 'weekly':
                    test_type = 'weekly'
                    db = client[os.getenv("MONGODB_DB", "Placement_Ai")]
                    collection = db["week_test_answers"]
                else:
                    test_type = 'skills'
                    db = client[os.getenv("MONGODB_DB_N8N", "n8n")]
                    collection = db["quiz_test_answers"]
                
                print(f"📂 Storage Type: {storage_type}, Test Type: {test_type}")
                
                # Upsert the answer - use mobile_week_N as _id for weekly tests
                if test_type == 'weekly':
                    week_number = test_data.get('week', 1)
                    doc_id = f"{mobile}_week_{week_number}"
                else:
                    doc_id = mobile
                
                collection.update_one(
                    {"_id": doc_id},
                    {
                        "$set": {
                            "testId": test_id,
                            "testType": test_type,
                            "week": test_data.get('week') if test_type == 'weekly' else None,
                            "month": test_data.get('month') if test_type == 'weekly' else None,
                            "lastUpdated": datetime.now().isoformat()
                        },
                        "$push": {
                            "userAnswers": answer_entry
                        }
                    },
                    upsert=True
                )
                print(f"💾 Answer persisted to MongoDB ({test_type} test) with _id={doc_id}")
        except Exception as db_err:
            print(f"⚠️ Failed to persist answer to MongoDB: {str(db_err)}")
            # Continue even if DB save fails - memory still has the answer
        
        print(f"✅ Answer recorded: {'Correct' if is_correct else 'Incorrect'}")
        
        # Skip n8n webhook call for faster response - use local logic directly
        # Return next question or test end based on local storage
        if question_index + 1 < len(questions):
            next_question = questions[question_index + 1].copy()
            # Remove correct answer before sending
            next_question.pop('correctAnswer', None)
            next_question.pop('correct_answer', None)
            
            return jsonify({
                'success': True,
                'status': 'next',
                'isCorrect': is_correct,
                'nextQuestion': next_question,
                'questionNumber': question_index + 2,
                'totalQuestions': len(questions),
                'progress': round((len(test_data['userAnswers']) / len(questions)) * 100, 2)
            }), 200
        else:
            # Test completed
            test_data['status'] = 'completed'
            return jsonify({
                'success': True,
                'status': 'test_end',
                'isCorrect': is_correct,
                'message': 'Test completed successfully',
                'totalAnswered': len(test_data['userAnswers']),
                'totalQuestions': len(questions)
            }), 200
        
    except Exception as e:
        print(f"❌ Error in submit-single-answer: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ===========================
# STUDENT ANALYSIS ENDPOINTS
# ===========================

@app.route('/api/check-student-analysis', methods=['GET'])
def check_student_analysis():
    """
    Check if student analysis data exists for a mobile number
    Useful for verifying if n8n workflow completed successfully
    """
    try:
        mobile = request.args.get('mobile')
        if not mobile:
            return jsonify({
                'success': False,
                'error': 'Mobile number parameter is required'
            }), 400
        
        # Try to find by multiple mobile formats
        db = get_db()
        collection = db["student analysis "]  # Collection name with trailing space
        
        # Try different formats
        mobile_formats = [
            mobile,  # Original format
            mobile.replace('+', '').replace('-', '').replace(' ', ''),  # Cleaned
            f"+91 {mobile}",  # Add +91 prefix
            f"+91{mobile}",  # Add +91 without space
        ]
        
        analysis_doc = None
        for mobile_format in mobile_formats:
            analysis_doc = collection.find_one({'$or': [
                {'_id': mobile_format},
                {'mobile': mobile_format},
                {'phoneNumber': mobile_format}
            ]})
            if analysis_doc:
                break
        
        if analysis_doc:
            return jsonify({
                'success': True,
                'exists': True,
                'mobile': analysis_doc.get('mobile') or analysis_doc.get('phoneNumber', mobile),
                'analysis_summary': {
                    'name': analysis_doc.get('name', 'N/A'),
                    'resume_score': analysis_doc.get('resume_score', 0),
                    'created_at': analysis_doc.get('created_at', 'N/A'),
                    'source': analysis_doc.get('source', 'N/A')
                },
                'message': 'Student analysis data found - n8n workflow completed successfully'
            })
        else:
            return jsonify({
                'success': True,
                'exists': False,
                'mobile': mobile,
                'message': 'No student analysis data found - n8n workflow may not have completed yet'
            })
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/trigger-n8n-for-resume', methods=['POST'])
def trigger_n8n_for_resume():
    """
    Trigger n8n workflow for a specific resume by mobile number
    Useful for processing existing resumes through n8n
    """
    try:
        data = request.get_json()
        
        if not data or not data.get('mobile'):
            return jsonify({
                'success': False,
                'error': 'Mobile number is required'
            }), 400
        
        mobile = data.get('mobile')
        
        # Get resume data from database
        db = get_db()
        collection_name = os.environ.get("MONGODB_COLLECTION", "Resume")
        collection = db[collection_name]
        
        # Find resume by mobile number (try different formats)
        mobile_clean = mobile.replace('+', '').replace('-', '').replace(' ', '')
        mobile_formatted = f"+{mobile_clean}"
        
        resume_doc = collection.find_one({
            '$or': [
                {'phone': mobile},
                {'phone': mobile_clean},
                {'phone': mobile_formatted},
                {'_id': mobile_clean},
                {'_id': mobile_formatted}
            ]
        })
        
        if not resume_doc:
            return jsonify({
                'success': False,
                'error': f'No resume found for mobile number: {mobile}'
            }), 404
        
        # Extract user data and prediction data
        user_data = {
            'name': resume_doc.get('name', ''),
            'email': resume_doc.get('email', ''),
            'mobile': resume_doc.get('phone', mobile),
            'tenthPercentage': resume_doc.get('tenthPercentage', 0),
            'twelfthPercentage': resume_doc.get('twelfthPercentage', 0),
            'collegeCGPA': resume_doc.get('cgpa', 0),
            'degree': resume_doc.get('degree', ''),
            'college': resume_doc.get('college', ''),
            'selectedDomainId': resume_doc.get('selectedDomainId', ''),
            'selectedSkills': resume_doc.get('skills', []),
            'customJobRole': resume_doc.get('customJobRole', '')
        }
        
        prediction_data = resume_doc.get('prediction', {})
        
        if not prediction_data:
            return jsonify({
                'success': False,
                'error': 'No prediction data found for this resume'
            }), 400
        
        # Send to n8n
        n8n_result = send_prediction_to_n8n(user_data, prediction_data, "manual_trigger")
        
        return jsonify({
            'success': True,
            'message': f'n8n workflow triggered for {user_data.get("name", "unknown user")}',
            'mobile': mobile,
            'n8n_result': n8n_result
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/send-to-n8n', methods=['POST'])
def send_to_n8n():
    """Send data to n8n webhook"""
    try:
        import requests
        
        print(f"\n{'='*70}")
        print(f"🌐 /api/send-to-n8n ENDPOINT CALLED")
        print(f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*70}")
        
        data = request.get_json()
        if not data:
            print("❌ No data provided in request!")
            return jsonify({
                'success': False,
                'message': 'No data provided'
            }), 400
        
        print(f"📦 Received data: {json.dumps(data, indent=2)}")
        
        # Get webhook URLs from environment
        webhook_url = os.getenv('N8N_MOBILE_WEBHOOK')
        webhook_url_2 = os.getenv('N8N_MOBILE_WEBHOOK_2')
        
        print(f"🔗 Primary webhook URL: {webhook_url or 'NOT CONFIGURED'}")
        print(f"🔗 Secondary webhook URL: {webhook_url_2 or 'NOT CONFIGURED'}")
        
        if not webhook_url and not webhook_url_2:
            print("❌ No webhook URLs configured!")
            return jsonify({
                'success': False,
                'message': 'Webhook URL not configured'
            }), 500

        # Prepare webhook payload
        webhook_payload = {
            'mobile': data.get('mobile'),
            'email': data.get('email'),
            'name': data.get('name'),
            'timestamp': datetime.now().isoformat(),
            'action': data.get('action', 'mobile_submission'),
            'source': 'placement-ai'
        }
        
        print(f"📤 Webhook payload to send: {json.dumps(webhook_payload, indent=2)}")
        print(f"📤 Webhook payload to send: {json.dumps(webhook_payload, indent=2)}")

        results = {}

        # Send to primary webhook if configured
        if webhook_url:
            try:
                print(f"\n📡 Sending to PRIMARY webhook: {webhook_url}")
                resp = requests.post(
                    webhook_url,
                    json=webhook_payload,
                    headers={'Content-Type': 'application/json'},
                    timeout=30
                )
                print(f"✅ Primary webhook response status: {resp.status_code}")
                print(f"📄 Primary webhook response: {resp.text[:500]}")
                results['webhook_1'] = {'status_code': resp.status_code, 'text': resp.text[:200] if resp.text else None}
            except Exception as e:
                print(f"❌ Primary webhook error: {str(e)}")
                results['webhook_1'] = {'error': str(e)}

        # Send to secondary webhook if configured (non-blocking)
        if webhook_url_2:
            try:
                print(f"\n📡 Sending to SECONDARY webhook: {webhook_url_2}")
                resp2 = requests.post(
                    webhook_url_2,
                    json=webhook_payload,
                    headers={'Content-Type': 'application/json'},
                    timeout=30
                )
                print(f"✅ Secondary webhook response status: {resp2.status_code}")
                print(f"📄 Secondary webhook response: {resp2.text[:500]}")
                results['webhook_2'] = {'status_code': resp2.status_code, 'text': resp2.text[:200] if resp2.text else None}
            except Exception as e:
                print(f"❌ Secondary webhook error: {str(e)}")
                results['webhook_2'] = {'error': str(e)}

        # Consider success if at least one webhook returned 200
        any_ok = any((v.get('status_code') == 200) for v in results.values() if isinstance(v, dict))

        print(f"\n📊 Results summary: {json.dumps(results, indent=2)}")
        print(f"🎯 Any webhook successful: {any_ok}")
        print(f"{'='*70}\n")

        if any_ok:
            return jsonify({'success': True, 'message': 'Data sent to at least one webhook', 'results': results})
        else:
            return jsonify({'success': False, 'message': 'No webhook returned 200', 'results': results}), 502
            
    except requests.exceptions.RequestException as e:
        return jsonify({
            'success': False,
            'message': f'Failed to send data to n8n: {str(e)}'
        }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500

@app.route('/api/test-n8n', methods=['GET'])
def test_n8n():
    """Test n8n webhook integration"""
    try:
        import requests
        
        webhook_url = os.getenv('N8N_MOBILE_WEBHOOK')
        webhook_url_2 = os.getenv('N8N_MOBILE_WEBHOOK_2')
        if not webhook_url and not webhook_url_2:
            return jsonify({
                'success': False,
                'message': 'N8N_MOBILE_WEBHOOK not configured in .env file'
            }), 500

        # Test payload
        test_payload = {
            'mobile': '9876543210',
            'email': 'test@example.com',
            'name': 'Test User',
            'timestamp': datetime.now().isoformat(),
            'action': 'test_webhook',
            'source': 'placement-ai-test'
        }

        results = {}

        if webhook_url:
            try:
                resp = requests.post(
                    webhook_url,
                    json=test_payload,
                    headers={'Content-Type': 'application/json'},
                    timeout=30
                )
                results['webhook_1'] = {'url': webhook_url, 'status_code': resp.status_code, 'response_text': resp.text[:200] if resp.text else 'No response content'}
            except Exception as e:
                results['webhook_1'] = {'url': webhook_url, 'error': str(e)}

        if webhook_url_2:
            try:
                resp2 = requests.post(
                    webhook_url_2,
                    json=test_payload,
                    headers={'Content-Type': 'application/json'},
                    timeout=30
                )
                results['webhook_2'] = {'url': webhook_url_2, 'status_code': resp2.status_code, 'response_text': resp2.text[:200] if resp2.text else 'No response content'}
            except Exception as e:
                results['webhook_2'] = {'url': webhook_url_2, 'error': str(e)}

        return jsonify({'success': True, 'results': results})
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Test failed: {str(e)}'
        }), 500

@app.route('/api/resume-analysis/<phone_number>', methods=['GET'])
def get_resume_analysis(phone_number):
    """Get resume analysis data for a specific phone number"""
    try:
        if not phone_number:
            return jsonify({
                'success': False,
                'message': 'Phone number is required'
            }), 400
        
        # Get database connection
        db = get_db()
        
        # Clean phone number (remove any formatting)
        clean_phone = phone_number.strip().replace('+', '').replace('-', '').replace(' ', '')
        
        # Search for analysis data in student_analysis collection
        # Try multiple phone number formats
        phone_patterns = [
            clean_phone,
            phone_number,
            f"+91{clean_phone}" if len(clean_phone) == 10 else clean_phone,
            clean_phone[2:] if clean_phone.startswith('91') and len(clean_phone) == 12 else clean_phone
        ]
        
        analysis_data = None
        for pattern in phone_patterns:
            analysis_data = db["student analysis "].find_one({'mobile': pattern})  # Collection name with trailing space
            if analysis_data:
                break
        
        if not analysis_data:
            return jsonify({
                'success': False,
                'message': 'No analysis data found for this phone number'
            }), 404
        
        # _id is now the mobile number (string), no need to convert from ObjectId
        if '_id' in analysis_data:
            analysis_data['_id'] = str(analysis_data['_id'])
        
        # Structure the response data
        response_data = {
            'summary': analysis_data.get('summary', ''),
            'resume_score': analysis_data.get('resume_score', 0),
            'strengths': analysis_data.get('strengths', []),
            'weaknesses': analysis_data.get('weaknesses', []),
            'ats_tips': analysis_data.get('ats_tips', []),
            'missing_skills': analysis_data.get('missing_skills', []),
            'project_suggestions': analysis_data.get('project_suggestions', []),
            'company_suggestions': {
                'company_1': {
                    'name': analysis_data.get('company_1_name', ''),
                    'eligible': analysis_data.get('company_1_eligible', ''),
                    'reason': analysis_data.get('company_1_reason', '')
                },
                'company_2': {
                    'name': analysis_data.get('company_2_name', ''),
                    'eligible': analysis_data.get('company_2_eligible', ''),
                    'reason': analysis_data.get('company_2_reason', '')
                },
                'company_3': {
                    'name': analysis_data.get('company_3_name', ''),
                    'eligible': analysis_data.get('company_3_eligible', ''),
                    'reason': analysis_data.get('company_3_reason', '')
                },
                'company_4': {
                    'name': analysis_data.get('company_4_name', ''),
                    'eligible': analysis_data.get('company_4_eligible', ''),
                    'reason': analysis_data.get('company_4_reason', '')
                }
            },
            'timestamp': analysis_data.get('timestamp'),
            'mobile': analysis_data.get('mobile')
        }
        
        return jsonify({
            'success': True,
            'data': response_data
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error retrieving analysis data: {str(e)}'
        }), 500


@app.route('/api/check-quiz-analysis/<mobile>', methods=['GET'])
def check_quiz_analysis(mobile):
    """
    Check if quiz analysis exists in the quiz_analysis collection (n8n database)
    Returns True if analysis exists, False otherwise
    
    This endpoint is used by the frontend to check if analysis already exists
    before triggering the webhook to generate a new one.
    """
    try:
        if not mobile:
            return jsonify({'success': False, 'exists': False, 'error': 'Mobile number is required'}), 400

        mongo_uri = os.getenv('MONGO_URI') or os.getenv('MONGODB_URI')
        if not mongo_uri:
            return jsonify({'success': False, 'exists': False, 'error': 'MongoDB URI not configured'}), 500

        client = MongoClient(mongo_uri)
        n8n_db_name = os.getenv('MONGODB_DB_N8N', 'n8n')
        coll_name = os.getenv('MONGODB_COLLECTION_QUIZ_ANALYSIS', 'quiz_analysis')
        db = client[n8n_db_name]
        collection = db[coll_name]

        # Build variants to search (preserve order)
        clean = ''.join([c for c in mobile if c.isdigit()])
        variants = [mobile, mobile.replace(' ', ''), mobile.replace('+', ''), clean]
        
        # Add last 10 digits (phone number without country code)
        if len(clean) >= 10:
            last10 = clean[-10:]
            variants.append(last10)
            variants.append(f'+91 {last10}')
            variants.append(f'+91{last10}')
            variants.append(f'91{last10}')
            variants.append(f'91 {last10}')

        seen = set()
        uniq = []
        for v in variants:
            if v not in seen:
                seen.add(v)
                uniq.append(v)

        # Try to find a document by _id or mobile fields
        doc = None
        matched = None
        for v in uniq:
            # try _id first
            doc = collection.find_one({'_id': v})
            if doc:
                matched = ('_id', v)
                break
            # try mobile-like fields
            doc = collection.find_one({'$or': [{'mobile': v}, {'phone': v}, {'phoneNumber': v}]})
            if doc:
                matched = ('field', v)
                break

        if doc:
            print(f"✅ Quiz analysis exists in database for {mobile} (matched {matched[0]}: {matched[1]})")
            return jsonify({
                'success': True,
                'exists': True,
                'message': 'Analysis already exists in database'
            }), 200
        else:
            print(f"❌ No quiz analysis found in database for {mobile}")
            return jsonify({
                'success': True,
                'exists': False,
                'message': 'No analysis found in database'
            }), 200

    except Exception as e:
        print(f"❌ Error checking quiz_analysis collection: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'exists': False,
            'error': str(e)
        }), 500


@app.route('/api/quiz-analysis/<mobile>', methods=['GET'])
def get_quiz_analysis(mobile):
    """
    Fetch quiz analysis documents from the n8n database's quiz_analysis collection
    Tries multiple mobile number formats to be tolerant of different _id conventions
    """
    try:
        if not mobile:
            return jsonify({'success': False, 'message': 'Mobile number is required'}), 400

        mongo_uri = os.getenv('MONGO_URI') or os.getenv('MONGODB_URI')
        if not mongo_uri:
            return jsonify({'success': False, 'message': 'MongoDB URI not configured'}), 500

        client = MongoClient(mongo_uri)
        n8n_db_name = os.getenv('MONGODB_DB_N8N', 'n8n')
        coll_name = os.getenv('MONGODB_COLLECTION_QUIZ_ANALYSIS', 'quiz_analysis')
        db = client[n8n_db_name]
        collection = db[coll_name]

        # Build variants to search (preserve order)
        clean = ''.join([c for c in mobile if c.isdigit()])
        variants = [mobile, mobile.replace(' ', ''), mobile.replace('+', ''), clean]
        
        # Add last 10 digits (phone number without country code)
        if len(clean) >= 10:
            last10 = clean[-10:]
            variants.append(last10)
            variants.append(f'+91 {last10}')
            variants.append(f'+91{last10}')
            variants.append(f'91{last10}')
            variants.append(f'91 {last10}')

        seen = set()
        uniq = []
        for v in variants:
            if v not in seen:
                seen.add(v)
                uniq.append(v)

        # Try to find a document by _id or mobile fields
        doc = None
        matched = None
        for v in uniq:
            # try _id first
            doc = collection.find_one({'_id': v})
            if doc:
                matched = ('_id', v)
                break
            # try mobile-like fields
            doc = collection.find_one({'$or': [{'mobile': v}, {'phone': v}, {'phoneNumber': v}]})
            if doc:
                matched = ('field', v)
                break

        if not doc:
            return jsonify({'success': False, 'message': 'No quiz analysis found for this mobile number'}), 404

        # Convert BSON types to JSON-friendly native types
        def normalize_value(v):
            # Handle nested extended-json styles like {'$numberDouble': '83.33'}
            if isinstance(v, dict):
                # Common extended JSON numeric forms
                if '$numberDouble' in v:
                    try:
                        return float(v['$numberDouble'])
                    except Exception:
                        return v['$numberDouble']
                if '$numberInt' in v:
                    try:
                        return int(v['$numberInt'])
                    except Exception:
                        return v['$numberInt']
                if '$numberLong' in v:
                    try:
                        return int(v['$numberLong'])
                    except Exception:
                        return v['$numberLong']
                # Date style
                if '$date' in v:
                    return v['$date']
                # Otherwise normalize recursively
                return {k: normalize_value(val) for k, val in v.items()}
            elif isinstance(v, list):
                return [normalize_value(x) for x in v]
            else:
                # For pymongo native types like Decimal128/ObjectId, convert to str/float as needed
                try:
                    from bson.decimal128 import Decimal128
                    from bson.objectid import ObjectId
                    if isinstance(v, Decimal128):
                        try:
                            return float(v.to_decimal())
                        except Exception:
                            return str(v)
                    if isinstance(v, ObjectId):
                        return str(v)
                except Exception:
                    pass
                return v

        # Build a sanitized copy
        sanitized = {}
        for k, val in doc.items():
            sanitized[k] = normalize_value(val)

        # Ensure _id is a string
        if '_id' in sanitized:
            try:
                sanitized['_id'] = str(sanitized['_id'])
            except Exception:
                pass

        return jsonify({'success': True, 'data': sanitized, 'matched': matched}), 200

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/quiz-result/<mobile>', methods=['GET'])
def get_quiz_result(mobile):
    """
    Fetch a saved quiz result from the quiz_result collection.
    Tries multiple mobile formats and _id lookup. Returned document is JSON-safe.
    """
    try:
        if not mobile:
            return jsonify({'success': False, 'message': 'Mobile number is required'}), 400

        mongo_uri = os.getenv('MONGO_URI') or os.getenv('MONGODB_URI')
        if not mongo_uri:
            return jsonify({'success': False, 'message': 'MongoDB URI not configured'}), 500

        client = MongoClient(mongo_uri)
        db_name = os.getenv('MONGODB_DB', os.getenv('MONGODB_DB_N8N', 'n8n'))
        db = client[db_name]
        collection = db['quiz_result']

        # Build variants to search
        clean = ''.join([c for c in mobile if c.isdigit()])
        variants = [mobile, mobile.replace(' ', ''), mobile.replace('+', ''), clean]
        
        # Add last 10 digits (phone number without country code)
        if len(clean) >= 10:
            last10 = clean[-10:]
            variants.append(last10)
            variants.append(f'+91 {last10}')
            variants.append(f'+91{last10}')
            variants.append(f'91{last10}')
            variants.append(f'91 {last10}')

        seen = set()
        uniq = []
        for v in variants:
            if v not in seen:
                seen.add(v)
                uniq.append(v)

        doc = None
        matched = None
        for v in uniq:
            # try _id first
            doc = collection.find_one({'_id': v})
            if doc:
                matched = ('_id', v)
                break
            doc = collection.find_one({'$or': [{'mobile': v}, {'phone': v}, {'phoneNumber': v}]})
            if doc:
                matched = ('field', v)
                break

        if not doc:
            return jsonify({'success': False, 'message': 'No quiz result found for this mobile number'}), 404

        # Normalize JSON-friendly
        def normalize_value(v):
            if isinstance(v, dict):
                # extended JSON numeric
                if '$numberDouble' in v:
                    try:
                        return float(v['$numberDouble'])
                    except Exception:
                        return v['$numberDouble']
                if '$numberInt' in v:
                    try:
                        return int(v['$numberInt'])
                    except Exception:
                        return v['$numberInt']
                if '$numberLong' in v:
                    try:
                        return int(v['$numberLong'])
                    except Exception:
                        return v['$numberLong']
                if '$date' in v:
                    return v['$date']
                return {k: normalize_value(val) for k, val in v.items()}
            elif isinstance(v, list):
                return [normalize_value(x) for x in v]
            else:
                try:
                    from bson.decimal128 import Decimal128
                    from bson.objectid import ObjectId
                    if isinstance(v, Decimal128):
                        try:
                            return float(v.to_decimal())
                        except Exception:
                            return str(v)
                    if isinstance(v, ObjectId):
                        return str(v)
                except Exception:
                    pass
                return v

        sanitized = {k: normalize_value(val) for k, val in doc.items()}
        if '_id' in sanitized:
            try:
                sanitized['_id'] = str(sanitized['_id'])
            except Exception:
                pass

        return jsonify({'success': True, 'data': sanitized, 'matched': matched}), 200

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/weekly-test-result/<mobile>', methods=['GET'])
def get_weekly_test_result(mobile):
    """
    Fetch a saved weekly test result from the week_test_result collection in Placement_Ai database.
    This is SEPARATE from quiz_result (which stores skills test results).
    """
    try:
        if not mobile:
            return jsonify({'success': False, 'message': 'Mobile number is required'}), 400

        mongo_uri = os.getenv('MONGO_URI') or os.getenv('MONGODB_URI')
        if not mongo_uri:
            return jsonify({'success': False, 'message': 'MongoDB URI not configured'}), 500

        client = MongoClient(mongo_uri)
        db = client[os.getenv("MONGODB_DB", "Placement_Ai")]
        collection = db['week_test_result']

        # Build mobile variants to search
        clean = ''.join([c for c in mobile if c.isdigit()])
        base_variants = [mobile, mobile.replace(' ', ''), mobile.replace('+', ''), clean]
        if len(clean) == 10:
            base_variants.append(f'+91 {clean}')
            base_variants.append(f'+91{clean}')

        seen = set()
        uniq = []
        for v in base_variants:
            if v not in seen:
                seen.add(v)
                uniq.append(v)
        
        doc = None
        matched = None
        
        # First try mobile-only _ids (new format)
        for v in uniq:
            doc = collection.find_one({'_id': v})
            if doc:
                matched = v
                break
        
        # Fallback to old week-specific format for backward compatibility
        if not doc:
            week_variants = []
            for base in uniq:
                for week in range(1, 13):
                    week_variants.append(f"{base}_week_{week}")
            
            for v in week_variants:
                doc = collection.find_one({'_id': v})
                if doc:
                    matched = v
                    break
        
        # Fallback to old format (backward compatibility)
        if not doc:
            for v in uniq:
                doc = collection.find_one({'_id': v})
                if doc:
                    matched = ('_id', v)
                    break
        
        # Also try searching by mobile field
        if not doc:
            for v in uniq:
                doc = collection.find_one({'$or': [{'mobile': v}, {'phone': v}, {'phoneNumber': v}]})
                if doc:
                    matched = ('field', v)
                    break

        if not doc:
            return jsonify({'success': False, 'message': 'No weekly test result found for this mobile number'}), 404

        # Convert ObjectId and other BSON types to strings
        sanitized = {}
        for k, v in doc.items():
            if k == '_id':
                sanitized[k] = str(v)
            elif hasattr(v, 'isoformat'):
                sanitized[k] = v.isoformat()
            else:
                sanitized[k] = v

        print(f"📊 Retrieved weekly test result for {mobile}")
        return jsonify({'success': True, 'data': sanitized, 'matched': matched, 'testType': 'weekly'}), 200

    except Exception as e:
        print(f"❌ Error getting weekly test result: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/get-test-result/<mobile>', methods=['GET'])
def get_test_result_combined(mobile):
    """
    Smart endpoint that checks BOTH weekly_test_storage AND test_questions_storage
    to determine which test type to return results for.
    
    Priority: Returns the most recently taken test (weekly or skills).
    """
    try:
        if not mobile:
            return jsonify({'success': False, 'message': 'Mobile number is required'}), 400

        mobile = mobile.strip()
        
        # Check memory storages first to see which test was most recently taken
        weekly_test = weekly_test_storage.get(mobile)
        skills_test = test_questions_storage.get(mobile)
        
        # Determine which test to return based on what's in memory
        test_type = None
        test_data = None
        
        if weekly_test and skills_test:
            # Both exist - determine which was most recently answered
            weekly_time = weekly_test.get('lastAnsweredAt', '')
            skills_time = skills_test.get('lastAnsweredAt', '')
            
            # First check if one is completed and the other isn't
            weekly_completed = weekly_test.get('status') == 'completed'
            skills_completed = skills_test.get('status') == 'completed'
            
            if skills_completed and not weekly_completed:
                # Skills test was completed, weekly wasn't - show skills
                test_type = 'skills'
                test_data = skills_test
            elif weekly_completed and not skills_completed:
                # Weekly test was completed, skills wasn't - show weekly
                test_type = 'weekly'
                test_data = weekly_test
            elif skills_time > weekly_time:
                # Skills test was answered more recently
                test_type = 'skills'
                test_data = skills_test
                print(f"📊 Skills test answered more recently: {skills_time} > {weekly_time}")
            else:
                # Weekly test was answered more recently (or same time)
                test_type = 'weekly'
                test_data = weekly_test
                print(f"📊 Weekly test answered more recently: {weekly_time} >= {skills_time}")
        elif weekly_test:
            test_type = 'weekly'
            test_data = weekly_test
        elif skills_test:
            test_type = 'skills'
            test_data = skills_test
        
        if test_data:
            print(f"📖 Found {test_type} test in memory for {mobile}")
            return jsonify({
                'success': True,
                'testType': test_type,
                'inMemory': True,
                'testId': test_data.get('testId'),
                'status': test_data.get('status', 'pending'),
                'totalQuestions': test_data.get('totalQuestions', 0),
                'answersCount': len(test_data.get('userAnswers', []))
            }), 200
        
        # Not in memory - check database collections
        mongo_uri = os.getenv('MONGO_URI') or os.getenv('MONGODB_URI')
        if not mongo_uri:
            return jsonify({'success': False, 'message': 'MongoDB URI not configured'}), 500
        
        client = MongoClient(mongo_uri)
        
        # Build variants
        clean = ''.join([c for c in mobile if c.isdigit()])
        variants = [mobile, mobile.replace(' ', ''), mobile.replace('+', ''), clean]
        if len(clean) == 10:
            variants.append(f'+91 {clean}')
            variants.append(f'+91{clean}')
        
        seen = set()
        uniq = [v for v in variants if not (v in seen or seen.add(v))]
        
        # Check week_test_result collection first
        weekly_db = client[os.getenv("MONGODB_DB", "Placement_Ai")]
        weekly_col = weekly_db['week_test_result']
        
        weekly_doc = None
        # Try mobile-only _ids first (new format)
        for v in uniq:
            weekly_doc = weekly_col.find_one({'_id': v})
            if weekly_doc:
                break
        
        # Fallback to old week-specific format for backward compatibility
        if not weekly_doc:
            week_variants = []
            for base in uniq:
                for week in range(1, 13):  # Check weeks 1-12
                    week_variants.append(f"{base}_week_{week}")
            
            for v in week_variants:
                weekly_doc = weekly_col.find_one({'_id': v})
                if weekly_doc:
                    break
        
        # Check quiz_result collection
        skills_db = client[os.getenv("MONGODB_DB_N8N", "n8n")]
        skills_col = skills_db['quiz_result']
        
        skills_doc = None
        for v in uniq:
            skills_doc = skills_col.find_one({'_id': v})
            if skills_doc:
                break
        
        # Return the most recent one based on savedAt/completedAt timestamp
        if weekly_doc and skills_doc:
            weekly_time = weekly_doc.get('savedAt') or weekly_doc.get('completedAt') or ''
            skills_time = skills_doc.get('savedAt') or skills_doc.get('completedAt') or ''
            if weekly_time >= skills_time:
                test_type = 'weekly'
            else:
                test_type = 'skills'
        elif weekly_doc:
            test_type = 'weekly'
        elif skills_doc:
            test_type = 'skills'
        else:
            return jsonify({'success': False, 'message': 'No test result found'}), 404
        
        print(f"📊 Found {test_type} test in database for {mobile}")
        return jsonify({
            'success': True,
            'testType': test_type,
            'inMemory': False,
            'redirectTo': f'/api/{"weekly-test-result" if test_type == "weekly" else "quiz-result"}/{mobile}'
        }), 200

    except Exception as e:
        print(f"❌ Error in get-test-result: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/save-student-analysis', methods=['POST'])
def save_student_analysis_endpoint():
    """
    API endpoint to save student analysis data (used by n8n)
    Prevents duplicate entries by using upsert operation
    Also fetches Microsoft Learn courses for provided topics
    """
    try:
        print(f"\n{'='*70}")
        print(f"🌐 /api/save-student-analysis ENDPOINT CALLED")
        print(f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*70}")
        
        data = request.get_json()
        
        if not data:
            print("❌ No data provided in request!")
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        print(f"📦 Received data with keys: {list(data.keys())}")
        mobile = data.get('mobile') or data.get('phone') or data.get('phoneNumber')
        topics = data.get('topics', [])
        print(f"📱 Mobile from request: {mobile}")
        print(f"📚 Topics from request: {topics}")
        
        # Save with duplicate prevention
        result = save_student_analysis_safe(data)
        
        print(f"✅ Save result: {result.get('action')} - {result.get('message')}")
        print(f"🆔 Document ID: {result.get('document_id')}")
        
        # Fetch Microsoft Learn courses if topics are provided
        courses_data = None
        if topics and isinstance(topics, list) and len(topics) > 0:
            try:
                print(f"🔍 Fetching Microsoft Learn courses for {len(topics)} topics...")
                catalog_url = 'https://learn.microsoft.com/api/catalog'
                catalog_resp = requests.get(catalog_url, timeout=10)
                catalog_resp.raise_for_status()
                catalog = catalog_resp.json()
                
                all_courses = catalog.get('courses', [])
                modules = catalog.get('modules', [])
                
                courses_result = {}
                for topic in topics:
                    topic_lower = topic.lower()
                    stop_words = {'for', 'with', 'the', 'and', 'or', 'in', 'to', 'of', 'a', 'an', 'on', 'at', 'from', 'by'}
                    keywords = [w for w in topic_lower.split() if w not in stop_words and len(w) > 2]
                    
                    matching = []
                    for course in all_courses:
                        title = (course.get('title') or '').lower()
                        summary = (course.get('summary') or '').lower()
                        products = [p.lower() for p in (course.get('products') or [])]
                        
                        score = 0
                        for keyword in keywords:
                            if keyword in title:
                                score += 3
                            elif keyword in summary:
                                score += 1
                            elif any(keyword in p for p in products):
                                score += 2
                        
                        if score > 0:
                            matching.append({
                                'type': 'course',
                                'title': course.get('title'),
                                'url': course.get('url'),
                                'summary': course.get('summary'),
                                'duration_minutes': course.get('duration_in_minutes'),
                                'level': course.get('levels', [''])[0] if course.get('levels') else 'intermediate',
                                'relevance_score': score
                            })
                    
                    for module in modules[:500]:
                        title = (module.get('title') or '').lower()
                        summary = (module.get('summary') or '').lower()
                        
                        score = 0
                        for keyword in keywords:
                            if keyword in title:
                                score += 3
                            elif keyword in summary:
                                score += 1
                        
                        if score > 0:
                            matching.append({
                                'type': 'module',
                                'title': module.get('title'),
                                'url': module.get('url'),
                                'summary': module.get('summary'),
                                'duration_minutes': module.get('duration_in_minutes'),
                                'level': module.get('levels', [''])[0] if module.get('levels') else 'beginner',
                                'relevance_score': score
                            })
                    
                    matching.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
                    courses_result[topic] = matching[:3]
                
                courses_data = {
                    'courses': courses_result,
                    'total_topics': len(topics),
                    'catalog_stats': {
                        'total_courses': len(all_courses),
                        'total_modules': len(modules)
                    }
                }
                print(f"✅ Fetched courses for {len(courses_result)} topics")
                
            except Exception as e:
                print(f"⚠️ Failed to fetch courses: {str(e)}")
                courses_data = {'error': f'Failed to fetch courses: {str(e)}'}
        
        print(f"{'='*70}\n")
        
        # Include courses in response
        if result['success']:
            response = {**result}
            if courses_data:
                response['microsoft_courses'] = courses_data
            return jsonify(response), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/sync-resume-to-analysis', methods=['POST'])
def sync_resume_to_analysis_endpoint():
    """
    MANUAL BULK SYNC: API endpoint to sync existing resume data to student analysis collection
    
    WARNING: This bypasses n8n processing and should only be used for:
    - Bulk migration of existing data before n8n integration
    - Emergency data recovery
    
    Normal flow: New predictions → n8n processes → n8n saves to student analysis
    """
    try:
        # Check for admin access or authentication as needed
        result = bulk_sync_resumes_to_analysis()
        
        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/student-analysis', methods=['GET'])
def get_student_analysis():
    """
    Fetch student analysis data from student_analysis collection
    
    Query Parameters:
    - mobile: Student's mobile number (optional)
    - email: Student's email (optional)
    
    Returns analysis data including strengths, weaknesses, and suggestions
    """
    try:
        # Get query parameters
        mobile = request.args.get('mobile', '').strip()
        email = request.args.get('email', '').strip()
        
        if not mobile and not email:
            return jsonify({
                'success': False,
                'error': 'Mobile number or email is required'
            }), 400
        
        # Get database connection
        db = get_db()
        collection = db["student analysis "]  # Collection name with trailing space
        
        # Build query with multiple phone format possibilities
        query = {}
        if mobile:
            # Try multiple formats
            mobile_formats = [
                mobile,  # Original
                mobile.replace('+', '').replace('-', '').replace(' ', ''),  # Cleaned
                f"+91 {mobile}",  # With +91 and space
                f"+91{mobile}",  # With +91 no space
            ]
            query = {'$or': [
                {'_id': {'$in': mobile_formats}},
                {'mobile': {'$in': mobile_formats}},
                {'phoneNumber': {'$in': mobile_formats}}
            ]}
        elif email:
            query = {'email': email}
        
        # Find analysis document (include _id since it's now the phone number)
        analysis_doc = collection.find_one(query)
        
        if not analysis_doc:
            return jsonify({
                'success': False,
                'message': 'No analysis data found for this student'
            }), 404
        
        # Format the response
        response_data = {
            'success': True,
            'data': {
                'id': str(analysis_doc.get('_id', '')),  # Include _id (mobile number)
                'name': analysis_doc.get('name', 'N/A'),
                'email': analysis_doc.get('email', 'N/A'),
                'mobile': analysis_doc.get('mobile', 'N/A'),
                'summary': analysis_doc.get('summary', ''),
                'resume_score': analysis_doc.get('resume_score', 0),
                
                # Main analysis arrays
                'strengths': analysis_doc.get('strengths', []),
                'weaknesses': analysis_doc.get('weaknesses', []),
                'suggestions': analysis_doc.get('suggestions', []),
                'skills': split_combined_skills(analysis_doc.get('skills', [])),
                'missing_skills': split_combined_skills(analysis_doc.get('missing_skills', [])),
                'ats_tips': analysis_doc.get('ats_tips', []),
                'project_suggestions': analysis_doc.get('project_suggestions', []),
                'company_suggestions': analysis_doc.get('company_suggestions', []),
                
                # Company eligibility data
                'company_1_name': analysis_doc.get('company_1_name', ''),
                'company_1_eligible': analysis_doc.get('company_1_eligible', ''),
                'company_1_reason': analysis_doc.get('company_1_reason', ''),
                'company_2_name': analysis_doc.get('company_2_name', ''),
                'company_2_eligible': analysis_doc.get('company_2_eligible', ''),
                'company_2_reason': analysis_doc.get('company_2_reason', ''),
                'company_3_name': analysis_doc.get('company_3_name', ''),
                'company_3_eligible': analysis_doc.get('company_3_eligible', ''),
                'company_3_reason': analysis_doc.get('company_3_reason', ''),
                'company_4_name': analysis_doc.get('company_4_name', ''),
                'company_4_eligible': analysis_doc.get('company_4_eligible', ''),
                'company_4_reason': analysis_doc.get('company_4_reason', ''),
                
                # Additional fields
                'experience': analysis_doc.get('experience', 'N/A'),
                'education': analysis_doc.get('education', {}),
                'projects': analysis_doc.get('projects', []),
                'certifications': analysis_doc.get('certifications', []),
                'achievements': analysis_doc.get('achievements', []),
                'created_at': analysis_doc.get('created_at', 'N/A'),
                'updated_at': analysis_doc.get('updated_at', 'N/A'),
                'source': analysis_doc.get('source', 'N/A'),
                'analysis_version': analysis_doc.get('analysis_version', 'N/A')
            }
        }
        
        return jsonify(response_data), 200
        
    except Exception as e:
        log_error(e, {
            'endpoint': '/api/student-analysis',
            'mobile': mobile,
            'email': email
        })
        return jsonify({
            'success': False,
            'error': f'Failed to fetch student analysis: {str(e)}'
        }), 500

# Video Translation Endpoint
@app.route('/api/translate-video', methods=['POST', 'OPTIONS'])
def translate_video():
    """Endpoint to handle video translation"""
    # Handle preflight OPTIONS request
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'ok'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        return response, 200
    
    try:
        # Check if video file is present
        if 'video' not in request.files:
            return jsonify({
                'success': False,
                'error': 'No video file provided'
            }), 400
        
        video_file = request.files['video']
        target_language = request.form.get('language', 'hindi')
        
        # Validate file
        if video_file.filename == '':
            return jsonify({
                'success': False,
                'error': 'No video file selected'
            }), 400
        
        # Check file extension
        allowed_extensions = {'.mp4', '.avi', '.mov', '.mkv'}
        file_ext = os.path.splitext(video_file.filename)[1].lower()
        if file_ext not in allowed_extensions:
            return jsonify({
                'success': False,
                'error': f'Invalid file format. Allowed formats: {", ".join(allowed_extensions)}'
            }), 400
        
        # Create temporary directory for processing
        temp_dir = tempfile.mkdtemp()
        
        try:
            # Save uploaded video
            input_video_path = os.path.join(temp_dir, f"input_video{file_ext}")
            video_file.save(input_video_path)
            
            print(f"📹 Video saved: {input_video_path}")
            print(f"🌍 Target language: {target_language}")
            
            # Import video translator
            from video_translator import video_translation_pipeline
            
            # Process video translation
            output_video_path = video_translation_pipeline(
                input_video_path, 
                target_language, 
                temp_dir
            )
            
            # Read the translated video
            with open(output_video_path, 'rb') as f:
                video_data = f.read()
            
            # Save to permanent location (optional)
            output_filename = f"translated_{int(time.time())}{file_ext}"
            permanent_output_path = os.path.join('translated_videos', output_filename)
            
            # Create directory if it doesn't exist
            os.makedirs('translated_videos', exist_ok=True)
            
            # Save permanently
            with open(permanent_output_path, 'wb') as f:
                f.write(video_data)
            
            print(f"✅ Translated video saved: {permanent_output_path}")
            
            return jsonify({
                'success': True,
                'message': 'Video translated successfully',
                'video_url': f'/api/download-video/{output_filename}',
                'filename': output_filename
            }), 200
            
        finally:
            # Cleanup temporary directory
            import shutil
            try:
                shutil.rmtree(temp_dir)
                print(f"🧹 Cleaned up temp directory: {temp_dir}")
            except Exception as e:
                print(f"⚠️  Failed to cleanup temp directory: {e}")
    
    except Exception as e:
        print(f"❌ Translation error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': f'Translation failed: {str(e)}'
        }), 500

# YouTube Video Translation Endpoint
@app.route('/api/translate-youtube', methods=['POST', 'OPTIONS'])
def translate_youtube():
    """Endpoint to handle YouTube video translation"""
    # Handle preflight OPTIONS request
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'ok'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        return response, 200
    
    try:
        # Get YouTube URL from form data
        youtube_url = request.form.get('youtube_url')
        target_language = request.form.get('language', 'hindi')
        
        if not youtube_url:
            return jsonify({
                'success': False,
                'error': 'No YouTube URL provided'
            }), 400
        
        # Validate YouTube URL
        import re
        youtube_regex = r'^(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+$'
        if not re.match(youtube_regex, youtube_url):
            return jsonify({
                'success': False,
                'error': 'Invalid YouTube URL'
            }), 400
        
        print(f"🔗 YouTube URL: {youtube_url}")
        print(f"🌍 Target language: {target_language}")
        
        # Create temporary directory for processing
        temp_dir = tempfile.mkdtemp()
        
        try:
            # Import video translator with YouTube support
            from video_translator import youtube_video_translation_pipeline
            
            # Process YouTube video translation
            output_video_path = youtube_video_translation_pipeline(
                youtube_url,
                target_language,
                temp_dir
            )
            
            # Read the translated video
            with open(output_video_path, 'rb') as f:
                video_data = f.read()
            
            # Save to permanent location
            output_filename = f"translated_yt_{int(time.time())}.mp4"
            permanent_output_path = os.path.join('translated_videos', output_filename)
            
            # Create directory if it doesn't exist
            os.makedirs('translated_videos', exist_ok=True)
            
            # Save permanently
            with open(permanent_output_path, 'wb') as f:
                f.write(video_data)
            
            print(f"✅ Translated YouTube video saved: {permanent_output_path}")
            
            return jsonify({
                'success': True,
                'message': 'YouTube video translated successfully',
                'video_url': f'/api/download-video/{output_filename}',
                'filename': output_filename
            }), 200
            
        finally:
            # Cleanup temporary directory
            import shutil
            try:
                shutil.rmtree(temp_dir)
                print(f"🧹 Cleaned up temp directory: {temp_dir}")
            except Exception as e:
                print(f"⚠️  Failed to cleanup temp directory: {e}")
    
    except Exception as e:
        print(f"❌ YouTube translation error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': f'YouTube translation failed: {str(e)}'
        }), 500

@app.route('/api/download-video/<filename>', methods=['GET'])
def download_video(filename):
    """Endpoint to download translated video"""
    try:
        from flask import send_file
        
        video_path = os.path.join('translated_videos', filename)
        
        if not os.path.exists(video_path):
            return jsonify({
                'success': False,
                'error': 'Video not found'
            }), 404
        
        return send_file(
            video_path,
            mimetype='video/mp4',
            as_attachment=True,
            download_name=filename
        )
    
    except Exception as e:
        log_error(e, {
            'endpoint': '/api/download-video',
            'filename': filename
        })
        return jsonify({
            'success': False,
            'error': f'Download failed: {str(e)}'
        }), 500

# ==================== PROFILE MANAGEMENT ENDPOINTS ====================

@app.route('/api/profile/<email>', methods=['GET'])
def get_profile(email):
    """Get user profile by email, auto-fill from resume data if available"""
    try:
        db = get_db()
        profiles_col = db['user_profiles']
        resumes_col = db['resumes']
        users_col = db['users']
        
        # Find profile by email
        profile = profiles_col.find_one({'email': email})
        
        if profile:
            # Remove MongoDB _id from response
            profile.pop('_id', None)
            # Ensure editCount exists (for backward compatibility)
            if 'editCount' not in profile:
                profile['editCount'] = 0
            return jsonify({
                'success': True,
                'profile': profile,
                'profileImage': profile.get('profileImage'),
                'editCount': profile.get('editCount', 0),
                'editsRemaining': 3 - profile.get('editCount', 0)
            })
        else:
            # No profile exists, try to auto-fill from resume data
            user = users_col.find_one({'email': email})
            
            if not user:
                # User not found
                return jsonify({
                    'success': True,
                    'profile': None,
                    'profileImage': None,
                    'message': 'No profile found, create new one'
                })
            
            # Try to find resume data by email or mobile
            resume = None
            if user.get('mobile'):
                resume = resumes_col.find_one({'mobile': user['mobile']})
            
            # Build profile from user data and resume data
            auto_filled_profile = {
                'email': email,
                'fullName': '',
                'dateOfBirth': '',
                'phoneNumber': '',
                'address1': '',
                'address2': '',
                'city': '',
                'state': '',
                'pincode': '',
                'linkedinProfile': '',
                'githubProfile': '',
                'personalWebsite': '',
                'degree': '',
                'branch': '',
                'collegeName': '',
                'graduationYear': '',
                'cgpa': '',
                'hasBacklogs': False,
                'backlogCount': 0,
                'editCount': 0
            }
            
            # Fill from user data
            if user.get('firstName') and user.get('lastName'):
                auto_filled_profile['fullName'] = f"{user['firstName']} {user['lastName']}"
            elif user.get('username'):
                auto_filled_profile['fullName'] = user['username']
            
            if user.get('mobile'):
                auto_filled_profile['phoneNumber'] = user['mobile']
            
            # Fill from resume data if available
            if resume:
                print(f"🔍 Found resume data for {email}, auto-filling profile")
                
                # Basic info from resume
                if resume.get('name'):
                    auto_filled_profile['fullName'] = resume['name']
                if resume.get('phone'):
                    auto_filled_profile['phoneNumber'] = resume['phone']
                if resume.get('email'):
                    auto_filled_profile['email'] = resume['email']
                
                # Academic info from resume
                if resume.get('bachelorDegree') or resume.get('degree'):
                    auto_filled_profile['degree'] = resume.get('bachelorDegree') or resume.get('degree', '')
                if resume.get('branch'):
                    auto_filled_profile['branch'] = resume.get('branch', '')
                if resume.get('bachelorUniversity') or resume.get('university'):
                    auto_filled_profile['collegeName'] = resume.get('bachelorUniversity') or resume.get('university', '')
                if resume.get('bachelorCGPA') or resume.get('cgpa'):
                    cgpa_value = resume.get('bachelorCGPA') or resume.get('cgpa', '')
                    auto_filled_profile['cgpa'] = str(cgpa_value) if cgpa_value else ''
                if resume.get('graduationYear'):
                    auto_filled_profile['graduationYear'] = str(resume.get('graduationYear', ''))
            
            return jsonify({
                'success': True,
                'profile': auto_filled_profile,
                'profileImage': None,
                'autoFilled': True,
                'editCount': 0,
                'editsRemaining': 3,
                'message': 'Profile auto-filled from resume data' if resume else 'No resume data found'
            })
            
    except Exception as e:
        print(f"💥 Error fetching profile: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'Error fetching profile: {str(e)}'
        }), 500

@app.route('/api/profile/update', methods=['POST'])
def update_profile():
    """Update or create user profile with image upload support"""
    try:
        import base64
        from werkzeug.utils import secure_filename
        
        print("🔵 Profile update request received")
        print(f"📧 Email from form: {request.form.get('email')}")
        print(f"📝 Form data keys: {list(request.form.keys())}")
        
        db = get_db()
        profiles_col = db['user_profiles']
        
        # Get form data
        email = request.form.get('email')
        
        if not email:
            print("❌ No email provided")
            return jsonify({
                'success': False,
                'message': 'Email is required'
            }), 400
        
        # Check if profile exists and get current edit count
        existing_profile = profiles_col.find_one({'email': email})
        current_edit_count = existing_profile.get('editCount', 0) if existing_profile else 0
        
        # Check if edit limit reached (only for existing profiles)
        if existing_profile and current_edit_count >= 3:
            print(f"❌ Edit limit reached for {email}. Current count: {current_edit_count}")
            return jsonify({
                'success': False,
                'message': 'Profile edit limit reached. You can only edit your profile 3 times.',
                'editLimitReached': True,
                'editCount': current_edit_count
            }), 403
        
        # Build profile data from form
        # Increment edit count (for new profiles, start at 1; for existing, increment)
        new_edit_count = current_edit_count + 1
        
        profile_data = {
            'email': email,
            'fullName': request.form.get('fullName', ''),
            'dateOfBirth': request.form.get('dateOfBirth', ''),
            'phoneNumber': request.form.get('phoneNumber', ''),
            'address1': request.form.get('address1', ''),
            'address2': request.form.get('address2', ''),
            'city': request.form.get('city', ''),
            'state': request.form.get('state', ''),
            'pincode': request.form.get('pincode', ''),
            'linkedinProfile': request.form.get('linkedinProfile', ''),
            'githubProfile': request.form.get('githubProfile', ''),
            'personalWebsite': request.form.get('personalWebsite', ''),
            'degree': request.form.get('degree', ''),
            'branch': request.form.get('branch', ''),
            'collegeName': request.form.get('collegeName', ''),
            'graduationYear': request.form.get('graduationYear', ''),
            'cgpa': request.form.get('cgpa', ''),
            'hasBacklogs': request.form.get('hasBacklogs', 'false') == 'true',
            'backlogCount': int(request.form.get('backlogCount', 0)),
            'editCount': new_edit_count,
            'updatedAt': datetime.now().isoformat()
        }
        
        print(f"💾 Saving profile data: {profile_data}")
        
        # Handle profile image upload
        if 'profileImage' in request.files:
            file = request.files['profileImage']
            if file and file.filename:
                print(f"📷 Processing profile image: {file.filename}")
                # Read file and convert to base64
                image_data = file.read()
                base64_image = base64.b64encode(image_data).decode('utf-8')
                # Store with data URI prefix
                file_ext = secure_filename(file.filename).split('.')[-1].lower()
                mime_type = f'image/{file_ext}' if file_ext in ['png', 'jpg', 'jpeg', 'gif'] else 'image/jpeg'
                profile_data['profileImage'] = f'data:{mime_type};base64,{base64_image}'
        
        # Update or insert profile
        result = profiles_col.update_one(
            {'email': email},
            {'$set': profile_data},
            upsert=True
        )
        
        print(f"✅ Profile saved successfully. Modified: {result.modified_count}, Upserted: {result.upserted_id}")
        print(f"📊 Edit count: {new_edit_count}/3")
        
        return jsonify({
            'success': True,
            'message': 'Profile saved successfully',
            'modified': result.modified_count > 0 or result.upserted_id is not None,
            'editCount': new_edit_count,
            'editsRemaining': 3 - new_edit_count
        })
        
    except Exception as e:
        print(f"💥 Error updating profile: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'Error updating profile: {str(e)}'
        }), 500

@app.route('/api/profile/completion/<email>', methods=['GET'])
def get_profile_completion(email):
    """Calculate and return profile completion percentage"""
    try:
        db = get_db()
        profiles_col = db['user_profiles']
        
        profile = profiles_col.find_one({'email': email})
        
        if not profile:
            return jsonify({
                'success': True,
                'completionPercentage': 0,
                'missingFields': [
                    'Full Name', 'Email', 'Phone Number', 'Location',
                    'Degree', 'Branch/Specialization', 'College Name',
                    'Year of Graduation', 'CGPA/Percentage'
                ]
            })
        
        # Define required fields for completion
        required_fields = {
            'fullName': 'Full Name',
            'email': 'Email',
            'phoneNumber': 'Phone Number',
            'location': 'Location',
            'degree': 'Degree',
            'branch': 'Branch/Specialization',
            'collegeName': 'College Name',
            'graduationYear': 'Year of Graduation',
            'cgpa': 'CGPA/Percentage'
        }
        
        filled_fields = 0
        missing_fields = []
        
        for field_key, field_label in required_fields.items():
            if profile.get(field_key) and str(profile.get(field_key)).strip():
                filled_fields += 1
            else:
                missing_fields.append(field_label)
        
        completion_percentage = round((filled_fields / len(required_fields)) * 100)
        
        return jsonify({
            'success': True,
            'completionPercentage': completion_percentage,
            'missingFields': missing_fields,
            'totalFields': len(required_fields),
            'filledFields': filled_fields
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error calculating profile completion: {str(e)}'
        }), 500

# ==================== END PROFILE MANAGEMENT ====================

# ==================== LOADING QUESTIONS & FACTS ====================

@app.route('/api/loading/random', methods=['GET'])
def get_random_loading_content():
    """Get a random question or fact for loading screens"""
    try:
        db = get_db()
        content_type = request.args.get('type', 'mixed')  # 'question', 'fact', or 'mixed'
        exclude_ids = request.args.get('exclude', '')  # comma-separated IDs to exclude
        
        exclude_list = [x.strip() for x in exclude_ids.split(',') if x.strip()]
        
        result = None
        
        if content_type == 'question' or (content_type == 'mixed' and random.random() < 0.6):
            # 60% chance of question in mixed mode
            questions_col = db['loading_questions']
            
            # Get random question (no context filtering)
            pipeline = [
                {'$match': {'active': True}},
            ]
            if exclude_list:
                pipeline[0]['$match']['question_id'] = {'$nin': exclude_list}
            pipeline.append({'$sample': {'size': 1}})
            
            print(f"🔍 Loading questions pipeline: {pipeline}")
            docs = list(questions_col.aggregate(pipeline))
            print(f"🔍 Found {len(docs)} question(s)")
            
            if docs:
                doc = docs[0]
                result = {
                    'type': 'question',
                    'id': doc.get('question_id'),
                    'category': doc.get('category'),
                    'text': doc.get('question_text'),
                    'icon': doc.get('icon_emoji', '❓'),
                    'options': doc.get('options', []),
                    'questionType': doc.get('question_type', 'single_choice')
                }
        
        if not result:
            # Get a random fact (no context filtering)
            facts_col = db['loading_facts']
            
            pipeline = [
                {'$match': {'active': True}},
            ]
            if exclude_list:
                pipeline[0]['$match']['fact_id'] = {'$nin': exclude_list}
            pipeline.append({'$sample': {'size': 1}})
            
            print(f"🔍 Loading facts pipeline: {pipeline}")
            docs = list(facts_col.aggregate(pipeline))
            print(f"🔍 Found {len(docs)} fact(s)")
            
            if docs:
                doc = docs[0]
                result = {
                    'type': 'fact',
                    'id': doc.get('fact_id'),
                    'category': doc.get('category'),
                    'text': doc.get('fact_text'),
                    'icon': doc.get('icon', '💡')
                }
        
        if not result:
            # Fallback content
            result = {
                'type': 'fact',
                'id': 'default',
                'category': 'motivation',
                'text': '🚀 Your career journey is loading... Great things take time!',
                'icon': '🚀'
            }
        
        return jsonify({'success': True, 'data': result})
        
    except Exception as e:
        print(f"Error fetching loading content: {e}")
        return jsonify({
            'success': True,
            'data': {
                'type': 'fact',
                'id': 'error_fallback',
                'category': 'motivation',
                'text': '⚡ Preparing something amazing for you...',
                'icon': '⚡'
            }
        })


@app.route('/api/loading/respond', methods=['POST'])
def save_loading_question_response():
    """Save user's response to a loading screen question"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        question_id = data.get('questionId')
        phone = data.get('phone') or data.get('mobile')
        selected_option = data.get('selectedOption')
        
        if not question_id or not phone or not selected_option:
            return jsonify({
                'success': False,
                'error': 'Missing required fields: questionId, phone, selectedOption'
            }), 400
        
        # Normalize phone number
        phone_digits = normalize_phone(phone)
        phone_formatted = format_phone_id(phone_digits) if phone_digits else phone
        
        db = get_db()
        responses_col = db['loading_question_responses']
        
        # Save the response
        response_doc = {
            'question_id': question_id,
            'phone': phone_formatted,
            'selected_option_id': selected_option.get('option_id') if isinstance(selected_option, dict) else selected_option,
            'selected_option_text': selected_option.get('text') if isinstance(selected_option, dict) else None,
            'coupon_category': selected_option.get('coupon_category') if isinstance(selected_option, dict) else None,
            'responded_at': datetime.now(),
            'context': data.get('context', 'unknown')
        }
        
        # Upsert - update if same question answered again
        result = responses_col.update_one(
            {'question_id': question_id, 'phone': phone_formatted},
            {'$set': response_doc},
            upsert=True
        )
        
        return jsonify({
            'success': True,
            'message': 'Response saved',
            'upserted': result.upserted_id is not None
        })
        
    except Exception as e:
        print(f"Error saving loading response: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/loading/batch', methods=['GET'])
def get_batch_loading_content():
    """Get multiple questions/facts at once for smoother loading experience"""
    try:
        db = get_db()
        count = min(int(request.args.get('count', 5)), 10)  # Max 10
        content_type = request.args.get('type', 'mixed')
        
        items = []
        
        # Get questions
        if content_type in ['question', 'mixed']:
            questions_col = db['loading_questions']
            q_count = count if content_type == 'question' else count // 2 + 1
            q_docs = list(questions_col.aggregate([
                {'$match': {'active': True}},
                {'$sample': {'size': q_count}}
            ]))
            for doc in q_docs:
                items.append({
                    'type': 'question',
                    'id': doc.get('question_id'),
                    'category': doc.get('category'),
                    'text': doc.get('question_text'),
                    'icon': doc.get('icon_emoji', '❓'),
                    'options': doc.get('options', []),
                    'questionType': doc.get('question_type', 'single_choice')
                })
        
        # Get facts
        if content_type in ['fact', 'mixed']:
            facts_col = db['loading_facts']
            f_count = count if content_type == 'fact' else count // 2
            f_docs = list(facts_col.aggregate([
                {'$match': {'active': True}},
                {'$sample': {'size': f_count}}
            ]))
            for doc in f_docs:
                items.append({
                    'type': 'fact',
                    'id': doc.get('fact_id'),
                    'category': doc.get('category'),
                    'text': doc.get('fact_text'),
                    'icon': doc.get('icon', '💡')
                })
        
        # Shuffle for mixed content
        if content_type == 'mixed':
            random.shuffle(items)
        
        return jsonify({'success': True, 'data': items[:count]})
        
    except Exception as e:
        print(f"Error fetching batch loading content: {e}")
        return jsonify({'success': True, 'data': []})

# ==================== END LOADING QUESTIONS & FACTS ====================

def ensure_loading_content_populated():
    """Ensure loading questions and facts are populated in the database"""
    try:
        db = get_db()
        questions_count = db['loading_questions'].count_documents({})
        facts_count = db['loading_facts'].count_documents({})
        
        if questions_count == 0 or facts_count == 0:
            print("📝 Populating loading questions and facts...")
            import subprocess
            result = subprocess.run(
                [sys.executable, 'populate_loading_questions.py'],
                cwd=os.path.dirname(os.path.abspath(__file__)),
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                print("✅ Loading content populated successfully!")
            else:
                print(f"⚠️ Warning: Could not populate loading content: {result.stderr}")
        else:
            print(f"✅ Loading content ready: {questions_count} questions, {facts_count} facts")
    except Exception as e:
        print(f"⚠️ Warning: Could not check loading content: {e}")

# ============================================================================
# RAZORPAY PAYMENT INTEGRATION
# ============================================================================

@app.route('/api/payment/create-order', methods=['POST', 'OPTIONS'])
def create_razorpay_order():
    """
    Create a Razorpay order for payment
    
    Expected payload:
    {
        "amount": 50000,  # Amount in paise (50000 = ₹500)
        "currency": "INR",
        "receipt": "receipt#1",
        "notes": {
            "mobile": "+91XXXXXXXXXX",
            "name": "Student Name",
            "purpose": "Premium Subscription"
        }
    }
    """
    if request.method == 'OPTIONS':
        return jsonify({'status': 'ok'}), 200
    
    try:
        if not razorpay_client:
            error_msg = 'Payment gateway not configured. Please contact support.'
            print(f"❌ PAYMENT ERROR: {error_msg}")
            return jsonify({
                'success': False,
                'message': error_msg
            }), 500
        
        data = request.get_json()
        
        if not data:
            error_msg = 'No data provided in request'
            print(f"❌ PAYMENT ERROR: {error_msg}")
            return jsonify({
                'success': False,
                'message': 'Invalid request data'
            }), 400
        
        # Validate required fields
        amount = data.get('amount')
        if not amount or amount <= 0:
            error_msg = f'Invalid amount: {amount}'
            print(f"❌ PAYMENT ERROR: {error_msg}")
            return jsonify({
                'success': False,
                'message': 'Valid amount is required (must be greater than 0)'
            }), 400
        
        # Log payment request
        mobile = data.get('notes', {}).get('mobile', 'Unknown')
        plan_name = data.get('notes', {}).get('plan_name', 'Unknown')
        print(f"\n{'='*60}")
        print(f"💳 NEW PAYMENT REQUEST")
        print(f"{'='*60}")
        print(f"Mobile: {mobile}")
        print(f"Plan: {plan_name}")
        print(f"Amount: ₹{amount/100:.2f}")
        print(f"Timestamp: {datetime.now().isoformat()}")
        print(f"{'='*60}\n")
        
        # Create order data
        order_data = {
            'amount': int(amount),  # Amount in paise
            'currency': data.get('currency', 'INR'),
            'receipt': data.get('receipt', f'receipt_{int(time.time())}'),
            'notes': data.get('notes', {})
        }
        
        # Create order using Razorpay client
        try:
            print("🔄 Attempting to create Razorpay order...")
            print(f"API Endpoint: https://api.razorpay.com/v1/orders")
            order = razorpay_client.order.create(data=order_data)
            print(f"✅ Razorpay order created successfully: {order['id']}")
        except requests.exceptions.ConnectionError as conn_error:
            error_msg = f"Network connection error: {str(conn_error)}"
            print(f"❌ PAYMENT ERROR: {error_msg}")
            print("\n⚠️  TROUBLESHOOTING TIPS:")
            print("1. Check your internet connection")
            print("2. Verify DNS settings (try using 8.8.8.8 or 1.1.1.1)")
            print("3. Check if api.razorpay.com is accessible")
            print("4. Disable VPN/Proxy if enabled")
            print("5. Check firewall settings")
            import traceback
            traceback.print_exc()
            return jsonify({
                'success': False,
                'message': 'Unable to connect to payment gateway. Please check your internet connection and try again.',
                'error_type': 'connection_error'
            }), 503
        except Exception as razorpay_error:
            error_msg = f"Razorpay API error: {str(razorpay_error)}"
            print(f"❌ PAYMENT ERROR: {error_msg}")
            import traceback
            traceback.print_exc()
            return jsonify({
                'success': False,
                'message': 'Failed to create payment order. Please try again.'
            }), 500
        
        # Save order to database
        try:
            db = get_db()
            payments_collection = db['payments']
            
            payment_doc = {
                'order_id': order['id'],
                'amount': order['amount'],
                'currency': order['currency'],
                'receipt': order['receipt'],
                'status': 'created',
                'notes': order_data.get('notes', {}),
                'mobile': normalize_phone(mobile) if mobile != 'Unknown' else None,
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow(),
                'payment_attempts': []
            }
            
            payments_collection.insert_one(payment_doc)
            print(f"💾 Payment record saved to database")
            
        except Exception as db_error:
            error_msg = f"Database error: {str(db_error)}"
            print(f"⚠️ WARNING: {error_msg}")
            import traceback
            traceback.print_exc()
            # Continue even if DB save fails
        
        return jsonify({
            'success': True,
            'data': {
                'order_id': order['id'],
                'amount': order['amount'],
                'currency': order['currency'],
                'key_id': razorpay_key_id  # Send key_id for frontend
            }
        })
        
    except Exception as e:
        error_msg = f"Unexpected error in create_razorpay_order: {str(e)}"
        print(f"\n❌ CRITICAL PAYMENT ERROR: {error_msg}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': 'An unexpected error occurred. Please try again later.'
        }), 500


@app.route('/api/payment/verify', methods=['POST', 'OPTIONS'])
def verify_razorpay_payment():
    """
    Verify Razorpay payment signature
    
    Expected payload:
    {
        "razorpay_order_id": "order_xxxxx",
        "razorpay_payment_id": "pay_xxxxx",
        "razorpay_signature": "signature_xxxxx",
        "mobile": "+91XXXXXXXXXX"  # Optional, for linking to user
    }
    """
    if request.method == 'OPTIONS':
        return jsonify({'status': 'ok'}), 200
    
    try:
        if not razorpay_client:
            return jsonify({
                'success': False,
                'message': 'Payment gateway not configured'
            }), 500
        
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'message': 'No data provided'
            }), 400
        
        # Get payment details
        order_id = data.get('razorpay_order_id')
        payment_id = data.get('razorpay_payment_id')
        signature = data.get('razorpay_signature')
        
        if not all([order_id, payment_id, signature]):
            return jsonify({
                'success': False,
                'message': 'Missing payment details'
            }), 400
        
        print(f"🔐 Verifying payment: {payment_id} for order: {order_id}")
        
        # Verify signature
        params_dict = {
            'razorpay_order_id': order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': signature
        }
        
        try:
            razorpay_client.utility.verify_payment_signature(params_dict)
            
            print(f"\n{'='*60}")
            print(f"✅ PAYMENT VERIFICATION SUCCESSFUL")
            print(f"{'='*60}")
            print(f"Order ID: {order_id}")
            print(f"Payment ID: {payment_id}")
            print(f"Timestamp: {datetime.utcnow().isoformat()}")
            print(f"{'='*60}\n")
            
            # Update payment status in database
            try:
                db = get_db()
                payments_collection = db['payments']
                
                # Get original payment record
                payment_record = payments_collection.find_one({'order_id': order_id})
                
                update_data = {
                    'payment_id': payment_id,
                    'signature': signature,
                    'status': 'success',
                    'verified_at': datetime.utcnow(),
                    'updated_at': datetime.utcnow()
                }
                
                # Add mobile if provided
                mobile = data.get('mobile')
                if mobile:
                    update_data['mobile'] = normalize_phone(mobile)
                
                payments_collection.update_one(
                    {'order_id': order_id},
                    {
                        '$set': update_data,
                        '$push': {
                            'payment_attempts': {
                                'timestamp': datetime.utcnow(),
                                'status': 'success',
                                'payment_id': payment_id
                            }
                        }
                    }
                )
                
                print(f"💾 Payment status updated to SUCCESS in database")
                
            except Exception as db_error:
                error_msg = f"Database update error: {str(db_error)}"
                print(f"⚠️ WARNING: {error_msg}")
                import traceback
                traceback.print_exc()
            
            return jsonify({
                'success': True,
                'message': 'Payment verified successfully',
                'status': 'success',
                'data': {
                    'order_id': order_id,
                    'payment_id': payment_id,
                    'status': 'success'
                }
            })
            
        except razorpay.errors.SignatureVerificationError as sig_error:
            print(f"\n{'='*60}")
            print(f"❌ PAYMENT VERIFICATION FAILED")
            print(f"{'='*60}")
            print(f"Order ID: {order_id}")
            print(f"Payment ID: {payment_id}")
            print(f"Error: Signature verification failed")
            print(f"Timestamp: {datetime.utcnow().isoformat()}")
            print(f"{'='*60}\n")
            
            # Update payment status as failed
            try:
                db = get_db()
                payments_collection = db['payments']
                payments_collection.update_one(
                    {'order_id': order_id},
                    {
                        '$set': {
                            'status': 'failed',
                            'payment_id': payment_id,
                            'signature': signature,
                            'error': 'Signature verification failed',
                            'error_details': str(sig_error),
                            'failed_at': datetime.utcnow(),
                            'updated_at': datetime.utcnow()
                        },
                        '$push': {
                            'payment_attempts': {
                                'timestamp': datetime.utcnow(),
                                'status': 'failed',
                                'error': 'Signature verification failed',
                                'payment_id': payment_id
                            }
                        }
                    }
                )
                print(f"💾 Failed payment logged in database")
            except Exception as db_error:
                error_msg = f"Failed to log payment failure: {str(db_error)}"
                print(f"⚠️ WARNING: {error_msg}")
            
            return jsonify({
                'success': False,
                'message': 'Payment verification failed. Please contact support if amount was deducted.',
                'error': 'signature_verification_failed'
            }), 400
        
    except Exception as e:
        print(f"❌ Error verifying payment: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'Error verifying payment: {str(e)}'
        }), 500


@app.route('/api/payment/status/<order_id>', methods=['GET'])
def get_payment_status(order_id):
    """
    Get payment status from database
    """
    try:
        db = get_db()
        payments_collection = db['payments']
        
        payment = payments_collection.find_one({'order_id': order_id})
        
        if not payment:
            return jsonify({
                'success': False,
                'message': 'Payment not found'
            }), 404
        
        # Remove MongoDB _id from response
        payment.pop('_id', None)
        
        return jsonify({
            'success': True,
            'data': payment
        })
        
    except Exception as e:
        print(f"❌ Error fetching payment status: {e}")
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500


@app.route('/api/payment/user-payments/<mobile>', methods=['GET'])
def get_user_payments(mobile):
    """
    Get all payments for a user
    """
    try:
        normalized_mobile = normalize_phone(mobile)
        
        db = get_db()
        payments_collection = db['payments']
        
        payments = list(payments_collection.find(
            {'mobile': normalized_mobile}
        ).sort('created_at', -1))
        
        # Remove MongoDB _id from responses
        for payment in payments:
            payment.pop('_id', None)
        
        return jsonify({
            'success': True,
            'data': {
                'mobile': normalized_mobile,
                'payments': payments,
                'total_payments': len(payments)
            }
        })
        
    except Exception as e:
        print(f"❌ Error fetching user payments: {e}")
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500


@app.route('/api/payment/failure', methods=['POST', 'OPTIONS'])
def handle_payment_failure():
    """
    Log payment failure details
    
    Expected payload:
    {
        "order_id": "order_xxxxx",
        "error": {
            "code": "BAD_REQUEST_ERROR",
            "description": "Payment failed",
            "reason": "payment_failed",
            "step": "payment_authentication",
            "source": "customer"
        },
        "mobile": "+91XXXXXXXXXX"
    }
    """
    if request.method == 'OPTIONS':
        return jsonify({'status': 'ok'}), 200
    
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'message': 'No data provided'
            }), 400
        
        order_id = data.get('order_id')
        error_details = data.get('error', {})
        mobile = data.get('mobile')
        
        print(f"\n{'='*60}")
        print(f"❌ PAYMENT FAILURE REPORTED")
        print(f"{'='*60}")
        print(f"Order ID: {order_id}")
        print(f"Error Code: {error_details.get('code', 'Unknown')}")
        print(f"Description: {error_details.get('description', 'Unknown')}")
        print(f"Reason: {error_details.get('reason', 'Unknown')}")
        print(f"Step: {error_details.get('step', 'Unknown')}")
        print(f"Source: {error_details.get('source', 'Unknown')}")
        print(f"Mobile: {mobile or 'Unknown'}")
        print(f"Timestamp: {datetime.utcnow().isoformat()}")
        print(f"{'='*60}\n")
        
        # Log failure to database
        try:
            db = get_db()
            payments_collection = db['payments']
            
            failure_log = {
                'error_code': error_details.get('code'),
                'error_description': error_details.get('description'),
                'error_reason': error_details.get('reason'),
                'error_step': error_details.get('step'),
                'error_source': error_details.get('source'),
                'metadata': error_details.get('metadata', {}),
                'timestamp': datetime.utcnow()
            }
            
            update_result = payments_collection.update_one(
                {'order_id': order_id},
                {
                    '$set': {
                        'status': 'failed',
                        'error_details': failure_log,
                        'failed_at': datetime.utcnow(),
                        'updated_at': datetime.utcnow()
                    },
                    '$push': {
                        'payment_attempts': {
                            'timestamp': datetime.utcnow(),
                            'status': 'failed',
                            'error': error_details.get('description', 'Payment failed')
                        }
                    }
                }
            )
            
            if update_result.modified_count > 0:
                print(f"💾 Payment failure logged in database")
            else:
                print(f"⚠️ No payment record found for order: {order_id}")
            
        except Exception as db_error:
            error_msg = f"Database error while logging failure: {str(db_error)}"
            print(f"⚠️ WARNING: {error_msg}")
            import traceback
            traceback.print_exc()
        
        return jsonify({
            'success': True,
            'message': 'Payment failure logged'
        })
        
    except Exception as e:
        error_msg = f"Error handling payment failure: {str(e)}"
        print(f"❌ ERROR: {error_msg}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': error_msg
        }), 500


@app.route('/api/payment/receipt/<order_id>', methods=['GET'])
def generate_receipt(order_id):
    """
    Generate payment receipt/invoice
    
    Returns JSON with receipt details that can be used to generate PDF
    """
    try:
        db = get_db()
        payments_collection = db['payments']
        
        payment = payments_collection.find_one({'order_id': order_id})
        
        if not payment:
            return jsonify({
                'success': False,
                'message': 'Payment not found'
            }), 404
        
        if payment.get('status') != 'success':
            return jsonify({
                'success': False,
                'message': 'Receipt only available for successful payments'
            }), 400
        
        # Get user details
        mobile = payment.get('mobile', 'N/A')
        notes = payment.get('notes', {})
        user_name = notes.get('name', 'Customer')
        plan_name = notes.get('plan_name', 'Subscription')
        
        # Calculate amounts
        amount_paise = payment.get('amount', 0)
        amount_rupees = amount_paise / 100
        gst_rate = 0.18  # 18% GST
        base_amount = amount_rupees / (1 + gst_rate)
        gst_amount = amount_rupees - base_amount
        
        # Generate receipt data
        receipt_data = {
            'receipt_number': payment.get('receipt', f"RCP-{order_id}"),
            'invoice_number': f"INV-{datetime.utcnow().strftime('%Y%m%d')}-{order_id[-8:]}",
            'date': payment.get('verified_at', payment.get('created_at')).strftime('%d %B %Y'),
            'time': payment.get('verified_at', payment.get('created_at')).strftime('%I:%M %p'),
            
            # Customer details
            'customer': {
                'name': user_name,
                'mobile': mobile,
                'email': notes.get('email', 'N/A')
            },
            
            # Payment details
            'payment': {
                'order_id': order_id,
                'payment_id': payment.get('payment_id', 'N/A'),
                'method': 'Razorpay',
                'status': 'PAID'
            },
            
            # Item details
            'items': [
                {
                    'description': f'{plan_name} Subscription',
                    'quantity': 1,
                    'unit_price': round(base_amount, 2),
                    'amount': round(base_amount, 2)
                }
            ],
            
            # Amount breakdown
            'amounts': {
                'subtotal': round(base_amount, 2),
                'gst': round(gst_amount, 2),
                'gst_rate': '18%',
                'total': round(amount_rupees, 2),
                'currency': payment.get('currency', 'INR')
            },
            
            # Company details
            'company': {
                'name': 'Placement AI',
                'address': 'India',
                'email': 'support@placementai.com',
                'website': 'www.placementai.com',
                'gstin': 'XXXXXXXXXXXXXXX'  # Add actual GSTIN if available
            },
            
            # Terms
            'terms': [
                'This is a computer-generated receipt.',
                'No signature required.',
                'For queries, contact support@placementai.com'
            ]
        }
        
        print(f"📄 Receipt generated for order: {order_id}")
        
        return jsonify({
            'success': True,
            'data': receipt_data
        })
        
    except Exception as e:
        error_msg = f"Error generating receipt: {str(e)}"
        print(f"❌ ERROR: {error_msg}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': error_msg
        }), 500


@app.route('/api/payment/analytics', methods=['GET'])
def payment_analytics():
    """
    Get payment analytics (admin endpoint)
    """
    try:
        db = get_db()
        payments_collection = db['payments']
        
        # Get date range from query params (default: last 30 days)
        days = int(request.args.get('days', 30))
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Aggregate payment stats
        pipeline = [
            {
                '$match': {
                    'created_at': {'$gte': start_date}
                }
            },
            {
                '$group': {
                    '_id': '$status',
                    'count': {'$sum': 1},
                    'total_amount': {'$sum': '$amount'}
                }
            }
        ]
        
        results = list(payments_collection.aggregate(pipeline))
        
        # Format results
        stats = {
            'period_days': days,
            'start_date': start_date.isoformat(),
            'end_date': datetime.utcnow().isoformat(),
            'summary': {}
        }
        
        for result in results:
            status = result['_id']
            stats['summary'][status] = {
                'count': result['count'],
                'total_amount': result['total_amount'] / 100,  # Convert to rupees
                'currency': 'INR'
            }
        
        # Calculate success rate
        total_count = sum(s['count'] for s in stats['summary'].values())
        success_count = stats['summary'].get('success', {}).get('count', 0)
        stats['success_rate'] = round((success_count / total_count * 100), 2) if total_count > 0 else 0
        
        print(f"📊 Payment analytics generated for last {days} days")
        
        return jsonify({
            'success': True,
            'data': stats
        })
        
    except Exception as e:
        error_msg = f"Error generating analytics: {str(e)}"
        print(f"❌ ERROR: {error_msg}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': error_msg
        }), 500


# ==================================================================================
# SKILL MANAGEMENT & ROADMAP ANALYSIS ENDPOINTS
# ==================================================================================
# These endpoints handle skill progression based on roadmap analysis

@app.route('/api/update-resume-skills-from-test', methods=['POST'])
def update_resume_skills_from_test():
    """
    Update resume skills after completing a weekly test
    Adds tested skills to the user's resume if they're not already present
    
    Request body:
    {
        "mobile": "+91 8864862270",
        "testSkills": ["Python", "Machine Learning", "NLP"]  // skills tested in the weekly test
    }
    """
    try:
        data = request.get_json()
        
        mobile = data.get('mobile')
        test_skills = data.get('testSkills', [])
        
        if not mobile:
            return jsonify({
                'success': False,
                'error': 'Mobile number is required'
            }), 400
        
        if not test_skills or len(test_skills) == 0:
            return jsonify({
                'success': False,
                'error': 'No skills provided'
            }), 400
        
        mobile = mobile.strip()
        
        print(f"\n{'='*60}")
        print(f"📝 UPDATE RESUME SKILLS FROM WEEKLY TEST")
        print(f"{'='*60}")
        print(f"📱 Mobile: {mobile}")
        print(f"🎯 Test Skills: {test_skills}")
        print(f"{'='*60}\n")
        
        # Get MongoDB connection
        mongo_uri = os.getenv('MONGO_URI') or os.getenv('MONGODB_URI')
        if not mongo_uri:
            return jsonify({
                'success': False,
                'error': 'MongoDB URI not configured'
            }), 500
        
        client = MongoClient(mongo_uri)
        db = client[os.getenv("MONGODB_DB", "Placement_Ai")]
        resume_col = db['resume']
        
        # Normalize mobile number for searching
        phone_digits = normalize_phone(mobile)
        
        # Build search variants
        variants = []
        if phone_digits:
            # Try with +91 prefix
            variants.append(f"+91 {phone_digits}")
            # Try without prefix
            variants.append(phone_digits)
            # Try with spaces removed
            variants.append(phone_digits.replace(' ', ''))
        # Also try original format
        variants.append(mobile)
        variants.append(mobile.replace(' ', ''))
        
        # Remove duplicates while preserving order
        unique_variants = []
        for v in variants:
            if v not in unique_variants:
                unique_variants.append(v)
        
        print(f"🔍 Searching for resume with variants: {unique_variants}")
        
        # Find user's resume
        resume_doc = None
        for variant in unique_variants:
            # Try mobile field
            resume_doc = resume_col.find_one({'mobile': variant})
            if resume_doc:
                print(f"✅ Found resume by mobile field: {variant}")
                break
            # Try phone field as fallback
            resume_doc = resume_col.find_one({'phone': variant})
            if resume_doc:
                print(f"✅ Found resume by phone field: {variant}")
                break
        
        if not resume_doc:
            return jsonify({
                'success': False,
                'error': 'Resume not found for this mobile number'
            }), 404
        
        # Get current skills from resume
        current_skills = resume_doc.get('skills', [])
        if not isinstance(current_skills, list):
            current_skills = []
        
        print(f"📋 Current skills: {current_skills}")
        
        # Add new skills that aren't already present (case-insensitive check)
        current_skills_lower = [str(s).lower() for s in current_skills]
        new_skills_added = []
        
        for skill in test_skills:
            if skill and str(skill).lower() not in current_skills_lower:
                current_skills.append(skill)
                new_skills_added.append(skill)
                current_skills_lower.append(str(skill).lower())
        
        if new_skills_added:
            # Update resume with new skills
            result = resume_col.update_one(
                {'_id': resume_doc['_id']},
                {'$set': {'skills': current_skills}}
            )
            
            print(f"✅ Added {len(new_skills_added)} new skills: {new_skills_added}")
            print(f"📊 Updated skills list: {current_skills}")
            
            return jsonify({
                'success': True,
                'message': f'Successfully added {len(new_skills_added)} new skill(s) to resume',
                'skillsAdded': new_skills_added,
                'totalSkills': len(current_skills)
            }), 200
        else:
            print(f"ℹ️ No new skills to add - all test skills already in resume")
            return jsonify({
                'success': True,
                'message': 'All test skills already present in resume',
                'skillsAdded': [],
                'totalSkills': len(current_skills)
            }), 200
        
    except Exception as e:
        print(f"❌ Error updating resume skills: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/check-skill-completion-with-ai', methods=['POST'])
def check_skill_completion_with_ai():
    """
    Check if skills should be moved from 'Skills You Can Develop' to 'Skills & Expertise'
    based on pre-analyzed roadmap mapping.
    
    When roadmap is generated, AI determines which skills complete at which weeks.
    This endpoint checks that mapping and moves skills when the corresponding week test is completed.
    
    Request body:
    {
        "mobile": "+91 8864862270",
        "weekNumber": 2,
        "monthNumber": 1
    }
    
    Returns:
    {
        "success": true,
        "skillsCompleted": ["NLP", "Excel"],
        "skillsMoved": ["NLP"],
        "message": "2 skills completed this week"
    }
    """
    try:
        data = request.get_json()
        
        mobile = data.get('mobile')
        week_number = data.get('weekNumber')
        month_number = data.get('monthNumber')
        
        # Validation
        if not mobile or not week_number or not month_number:
            return jsonify({
                'success': False,
                'error': 'Mobile, weekNumber, and monthNumber are required'
            }), 400
        
        # Normalize week number: Convert cumulative week (5-8 for month 2) to per-month week (1-4)
        # If week > 4, it's cumulative - convert it to 1-4 per month
        if week_number > 4:
            # Cumulative week system: Month 1 = weeks 1-4, Month 2 = weeks 5-8, etc.
            normalized_week = ((week_number - 1) % 4) + 1
            print(f"⚠️ Week {week_number} is cumulative, normalizing to {normalized_week} for Month {month_number}")
            week_number = normalized_week
        
        print(f"\n{'='*60}")
        print(f"🎯 SKILL COMPLETION CHECK (ROADMAP-BASED)")
        print(f"{'='*60}")
        print(f"📱 Mobile: {mobile}")
        print(f"📅 Month {month_number}, Week {week_number}")
        print(f"{'='*60}\n")
        
        # Get MongoDB connection
        mongo_uri = os.getenv('MONGO_URI') or os.getenv('MONGODB_URI')
        if not mongo_uri:
            return jsonify({
                'success': False,
                'error': 'MongoDB URI not configured'
            }), 500
        
        client = MongoClient(mongo_uri)
        db = client[os.getenv("MONGODB_DB", "Placement_Ai")]
        resume_col = db['Resume']  # Fixed: Capital R
        mapping_col = db['skill_week_mapping']
        
        # Normalize mobile to last 10 digits for mapping lookup
        clean_mobile = ''.join(filter(str.isdigit, str(mobile)))
        mobile_id = clean_mobile[-10:]  # Last 10 digits for skill_week_mapping
        
        mapping_doc = mapping_col.find_one({'_id': mobile_id})
        
        if not mapping_doc:
            print(f"⚠️ No skill-week mapping found for user {mobile_id}")
            print(f"🔧 Attempting to auto-generate mappings from roadmap...")
            
            # Try to auto-generate mappings from Roadmap_Dashboard
            try:
                roadmap_col = db['Roadmap_Dashboard ']  # Note: trailing space
                
                # Find user's roadmap
                mobile_formats = [
                    mobile,
                    f"+91 {clean_mobile[-10:]}",
                    f"+91{clean_mobile[-10:]}",
                    clean_mobile,
                    clean_mobile[-10:]
                ]
                
                roadmap_doc = roadmap_col.find_one({'_id': {'$in': mobile_formats}})
                
                if roadmap_doc and 'roadmap' in roadmap_doc:
                    print(f"   ✅ Found roadmap, generating mappings...")
                    roadmap_data = roadmap_doc['roadmap']
                    
                    # Get user's job role skills
                    job_role = None
                    job_role_skills = None
                    resume_doc = resume_col.find_one({'_id': {'$in': mobile_formats}})
                    if resume_doc:
                        # Try jobRoleSkills first
                        job_role_skills_data = resume_doc.get('jobRoleSkills', {})
                        if job_role_skills_data:
                            job_role = job_role_skills_data.get('role')
                            current_skills = job_role_skills_data.get('current', [])
                            skills_to_learn = job_role_skills_data.get('skillsToLearn', [])
                            job_role_skills = current_skills + skills_to_learn
                        
                        # Fallback to jobSelection
                        if not job_role_skills:
                            job_selection = resume_doc.get('jobSelection', {})
                            job_role = job_selection.get('jobRole')
                            selected_skills = job_selection.get('selectedSkills', [])
                            unselected_skills = job_selection.get('unselectedSkills', [])
                            job_role_skills = selected_skills + unselected_skills
                        
                        if job_role and job_role_skills:
                            print(f"   Using job role: {job_role} with {len(job_role_skills)} skills")
                    
                    # Generate mappings for all months
                    for month_key, month_data in roadmap_data.items():
                        if month_key.startswith('Month '):
                            month_num = int(month_key.split(' ')[1])
                            skill_mapping = _analyze_roadmap_dashboard_for_skills(month_data, job_role, job_role_skills)
                            if skill_mapping:
                                _save_skill_week_mapping(mobile, month_num, skill_mapping)
                                print(f"   ✅ Generated mapping for Month {month_num}")
                    
                    # Re-fetch the mapping document
                    mapping_doc = mapping_col.find_one({'_id': mobile_id})
                    
                    if not mapping_doc:
                        print(f"   ❌ Still no mappings after generation")
                        return jsonify({
                            'success': True,
                            'message': 'Could not generate skill mappings from roadmap',
                            'skillsCompleted': [],
                            'skillsMoved': []
                        }), 200
                else:
                    print(f"   ⚠️ No roadmap found for auto-generation")
                    return jsonify({
                        'success': True,
                        'message': 'No skill mapping or roadmap found',
                        'skillsCompleted': [],
                        'skillsMoved': []
                    }), 200
                    
            except Exception as gen_error:
                print(f"   ❌ Error auto-generating mappings: {gen_error}")
                return jsonify({
                    'success': True,
                    'message': 'No skill mapping found (roadmap may not have been analyzed yet)',
                    'skillsCompleted': [],
                    'skillsMoved': []
                }), 200
        
        # Get mapping for this month
        month_key = f"month_{month_number}"
        available_months = mapping_doc.get('months', {})
        skill_mapping = available_months.get(month_key, {})
        
        print(f"📋 Available months in mapping: {list(available_months.keys())}")
        print(f"🔍 Looking for: {month_key}")
        
        if not skill_mapping:
            print(f"⚠️ No skill mapping for {month_key}")
            print(f"   Available mappings: {available_months}")
            print(f"🔧 Attempting to auto-generate mapping for {month_key}...")
            
            # Try to auto-generate mapping for this specific month
            try:
                roadmap_col = db['Roadmap_Dashboard ']
                
                mobile_formats = [
                    mobile,
                    f"+91 {clean_mobile[-10:]}",
                    f"+91{clean_mobile[-10:]}",
                    clean_mobile,
                    clean_mobile[-10:]
                ]
                
                roadmap_doc = roadmap_col.find_one({'_id': {'$in': mobile_formats}})
                
                if roadmap_doc and 'roadmap' in roadmap_doc:
                    month_roadmap_key = f"Month {month_number}"
                    month_data = roadmap_doc['roadmap'].get(month_roadmap_key)
                    
                    if month_data:
                        print(f"   ✅ Found roadmap for {month_roadmap_key}, generating mapping...")
                        
                        # Get user's job role skills
                        job_role = None
                        job_role_skills = None
                        resume_doc = resume_col.find_one({'_id': {'$in': mobile_formats}})
                        if resume_doc:
                            # Try jobRoleSkills first
                            job_role_skills_data = resume_doc.get('jobRoleSkills', {})
                            if job_role_skills_data:
                                job_role = job_role_skills_data.get('role')
                                current_skills = job_role_skills_data.get('current', [])
                                skills_to_learn = job_role_skills_data.get('skillsToLearn', [])
                                job_role_skills = current_skills + skills_to_learn
                            
                            # Fallback to jobSelection
                            if not job_role_skills:
                                job_selection = resume_doc.get('jobSelection', {})
                                job_role = job_selection.get('jobRole')
                                selected_skills = job_selection.get('selectedSkills', [])
                                unselected_skills = job_selection.get('unselectedSkills', [])
                                job_role_skills = selected_skills + unselected_skills
                            
                            if job_role and job_role_skills:
                                print(f"   Using job role: {job_role} with {len(job_role_skills)} skills")
                        
                        skill_mapping = _analyze_roadmap_dashboard_for_skills(month_data, job_role, job_role_skills)
                        
                        if skill_mapping:
                            _save_skill_week_mapping(mobile, month_number, skill_mapping)
                            print(f"   ✅ Successfully generated and saved mapping for {month_key}")
                        else:
                            print(f"   ⚠️ Could not extract skills from roadmap")
                            return jsonify({
                                'success': True,
                                'message': f'Could not extract skills for Month {month_number}',
                                'skillsCompleted': [],
                                'skillsMoved': [],
                                'availableMonths': list(available_months.keys())
                            }), 200
                    else:
                        print(f"   ⚠️ No roadmap data for {month_roadmap_key}")
                        return jsonify({
                            'success': True,
                            'message': f'No roadmap found for Month {month_number}',
                            'skillsCompleted': [],
                            'skillsMoved': [],
                            'availableMonths': list(available_months.keys())
                        }), 200
                else:
                    print(f"   ⚠️ No roadmap document found")
                    return jsonify({
                        'success': True,
                        'message': f'No skill mapping found for Month {month_number}',
                        'skillsCompleted': [],
                        'skillsMoved': [],
                        'availableMonths': list(available_months.keys())
                    }), 200
                    
            except Exception as gen_error:
                print(f"   ❌ Error auto-generating mapping: {gen_error}")
                return jsonify({
                    'success': True,
                    'message': f'No skill mapping found for Month {month_number}',
                    'skillsCompleted': [],
                    'skillsMoved': [],
                    'availableMonths': list(available_months.keys())
                }), 200
        
        print(f"📋 Skill-Week Mapping for {month_key}: {skill_mapping}")
        
        # Find all skills that are taught in this specific week
        # New format: {"Python": [1, 2, 3], "Machine Learning": [4]}
        skills_completed_this_week = []
        
        for skill, week_numbers in skill_mapping.items():
            # Handle both old format (int) and new format (list)
            if isinstance(week_numbers, int):
                week_numbers = [week_numbers]
            elif not isinstance(week_numbers, list):
                continue
            
            # Check if current week is the LAST week where this skill appears
            # This means the skill is "completed" at this week
            if week_number == max(week_numbers):
                # Split combined skills (e.g., "Machine Learning Models & scikit-learn" -> ["Machine Learning Models", "scikit-learn"])
                if ' & ' in skill:
                    individual_skills = [s.strip() for s in skill.split(' & ')]
                    skills_completed_this_week.extend(individual_skills)
                else:
                    skills_completed_this_week.append(skill)
            # If this is week 4 (end of month), also include any skills that completed in earlier weeks
            elif week_number == 4 and max(week_numbers) < week_number:
                print(f"   ℹ️ Also including skill from weeks {week_numbers}: {skill}")
                if ' & ' in skill:
                    individual_skills = [s.strip() for s in skill.split(' & ')]
                    skills_completed_this_week.extend(individual_skills)
                else:
                    skills_completed_this_week.append(skill)
        
        if not skills_completed_this_week:
            print(f"ℹ️ No skills complete at Week {week_number}")
            return jsonify({
                'success': True,
                'message': f'No skills scheduled to complete at Week {week_number}',
                'skillsCompleted': [],
                'skillsMoved': []
            }), 200
        
        print(f"✅ Skills completing at Week {week_number}: {skills_completed_this_week}")
        
        # Find user's resume by _id (Resume collection uses _id as mobile number)
        # Try different mobile formats
        mobile_formats = [
            mobile,                           # Original format
            f"+91 {clean_mobile[-10:]}",     # +91 XXXXXXXXXX
            f"+91{clean_mobile[-10:]}",      # +91XXXXXXXXXX
            clean_mobile,                    # All digits
            clean_mobile[-10:]               # Last 10 digits
        ]
        
        print(f"🔍 Searching for resume with mobile formats: {mobile_formats}")
        
        resume_doc = None
        for variant in mobile_formats:
            resume_doc = resume_col.find_one({'_id': variant})
            if resume_doc:
                print(f"📄 Found resume with _id: {variant}")
                break
        
        if not resume_doc:
            print(f"❌ Resume not found for mobile: {mobile}")
            print(f"   Tried formats: {mobile_formats}")
            return jsonify({
                'success': False,
                'error': 'Resume not found'
            }), 404
        
        # Get current skills from resume
        current_skills = resume_doc.get('skills', [])
        if not isinstance(current_skills, list):
            current_skills = []
        
        print(f"📋 Current skills in resume: {current_skills}")
        
        # Ensure current skills are split
        current_skills = split_combined_skills(current_skills)
        
        current_skills_lower = [str(s).lower() for s in current_skills]
        
        print(f"🔍 Skills to check: {skills_completed_this_week}")
        print(f"🔍 Current skills (lowercase): {current_skills_lower}")
        
        # Add completed skills that aren't already in resume
        skills_moved = []
        for skill in skills_completed_this_week:
            skill_lower = skill.lower()
            if skill_lower not in current_skills_lower:
                current_skills.append(skill)
                current_skills_lower.append(skill_lower)
                skills_moved.append(skill)
                print(f"   ➕ Adding new skill: {skill}")
            else:
                print(f"   ℹ️ Skill already exists: {skill}")
        
        if skills_moved:
            # Update resume with new skills
            resume_col.update_one(
                {'_id': resume_doc['_id']},
                {'$set': {'skills': current_skills}}
            )
            
            print(f"🎉 Moved {len(skills_moved)} skill(s) to Skills & Expertise: {skills_moved}")
        else:
            print(f"ℹ️ All completed skills already in resume")
        
        return jsonify({
            'success': True,
            'message': f'{len(skills_completed_this_week)} skill(s) completed at Week {week_number}',
            'skillsCompleted': skills_completed_this_week,
            'skillsMoved': skills_moved,
            'totalSkillsInResume': len(current_skills)
        }), 200
        
    except Exception as e:
        print(f"❌ Error in skill completion check: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/get-resume-skills', methods=['GET'])
def get_resume_skills():
    """
    Get current skills from Resume collection for a user.
    Used to sync frontend localStorage with database.
    
    Query params:
        mobile: User's mobile number
    
    Returns:
        {
            "success": true,
            "skills": ["Python", "Machine Learning Models", ...],
            "totalSkills": 5
        }
    """
    try:
        mobile = request.args.get('mobile')
        
        if not mobile:
            return jsonify({
                'success': False,
                'error': 'Mobile number is required'
            }), 400
        
        # Get MongoDB connection
        mongo_uri = os.getenv('MONGO_URI') or os.getenv('MONGODB_URI')
        if not mongo_uri:
            return jsonify({
                'success': False,
                'error': 'MongoDB URI not configured'
            }), 500
        
        client = MongoClient(mongo_uri)
        db = client[os.getenv("MONGODB_DB", "Placement_Ai")]
        resume_col = db['Resume']
        
        # Try different mobile formats
        clean_mobile = ''.join(filter(str.isdigit, str(mobile)))
        mobile_formats = [
            mobile,
            f"+91 {clean_mobile[-10:]}",
            f"+91{clean_mobile[-10:]}",
            clean_mobile,
            clean_mobile[-10:]
        ]
        
        resume_doc = None
        for variant in mobile_formats:
            resume_doc = resume_col.find_one({'_id': variant})
            if resume_doc:
                break
        
        if not resume_doc:
            return jsonify({
                'success': False,
                'error': 'Resume not found'
            }), 404
        
        skills = resume_doc.get('skills', [])
        if not isinstance(skills, list):
            skills = []
        
        # Ensure skills are split (no combined skills)
        skills = split_combined_skills(skills)
        
        return jsonify({
            'success': True,
            'skills': skills,
            'totalSkills': len(skills)
        }), 200
        
    except Exception as e:
        print(f"❌ Error getting resume skills: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

def _get_job_role_skills(job_domain, job_role):
    """
    Get the list of required skills for a specific job role.
    
    Uses comprehensive mapping from data/job_role_skills.py which contains
    ALL job roles and their required skills (not just 7, varies by role).
    
    These are the HIGH-LEVEL SKILLS that weekly test TOPICS map to via semantic matching.
    Example:
    - Job Role Skill: "Machine Learning"
    - Weekly Test Topics: "Decision Trees", "Random Forest", "K-Means Clustering"
    - Semantic matching connects topics → skill and gives stars based on topic performance
    
    Args:
        job_domain (str): Job domain (not used, for future expansion)
        job_role (str): Job role name (e.g., "NLP Engineer", "Data Analyst")
    
    Returns:
        list: Required skills for the job role (varies by role - could be 5, 7, 10, 15+ skills)
    """
    try:
        from data.job_role_skills import get_job_role_skills
        
        skills = get_job_role_skills(job_role)
        
        if skills:
            print(f"✅ Found {len(skills)} required skills for '{job_role}'")
            return skills
        else:
            print(f"⚠️  No skills found for job role: '{job_role}'")
            print(f"   This might be a new/custom role. Please add to data/job_role_skills.py")
            return []
            
    except Exception as e:
        print(f"❌ Error loading job role skills: {str(e)}")
        import traceback
        traceback.print_exc()
        return []


def _get_job_role_skills_simple(job_role):
    """
    Simplified version that gets skills using just job role name.
    Works with both ID format ('nlp_engineer') and display format ('NLP Engineer').
    
    Args:
        job_role (str): Job role name or ID
    
    Returns:
        list: Required skills for the job role
    """
    try:
        from data.job_role_skills import get_job_role_skills
        
        skills = get_job_role_skills(job_role)
        
        if skills:
            print(f"✅ Found {len(skills)} required skills for '{job_role}'")
            return skills
        else:
            print(f"⚠️  No skills found for job role: '{job_role}'")
            return []
            
    except Exception as e:
        print(f"❌ Error loading job role skills: {str(e)}")
        return []


@app.route('/api/generate-skill-mappings-from-roadmap', methods=['POST'])
def generate_skill_mappings_from_roadmap():
    """
    Generate skill-week mappings from existing Roadmap_Dashboard data.
    
    This endpoint analyzes the user's existing roadmap and uses Perplexity AI 
    to extract skill completion weeks, then saves them to skill_week_mapping collection.
    
    Expected payload:
    {
        "mobile": "+91 9084117332",
        "month_number": 1  // Optional, if not provided will process all months
    }
    
    Response:
    {
        "success": true,
        "message": "Generated skill mappings for 3 months",
        "mappings": {
            "month_1": {"Excel Formulas": 1, "Data Cleaning": 2},
            "month_2": {...},
            "month_3": {...}
        }
    }
    """
    try:
        data = request.get_json()
        
        mobile = data.get('mobile')
        specific_month = data.get('month_number')  # Optional
        
        if not mobile:
            return jsonify({
                'success': False,
                'message': 'Mobile number is required'
            }), 400
        
        print(f"\n{'='*80}")
        print(f"🔧 GENERATING SKILL-WEEK MAPPINGS FROM ROADMAP_DASHBOARD")
        print(f"   Mobile: {mobile}")
        if specific_month:
            print(f"   Month: {specific_month}")
        else:
            print(f"   Processing: All months")
        print(f"{'='*80}\n")
        
        # Get database
        db = get_db()
        roadmap_collection = db['Roadmap_Dashboard ']  # Note: trailing space
        resume_collection = db['Resume']
        
        # Normalize mobile number
        clean_mobile = ''.join(filter(str.isdigit, mobile))
        mobile_formats = [
            mobile,
            clean_mobile,
            clean_mobile[-10:],
            f"+91 {clean_mobile[-10:]}",
            f"+91{clean_mobile[-10:]}"
        ]
        mobile_formats = list(dict.fromkeys(mobile_formats))
        
        print(f"🔍 Searching for roadmap with mobile formats: {mobile_formats}")
        
        # Get user's job role and skills from Resume collection
        job_role = None
        job_role_skills = None
        resume_doc = resume_collection.find_one({'_id': {'$in': mobile_formats}})
        if resume_doc:
            # Try jobRoleSkills first (preferred)
            job_role_skills_data = resume_doc.get('jobRoleSkills', {})
            if job_role_skills_data:
                job_role = job_role_skills_data.get('role')
                job_domain = job_role_skills_data.get('domain')
                
                # Get skills from jobRoleSkills (current + skillsToLearn)
                current_skills = job_role_skills_data.get('current', [])
                skills_to_learn = job_role_skills_data.get('skillsToLearn', [])
                job_role_skills = current_skills + skills_to_learn
            
            # Fallback to jobSelection if jobRoleSkills not found
            if not job_role_skills:
                job_selection = resume_doc.get('jobSelection', {})
                job_role = job_selection.get('jobRole')
                job_domain = job_selection.get('jobDomain')
                
                # Get skills from jobSelection (selectedSkills + unselectedSkills)
                selected_skills = job_selection.get('selectedSkills', [])
                unselected_skills = job_selection.get('unselectedSkills', [])
                job_role_skills = selected_skills + unselected_skills
            
            if job_role and job_role_skills:
                print(f"✅ Found user's job selection:")
                print(f"   Domain: {job_domain}")
                print(f"   Role: {job_role}")
                print(f"   Total target skills: {len(job_role_skills)}")
                print(f"   Skills: {job_role_skills}")
        
        # Find user's roadmap
        roadmap_doc = roadmap_collection.find_one({'_id': {'$in': mobile_formats}})
        
        if not roadmap_doc:
            print(f"❌ No roadmap found in Roadmap_Dashboard collection")
            print(f"   Tried mobile formats: {mobile_formats}")
            return jsonify({
                'success': False,
                'message': 'No roadmap found for this user in Roadmap_Dashboard collection'
            }), 404
        
        print(f"✅ Found roadmap document")
        print(f"   User ID: {roadmap_doc.get('_id')}")
        
        # Get the roadmap data
        roadmap_data = roadmap_doc.get('roadmap', {})
        
        if not roadmap_data:
            return jsonify({
                'success': False,
                'message': 'Roadmap data is empty'
            }), 404
        
        # Always regenerate mappings (don't return existing ones)
        # This ensures we use the latest Perplexity analysis with new array format
        print(f"   🔄 Regenerating skill mappings with latest analysis...")
        
        # Process each month
        all_mappings = {}
        months_processed = []
        
        for month_key, month_data in roadmap_data.items():
            # Extract month number from "Month 1", "Month 2", etc.
            if not month_key.startswith('Month '):
                continue
            
            month_num = int(month_key.split(' ')[1])
            
            # Skip if specific month requested and this isn't it
            if specific_month and month_num != specific_month:
                continue
            
            print(f"\n📊 Processing {month_key}...")
            
            # Analyze this month's data WITH job role skills for better matching
            skill_mapping = _analyze_roadmap_dashboard_for_skills(month_data, job_role, job_role_skills)
            
            if skill_mapping:
                # Save to skill_week_mapping collection
                _save_skill_week_mapping(mobile, month_num, skill_mapping)
                all_mappings[f"month_{month_num}"] = skill_mapping
                months_processed.append(month_num)
                print(f"   ✅ Saved mapping for Month {month_num}: {len(skill_mapping)} skills")
            else:
                print(f"   ⚠️ No skills extracted for Month {month_num}")
        
        if not months_processed:
            print(f"\n⚠️ No new skill mappings were generated from roadmap")
            print(f"   Checking if mappings already exist in database...")
            
            # Check if skill mappings already exist
            mapping_col = db['skill_week_mapping']
            mobile_id = clean_mobile[-10:]  # Last 10 digits
            existing_mapping = mapping_col.find_one({'_id': mobile_id})
            
            if existing_mapping and 'months' in existing_mapping:
                months_data = existing_mapping.get('months', {})
                if months_data:
                    print(f"✅ Found existing skill mappings for {mobile_id}!")
                    print(f"   Months: {list(months_data.keys())}")
                    
                    return jsonify({
                        'success': True,
                        'message': 'Skill mappings already exist',
                        'months_processed': [int(m.split('_')[1]) for m in months_data.keys() if m.startswith('month_')],
                        'mappings': months_data,
                        'totalSkills': sum(len(skills) for skills in months_data.values() if isinstance(skills, dict)),
                        'note': 'Using existing mappings from database'
                    }), 200
            
            print(f"\n❌ No skill mappings could be generated or found")
            print(f"   Possible reasons:")
            print(f"   - No roadmap data found")
            print(f"   - Roadmap data structure is invalid")
            print(f"   - Perplexity API failed to analyze roadmap")
            print(f"   - No months with valid data in roadmap")
            
            return jsonify({
                'success': False,
                'message': 'No skill mappings could be generated. Possible reasons:\n• No roadmap found for this user\n• Roadmap data is empty or invalid\n• AI analysis failed\n\nPlease ensure you have generated a roadmap first.',
                'details': {
                    'roadmap_found': roadmap_doc is not None if 'roadmap_doc' in locals() else False,
                    'roadmap_has_data': bool(roadmap_data) if 'roadmap_data' in locals() else False,
                    'months_in_roadmap': list(roadmap_data.keys()) if 'roadmap_data' in locals() and roadmap_data else []
                }
            }), 200  # Changed to 200 to allow frontend to show user-friendly message
        
        return jsonify({
            'success': True,
            'message': f'Generated skill mappings for {len(months_processed)} month(s)',
            'months_processed': months_processed,
            'mappings': all_mappings,
            'totalSkills': sum(len(mapping) for mapping in all_mappings.values())
        }), 200
        
    except Exception as e:
        print(f"❌ Error generating skill mappings: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/skill-ratings/<mobile>', methods=['GET'])
def get_skill_ratings(mobile):
    """
    Calculate star ratings for JOB-ROLE-SPECIFIC SKILLS based on weekly test performance.
    
    📚 DATA SOURCE: Weekly_test_analysis collection
    - Each document contains test results for one week
    - Document structure: {mobile, analysis: {...}, skillPerformance: {...}}
    - skillPerformance (root level): Actual difficulty-weighted scores
      Format: {"topic": {"score": 24, "maxScore": 26, "percentage": 92.31, "correct": 18, "total": 20}}
      The percentage accounts for easy/medium/hard question difficulty levels
    
    🎯 HOW IT WORKS:
    1. User selects job role (e.g., "NLP Engineer") → Gets list of required SKILLS
       - Skills are HIGH-LEVEL: "Machine Learning", "Python", "NLP", "scikit-learn", etc.
       - Number varies by role (not always 7 - could be 5, 10, 15+ skills)
    
    2. Weekly tests are generated from roadmap covering specific TOPICS
       - Topics are CURRICULUM ITEMS: "Linear Regression", "Logistic Regression", etc.
       - Each topic has questions with different difficulty levels (easy/medium/hard)
       - Scores are calculated based on difficulty-weighted marks
    
    3. Semantic AI matching connects TOPICS → SKILLS automatically
       - Example: "Linear Regression theory" topic → "Machine Learning" skill (85% similarity)
       - Example: "Install scikit-learn" topic → "scikit-learn" skill (92% similarity)
       - Uses sentence-transformers embeddings for intelligent matching
    
    4. Star ratings calculated from ACTUAL difficulty-weighted topic performance
       - If user scores 50% on "Linear Regression" (difficulty-weighted), "Machine Learning" gets 50%
       - If user scores 33.96% on "scikit-learn topics" (difficulty-weighted), "scikit-learn" gets 33.96%
       - Average across all weeks where skill topics appear
    
    This ensures users develop the EXACT skills needed for their target job role,
    with accurate scoring that accounts for question difficulty levels.
    
    ⭐ Star Rating Thresholds:
    - 0 stars: < 50% average (Needs Work)
    - 1 star: 50-69% average (Fair)
    - 2 stars: 70-89% average (Good)
    - 3 stars: 90%+ average (Expert)
    """
    try:
        from utils.db import normalize_phone, format_phone_id
        
        # Normalize mobile for skill_week_mapping lookup (uses last 10 digits)
        mobile_id = _normalize_mobile_id(mobile)
        
        # Format mobile for week_test_result lookup (uses "+91 1234567890" format)
        phone_digits = normalize_phone(mobile)
        formatted_mobile = format_phone_id(phone_digits) if phone_digits else mobile
        
        mongo_uri = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
        db_name = os.getenv('MONGODB_DB', 'Placement_Ai')
        client = MongoClient(mongo_uri)
        db = client[db_name]
        
        # 🎯 ALWAYS FETCH RESUME TO GET JOB SELECTION SKILLS
        resume_doc = None
        resume_col = db['Resume']
        
        # Try to find resume with same mobile variants
        clean = ''.join([c for c in mobile if c.isdigit()])
        mobile_variants = [mobile, mobile.replace(' ', ''), mobile.replace('+', ''), clean]
        if len(clean) == 10:
            mobile_variants.append(f'+91 {clean}')
            mobile_variants.append(f'+91{clean}')
        
        for variant in mobile_variants:
            resume_doc = resume_col.find_one({'_id': variant})
            if resume_doc:
                break
        
        # If not found by _id, try mobile/phone fields
        if not resume_doc:
            for variant in mobile_variants:
                resume_doc = resume_col.find_one({'$or': [{'mobile': variant}, {'phone': variant}]})
                if resume_doc:
                    break
        
        # If not found in Resume, try resume_temp
        if not resume_doc:
            resume_temp_col = db['resume_temp']
            for variant in mobile_variants:
                resume_doc = resume_temp_col.find_one({'$or': [{'mobile': variant}, {'phone': variant}]})
                if resume_doc:
                    break
        
        if not resume_doc:
            return jsonify({
                'success': False,
                'message': 'Resume not found. Please complete your profile first.',
                'skillRatings': {},
                'jobRoleSkills': []
            }), 404
        
        # Get job role and skills from resume
        # Try jobRoleSkills first (preferred structure)
        job_role_skills_data = resume_doc.get('jobRoleSkills', {})
        if job_role_skills_data:
            job_role = job_role_skills_data.get('role', '')
            job_domain = job_role_skills_data.get('domain', '')
            
            # Get skills from jobRoleSkills (current + skillsToLearn)
            current_skills = job_role_skills_data.get('current', [])
            skills_to_learn = job_role_skills_data.get('skillsToLearn', [])
            job_role_available_skills = current_skills + skills_to_learn
            
            print(f"📊 Using jobRoleSkills: '{job_domain}/{job_role}'")
            print(f"   Current skills: {current_skills}")
            print(f"   Skills to learn: {skills_to_learn}")
        else:
            # Fallback to jobSelection structure
            job_selection = resume_doc.get('jobSelection', {})
            job_role = job_selection.get('jobRole', '')
            job_domain = job_selection.get('jobDomain', '')
            
            # Get skills from jobSelection (selectedSkills + unselectedSkills)
            selected_skills = job_selection.get('selectedSkills', [])
            unselected_skills = job_selection.get('unselectedSkills', [])
            job_role_available_skills = selected_skills + unselected_skills
            
            print(f"📊 Using jobSelection: '{job_domain}/{job_role}'")
            print(f"   Selected skills: {selected_skills}")
            print(f"   Skills to learn: {unselected_skills}")
        
        # Validate job role and skills
        if not job_role:
            return jsonify({
                'success': False,
                'message': 'No job role found in your profile. Please select a job role.',
                'skillRatings': {},
                'jobRoleSkills': []
            }), 400
        
        if not job_role_available_skills:
            return jsonify({
                'success': False,
                'message': f'No skills found in jobSelection for {job_role}. Please update your profile.',
                'skillRatings': {},
                'jobRoleSkills': []
            }), 400
        
        print(f"\n{'='*80}")
        print(f"🎯 CALCULATING RATINGS FOR JOB-ROLE-SPECIFIC SKILLS")
        print(f"{'='*80}")
        print(f"User: {mobile_id}")
        print(f"Selected Job Role: {job_domain}/{job_role}")
        print(f"Job-Role-Specific Skills ({len(job_role_available_skills)}): {job_role_available_skills}")
        print(f"{'='*80}\n")
        
        # Get skill-week mapping
        skill_mapping_col = db['skill_week_mapping']
        mapping_doc = skill_mapping_col.find_one({'_id': mobile_id})
        
        if not mapping_doc or 'months' not in mapping_doc:
            return jsonify({
                'success': True,
                'message': 'No skill mappings found',
                'skillRatings': {}
            }), 200
        
        # Get all weekly test results for this user from Weekly_test_analysis collection
        # This collection stores AI-analyzed test results with topic-wise performance
        week_analysis_col = db['Weekly_test_analysis']
        
        # Build mobile variants to search
        clean = ''.join([c for c in mobile if c.isdigit()])
        mobile_variants = [mobile, mobile.replace(' ', ''), mobile.replace('+', ''), clean]
        if len(clean) == 10:
            mobile_variants.append(f'+91 {clean}')
            mobile_variants.append(f'+91{clean}')
        
        # Remove duplicates while preserving order
        seen = set()
        unique_variants = []
        for v in mobile_variants:
            if v not in seen:
                seen.add(v)
                unique_variants.append(v)
        
        # Query for all weekly test analysis documents
        # Documents are stored with _id format: "{mobile}_week_{week_number}"
        all_week_results = []
        for variant in unique_variants:
            docs = list(week_analysis_col.find({'mobile': variant}))
            if docs:
                all_week_results.extend(docs)
                break
        
        print(f"📊 Found {len(all_week_results)} weekly test analysis documents for {mobile}")
        
        # Build a lookup: (month, week) -> {'overall': percentage, 'skillPerformance': {...}}
        # This stores overall score AND topic-specific performance with ACTUAL difficulty-weighted scores
        week_data = {}
        for doc in all_week_results:
            analysis = doc.get('analysis', {})
            month = analysis.get('month')
            week = analysis.get('week')
            
            # Get overall percentage from score_summary
            score_summary = analysis.get('score_summary', {})
            score_pct = score_summary.get('percentage', 0)
            
            # Get skillPerformance from ROOT level of document (not from analysis object)
            # This contains actual difficulty-weighted percentages based on easy/medium/hard questions
            # Format: {"topic_name": {"correct": 10, "total": 20, "score": 13, "maxScore": 26, "percentage": 50}}
            skill_performance = doc.get('skillPerformance', {})
            
            if month and week:
                week_data[(month, week)] = {
                    'overall': score_pct,
                    'skillPerformance': skill_performance  # Dict with actual weighted percentages
                }
        
        print(f"📊 Processed {len(week_data)} weeks of data for {mobile_id}")
        print(f"   Week data available: {list(week_data.keys())}")
        
        # Helper function to find skill-specific score using semantic embeddings
        def get_skill_score(skill_name, skill_performance_dict):
            """
            Find the percentage for a specific skill by matching against topic names in skillPerformance.
            Uses semantic similarity (sentence embeddings) for intelligent matching.
            
            Args:
                skill_name: The skill to find (e.g., "Machine Learning", "scikit-learn")
                skill_performance_dict: Dict with topic keys and performance data
                    Example: {"Linear Regression theory": {"percentage": 50, "score": 13, "maxScore": 26}, ...}
            
            Returns:
                tuple: (score, matched_topic_name) or (None, None) if not found
            """
            if not skill_performance_dict:
                return None, None
            
            # Try exact match first (fast path)
            if skill_name in skill_performance_dict:
                return skill_performance_dict[skill_name].get('percentage', 0), skill_name
            
            # Use semantic similarity for intelligent matching
            try:
                from sentence_transformers import SentenceTransformer, util
                import torch
                
                # Initialize model (will be cached after first use)
                if not hasattr(get_skill_score, 'model'):
                    print("      📦 Loading semantic matching model (one-time)...")
                    get_skill_score.model = SentenceTransformer('all-MiniLM-L6-v2')
                    get_skill_score.cache = {}
                    print("      ✅ Model loaded")
                
                model = get_skill_score.model
                cache = get_skill_score.cache
                
                # Get embedding for the skill (with caching)
                if skill_name not in cache:
                    cache[skill_name] = model.encode(skill_name, convert_to_tensor=True)
                skill_embedding = cache[skill_name]
                
                # Get all topic names from skillPerformance dict
                topic_names = list(skill_performance_dict.keys())
                if not topic_names:
                    return None, None
                
                # Get embeddings for all topics
                topic_embeddings = model.encode(topic_names, convert_to_tensor=True)
                
                # Calculate cosine similarities
                similarities = util.cos_sim(skill_embedding, topic_embeddings)[0]
                
                # Find best match above threshold
                max_sim_idx = torch.argmax(similarities).item()
                max_similarity = similarities[max_sim_idx].item()
                
                # Threshold: 0.3 = loose match (ML concepts), 0.5 = medium, 0.7 = strict
                if max_similarity > 0.3:
                    best_match_topic_name = topic_names[max_sim_idx]
                    # Get the percentage from the matched topic
                    best_score_val = skill_performance_dict[best_match_topic_name].get('percentage', 0)
                    print(f"      🔗 '{skill_name}' → '{best_match_topic_name}' (similarity: {max_similarity:.2f}, score: {best_score_val}%)")
                    return best_score_val, best_match_topic_name
            
            except Exception as e:
                print(f"      ⚠️  Semantic matching error: {str(e)}")
            
            return None, None
        
        # Calculate ratings for each skill
        skill_ratings = {}
        
        months_data = mapping_doc.get('months', {})
        
        for month_key, skill_map in months_data.items():
            # Extract month number from "month_1", "month_2", etc.
            try:
                month_num = int(month_key.split('_')[1])
            except:
                continue
            
            # skill_map is like: {"Python": [1, 2, 3], "Machine Learning": [4], ...}
            # OR old format: {"Python": 4, "Machine Learning & scikit-learn": 4}
            # The array contains week numbers where that skill is taught
            for skill_name, week_numbers in skill_map.items():
                # Ensure week_numbers is a list
                if isinstance(week_numbers, int):
                    week_numbers = [week_numbers]  # Convert single number to array
                elif not isinstance(week_numbers, list):
                    continue  # Skip invalid data
                
                # Handle combined skills that were split (e.g., "Machine Learning Models & scikit-learn")
                # These should match both individual skills in the resume
                if ' & ' in skill_name:
                    # Split into individual skills
                    individual_skills = [s.strip() for s in skill_name.split(' & ')]
                    
                    # Calculate rating for each individual skill separately
                    for individual_skill in individual_skills:
                        # Get skill-specific scores for all weeks where this skill appears
                        week_percentages = []
                        week_sources = []  # Track if we used skill-specific or overall score
                        
                        for week_num in week_numbers:
                            if (month_num, week_num) in week_data:
                                week_info = week_data[(month_num, week_num)]
                                
                                # Try to get skill-specific score from skillPerformance (actual weighted %)
                                skill_score, matched_topic = get_skill_score(individual_skill, week_info.get('skillPerformance', {}))
                                
                                if skill_score is not None:
                                    week_percentages.append(skill_score)
                                    week_sources.append(f"Week {week_num}: {skill_score}% (from '{matched_topic}')")
                                else:
                                    # Fallback to overall score if skill-specific not found
                                    overall_score = week_info.get('overall', 0)
                                    week_percentages.append(overall_score)
                                    week_sources.append(f"Week {week_num}: {overall_score}% (overall - no match)")
                        
                        if week_percentages:
                            avg_percentage = sum(week_percentages) / len(week_percentages)
                            
                            # Determine stars based on average performance
                            # 0 stars: < 50%
                            # 1 star: 50-69%
                            # 2 stars: 70-89%
                            # 3 stars: 90%+
                            if avg_percentage >= 90:
                                stars = 3
                            elif avg_percentage >= 70:
                                stars = 2
                            elif avg_percentage >= 50:
                                stars = 1
                            else:
                                stars = 0
                            
                            skill_ratings[individual_skill] = {
                                'stars': stars,
                                'averagePercentage': round(avg_percentage, 2),
                                'weeksAppearing': week_numbers,
                                'month': month_num,
                                'weeksTested': len(week_percentages),
                                'weekScores': week_percentages,
                                'scoreDetails': week_sources  # For debugging
                            }
                            
                            print(f"   ⭐ {individual_skill}: {stars} stars ({avg_percentage:.1f}% avg)")
                            for detail in week_sources:
                                print(f"      - {detail}")
                else:
                    # Single skill (not combined)
                    # Get skill-specific scores for all weeks where this skill appears
                    week_percentages = []
                    week_sources = []  # Track if we used skill-specific or overall score
                    
                    for week_num in week_numbers:
                        if (month_num, week_num) in week_data:
                            week_info = week_data[(month_num, week_num)]
                            
                            # Try to get skill-specific score from skillPerformance (actual weighted %)
                            skill_score, matched_topic = get_skill_score(skill_name, week_info.get('skillPerformance', {}))
                            
                            if skill_score is not None:
                                week_percentages.append(skill_score)
                                week_sources.append(f"Week {week_num}: {skill_score}% (from '{matched_topic}')")
                            else:
                                # Fallback to overall score if skill-specific not found
                                overall_score = week_info.get('overall', 0)
                                week_percentages.append(overall_score)
                                week_sources.append(f"Week {week_num}: {overall_score}% (overall - no match)")
                    
                    if week_percentages:
                        avg_percentage = sum(week_percentages) / len(week_percentages)
                        
                        # Determine stars based on average performance
                        # 0 stars: < 50%
                        # 1 star: 50-69%
                        # 2 stars: 70-89%
                        # 3 stars: 90%+
                        if avg_percentage >= 90:
                            stars = 3
                        elif avg_percentage >= 70:
                            stars = 2
                        elif avg_percentage >= 50:
                            stars = 1
                        else:
                            stars = 0
                        
                        skill_ratings[skill_name] = {
                            'stars': stars,
                            'averagePercentage': round(avg_percentage, 2),
                            'weeksAppearing': week_numbers,  # Changed from completionWeek
                            'month': month_num,
                            'weeksTested': len(week_percentages),
                            'weekScores': week_percentages,
                            'scoreDetails': week_sources  # For debugging
                        }
                        
                        print(f"   ⭐ {skill_name}: {stars} stars ({avg_percentage:.1f}% avg)")
                        for detail in week_sources:
                            print(f"      - {detail}")


        # 🎯 FILTER TO ONLY JOB-ROLE-SPECIFIC SKILLS
        # Only return ratings for required skills from the selected job role
        # Note: The semantic matching ALREADY connected test topics to these skills
        # Example flow:
        #   1. Job role skill: "Machine Learning"
        #   2. Test topics: "Decision Trees", "Random Forest", "K-Means"
        #   3. Semantic matching: "Decision Trees" → "Machine Learning" (85% similarity)
        #   4. User scores 80% on Decision Trees → "Machine Learning" skill gets 80%
        filtered_skill_ratings = {}
        
        print(f"\n{'='*80}")
        print(f"🔍 FILTERING TO JOB-ROLE-SPECIFIC SKILLS")
        print(f"{'='*80}")
        print(f"Total skills with ratings from all tests: {len(skill_ratings)}")
        print(f"Job-role required skills: {len(job_role_available_skills)}")
        print(f"{'='*80}\n")
        
        for job_skill in job_role_available_skills:
            # Direct match
            if job_skill in skill_ratings:
                filtered_skill_ratings[job_skill] = skill_ratings[job_skill]
                print(f"   ✅ {job_skill}: {skill_ratings[job_skill]['stars']} stars")
                print(f"      Average: {skill_ratings[job_skill]['averagePercentage']}%")
                for detail in skill_ratings[job_skill].get('scoreDetails', []):
                    print(f"      {detail}")
            else:
                # Try semantic similarity for partial matches
                # e.g., "Natural Language Processing (NLP)" might be stored as "NLP" or "Natural Language Processing"
                best_match = None
                best_similarity = 0
                
                for rated_skill in skill_ratings.keys():
                    # Simple string matching first
                    if job_skill.lower() in rated_skill.lower() or rated_skill.lower() in job_skill.lower():
                        if len(rated_skill) > best_similarity:
                            best_match = rated_skill
                            best_similarity = len(rated_skill)
                
                if best_match:
                    filtered_skill_ratings[job_skill] = skill_ratings[best_match]
                    print(f"   ✅ {job_skill}: {skill_ratings[best_match]['stars']} stars (matched '{best_match}')")
                    print(f"      Average: {skill_ratings[best_match]['averagePercentage']}%")
                else:
                    # No match found - skill not tested yet (add with 0 stars)
                    filtered_skill_ratings[job_skill] = {
                        'stars': 0,
                        'averagePercentage': 0,
                        'weeksAppearing': [],
                        'month': None,
                        'weeksTested': 0,
                        'weekScores': [],
                        'scoreDetails': []
                    }
                    print(f"   ⭕ {job_skill}: Not tested yet (0 stars)")
                    print(f"      No curriculum topics matched this skill via semantic AI")
        
        print(f"\n{'='*80}")
        print(f"📊 FINAL RESULTS")
        print(f"{'='*80}")
        print(f"Total job role skills: {len(filtered_skill_ratings)}")
        print(f"Skills with test data: {len([s for s in filtered_skill_ratings.values() if s['weeksTested'] > 0])}")
        print(f"Skills not yet tested: {len([s for s in filtered_skill_ratings.values() if s['weeksTested'] == 0])}")
        print(f"{'='*80}\n")
        
        return jsonify({
            'success': True,
            'skillRatings': filtered_skill_ratings,
            'totalSkillsRated': len(filtered_skill_ratings),
            'jobRole': job_role,
            'jobRoleSkills': job_role_available_skills,
            'message': f'Showing ratings for {job_role} skills only'
        }), 200
        
    except Exception as e:
        print(f"❌ Error calculating skill ratings: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/debug-skill-mappings/<mobile>', methods=['GET'])
def debug_skill_mappings(mobile):
    """Debug endpoint to check skill-week mappings for a user"""
    try:
        mongo_uri = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
        client = MongoClient(mongo_uri)
        db = client[os.getenv('MONGODB_DB', 'Placement_Ai')]
        
        # Normalize mobile
        clean_mobile = ''.join(filter(str.isdigit, str(mobile)))
        mobile_id = clean_mobile[-10:]
        
        mapping_col = db['skill_week_mapping']
        mapping_doc = mapping_col.find_one({'_id': mobile_id})
        
        # Also check resume
        resume_col = db['Resume']
        mobile_formats = [
            mobile,
            f"+91 {mobile_id}",
            f"+91{mobile_id}",
            clean_mobile,
            mobile_id
        ]
        
        resume_doc = None
        for variant in mobile_formats:
            resume_doc = resume_col.find_one({'_id': variant})
            if resume_doc:
                break
        
        if not mapping_doc:
            return jsonify({
                'success': False,
                'message': f'No skill mappings found for {mobile_id}',
                'mobile_id': mobile_id
            }), 404
        
        return jsonify({
            'success': True,
            'mobile_id': mobile_id,
            'mappings': mapping_doc.get('months', {}),
            'created_at': mapping_doc.get('created_at'),
            'updated_at': mapping_doc.get('updated_at'),
            'resume_skills': resume_doc.get('skills', []) if resume_doc else None,
            'resume_id': resume_doc.get('_id') if resume_doc else None
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/force-move-skills', methods=['POST'])
def force_move_skills():
    """Manually force skill movement for debugging"""
    try:
        data = request.get_json()
        mobile = data.get('mobile')
        month_number = data.get('month', 2)
        week_number = data.get('week', 4)
        
        if not mobile:
            return jsonify({'success': False, 'error': 'Mobile required'}), 400
        
        # Call the check skill completion function
        from flask import Flask
        with app.test_request_context(
            '/api/check-skill-completion-with-ai',
            method='POST',
            json={'mobile': mobile, 'weekNumber': week_number, 'monthNumber': month_number}
        ):
            response = check_skill_completion_with_ai()
            return response
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================================================================================
# PROJECT SUBMISSION & PERPLEXITY AI INTEGRATION
# ==================================================================================

@app.route('/api/get-current-month-project', methods=['POST'])
def get_current_month_project():
    """
    Get the current month's project from Roadmap_Dashboard collection.
    
    Expected payload:
    {
        "mobile": "+91 9084117332"
    }
    
    Returns project details for the user's current month.
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'message': 'No data provided'
            }), 400
        
        mobile = data.get('mobile')
        
        if not mobile:
            return jsonify({
                'success': False,
                'message': 'Mobile number is required'
            }), 400
        
        print(f"\n=== Fetching current month project for mobile: {mobile} ===")
        
        # Get database connection
        db = get_db()
        roadmap_collection = db['Roadmap_Dashboard ']
        resume_collection = db['Resume']
        
        # Clean mobile number - remove all non-digits first
        clean_mobile = ''.join(filter(str.isdigit, mobile))
        
        # Try various mobile formats
        mobile_formats = [
            mobile,
            clean_mobile,
            clean_mobile[-10:],
            f"+91 {clean_mobile[-10:]}",
            f"+91{clean_mobile[-10:]}"
        ]
        
        # Remove duplicates
        mobile_formats = list(dict.fromkeys(mobile_formats))
        
        # Get user's current month from Resume collection
        user_resume = resume_collection.find_one({'_id': {'$in': mobile_formats}})
        
        if not user_resume:
            return jsonify({
                'success': False,
                'message': 'User not found'
            }), 404
        
        # Calculate current month based on week_test collection (more accurate)
        # Week 1-4 = Month 1, Week 5-8 = Month 2, Week 9-12 = Month 3, etc.
        week_test_collection = db['week_test']
        week_test = week_test_collection.find_one({'_id': {'$in': mobile_formats}})
        
        if week_test and 'week' in week_test:
            current_week = week_test.get('week', 1)
            # Calculate month from week number
            calculated_month = ((current_week - 1) // 4) + 1
            print(f"User's current week: {current_week}, calculated month: {calculated_month}")
        else:
            # Fallback to Resume collection's currentMonth field
            calculated_month = user_resume.get('currentMonth', 1)
            print(f"User's current month from Resume: {calculated_month}")
        
        # Check which months have already been submitted
        submissions_collection = db['project_submissions']
        submitted_months = set()
        
        # Get all submissions for this user
        user_submissions = submissions_collection.find({'mobile': {'$in': mobile_formats}})
        for submission in user_submissions:
            month = submission.get('month')
            if month:
                submitted_months.add(month)
        
        print(f"Already submitted months: {submitted_months}")
        
        # Find the first unsubmitted month (starting from month 1)
        current_month = 1
        max_month = min(calculated_month, 12)  # Cap at 12 months
        
        for month_num in range(1, max_month + 1):
            if month_num not in submitted_months:
                current_month = month_num
                break
        else:
            # All months submitted up to current month, show current month
            current_month = calculated_month
        
        print(f"Showing project for month: {current_month} (next unsubmitted)")
        
        # Get roadmap from Roadmap_Dashboard
        roadmap = roadmap_collection.find_one({'_id': {'$in': mobile_formats}})
        
        if not roadmap:
            return jsonify({
                'success': False,
                'message': 'No roadmap found for this user'
            }), 404
        
        # Extract month project - check both "Month 1" and "month1" formats
        month_key_space = f"Month {current_month}"  # New format: "Month 1"
        month_key_no_space = f"month{current_month}"  # Old format: "month1"
        
        # Get roadmap data (could be nested under 'roadmap' key or at top level)
        roadmap_data = roadmap.get('roadmap', roadmap)
        
        # Try new format first, then fall back to old format
        month_data = roadmap_data.get(month_key_space) or roadmap_data.get(month_key_no_space, {})
        
        if not month_data:
            return jsonify({
                'success': False,
                'message': f'No data found for month {current_month}'
            }), 404
        
        # Extract project details - support multiple field names
        project_title = month_data.get('Mini Project') or month_data.get('project') or 'No project assigned'
        project_description = month_data.get('Expected Outcome') or month_data.get('projectDescription') or month_data.get('Skill Focus') or ''
        
        print(f"✅ Found project: {project_title}")
        
        return jsonify({
            'success': True,
            'data': {
                'month': current_month,
                'projectTitle': project_title,
                'projectDescription': project_description,
                'monthKey': month_key_space  # Return the format we found
            }
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'Error fetching current month project: {str(e)}'
        }), 500


@app.route('/api/get-project-steps', methods=['POST'])
def get_project_steps():
    """
    Use Perplexity AI to generate professional project implementation steps.
    
    Expected payload:
    {
        "projectTitle": "Sales Dashboard",
        "projectDescription": "Create a dashboard for sales analysis"
    }
    
    Returns AI-generated steps for implementing the project.
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'message': 'No data provided'
            }), 400
        
        project_title = data.get('projectTitle')
        project_description = data.get('projectDescription', '')
        
        if not project_title:
            return jsonify({
                'success': False,
                'message': 'Project title is required'
            }), 400
        
        print(f"\n=== Getting project steps from Perplexity AI ===")
        print(f"📋 Project: {project_title}")
        
        # Get Perplexity API key from environment
        api_key = os.getenv('PERPLEXITY_API_KEY')
        if not api_key:
            return jsonify({'success': False, 'message': 'Perplexity API key not configured'}), 500
        
        # Construct prompt for Perplexity
        prompt = f"""You are an expert software project manager helping a student build this SPECIFIC project: "{project_title}".

Project Description: {project_description if project_description else 'Not provided'}

Provide a detailed, step-by-step implementation guide SPECIFICALLY FOR THIS PROJECT. The steps must be tailored to building "{project_title}" - not generic software development steps.

CRITICAL Requirements:
1. Give 8-10 concrete steps SPECIFIC to building "{project_title}"
2. Mention the EXACT technologies, frameworks, and tools needed for THIS specific project type
3. Each step must be actionable and directly related to creating "{project_title}"
4. Include specific features, data structures, or algorithms relevant to THIS project
5. If it's a data analysis project - mention specific datasets, visualizations, and metrics
6. If it's a web app - mention specific UI components, API endpoints, and database schemas
7. If it's ML/AI - mention specific models, training steps, and evaluation metrics
8. Format each step clearly numbered (1., 2., 3., etc.)

DO NOT give generic software development advice. Every step must be directly applicable to building "{project_title}".

Example: If the project is "Sales Dashboard", mention "Connect to sales database", "Create revenue visualization charts", "Implement sales trend analysis", etc. - NOT generic steps like "Set up Git repository"."""
        
        # Call Perplexity API
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            'model': 'llama-3.1-sonar-small-128k-online',
            'messages': [
                {
                    'role': 'system',
                    'content': f'You are a technical expert specializing in {project_title}. Provide detailed, project-specific implementation guidance with exact technologies and steps tailored to this specific project type.'
                },
                {
                    'role': 'user',
                    'content': prompt
                }
            ],
            'temperature': 0.4,  # Increased for more creative, specific responses
            'max_tokens': 2000   # Increased for more detailed steps
        }
        
        print("🤖 Calling Perplexity API...")
        response = requests.post(
            'https://api.perplexity.ai/chat/completions',
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"❌ Perplexity API error: {response.status_code}")
            print(f"Response: {response.text}")
            
            # Provide fallback generic steps when API fails
            fallback_steps = [
                f"Research and understand the requirements for {project_title}",
                f"Set up project structure and choose appropriate tech stack for {project_title}",
                f"Design the architecture and data flow specific to {project_title}",
                f"Implement core features and functionality for {project_title}",
                f"Create user interface/visualization components for {project_title}",
                f"Add data processing and business logic for {project_title}",
                f"Implement testing and validation for {project_title}",
                f"Optimize performance and add error handling",
                f"Document the project with README and user guide",
                f"Deploy {project_title} and prepare demonstration"
            ]
            
            return jsonify({
                'success': True,
                'data': {
                    'steps': fallback_steps,
                    'rawText': 'Generic implementation steps (Perplexity API unavailable)',
                    'fallback': True
                }
            })
        
        result = response.json()
        steps_text = result['choices'][0]['message']['content']
        
        print(f"✅ Got steps from Perplexity AI ({len(steps_text)} chars)")
        
        # Parse steps from the response
        steps = []
        lines = steps_text.split('\n')
        current_step = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Check if line starts with a number (e.g., "1.", "1)", "Step 1:")
            import re
            step_match = re.match(r'^(\d+)[\.\)\:]?\s+(.+)', line)
            if step_match:
                if current_step:
                    steps.append(current_step)
                current_step = step_match.group(2).strip()
            elif current_step:
                # Continuation of previous step
                current_step += ' ' + line
        
        # Add last step
        if current_step:
            steps.append(current_step)
        
        # If parsing failed, return raw text split by double newlines
        if not steps:
            steps = [s.strip() for s in steps_text.split('\n\n') if s.strip()]
        
        print(f"📝 Parsed {len(steps)} steps")
        
        return jsonify({
            'success': True,
            'data': {
                'steps': steps,
                'rawText': steps_text
            }
        })
        
    except requests.exceptions.Timeout:
        return jsonify({
            'success': False,
            'message': 'Perplexity API request timed out'
        }), 504
    except requests.exceptions.RequestException as e:
        print(f"❌ Request error: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Failed to connect to Perplexity API: {str(e)}'
        }), 500
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'Error generating project steps: {str(e)}'
        }), 500


@app.route('/api/submit-project', methods=['POST'])
def submit_project():
    """
    Submit project for AI evaluation and feedback.
    Accepts project title, description, and file upload.
    Returns AI-generated feedback with scoring.
    """
    try:
        # Check if required data is present
        if 'mobile' not in request.form:
            return jsonify({
                'success': False,
                'message': 'Mobile number is required'
            }), 400
        
        mobile = request.form.get('mobile')
        project_title = request.form.get('title', '')
        project_description = request.form.get('description', '')
        
        if not project_title or not project_description:
            return jsonify({
                'success': False,
                'message': 'Project title and description are required'
            }), 400
        
        # Handle multiple file uploads and store complete file data
        uploaded_files = []
        files_info = []
        files_content = []
        
        # Check for multiple files in request
        if request.files:
            file_list = request.files.getlist('files[]')  # Multiple files
            if not file_list:
                # Fallback to single file upload
                single_file = request.files.get('file')
                if single_file and single_file.filename:
                    file_list = [single_file]
            
            # LIMIT: Maximum 10 files allowed
            if len(file_list) > 10:
                return jsonify({
                    'success': False,
                    'message': f'Too many files! Maximum 10 files allowed. You tried to upload {len(file_list)} files.'
                }), 400
            
            for project_file in file_list:
                if project_file and project_file.filename:
                    # Read file content
                    file_data = project_file.read()
                    file_size = len(file_data)
                    
                    # Store file information
                    file_info = {
                        'filename': project_file.filename,
                        'size': file_size,
                        'type': project_file.content_type,
                        'extension': project_file.filename.split('.')[-1] if '.' in project_file.filename else ''
                    }
                    
                    # Convert file to base64 for storage in MongoDB
                    import base64
                    file_content = base64.b64encode(file_data).decode('utf-8')
                    
                    uploaded_files.append(project_file.filename)
                    files_info.append(file_info)
                    files_content.append(file_content)
                    
                    print(f"File {len(uploaded_files)} stored: {file_info['filename']} ({file_size} bytes)")
                    project_file.seek(0)  # Reset file pointer
        
        print(f"\n=== Project Submission Received ===")
        print(f"Mobile: {mobile}")
        print(f"Title: {project_title}")
        print(f"Files: {len(uploaded_files)} file(s) uploaded")
        if uploaded_files:
            for idx, filename in enumerate(uploaded_files):
                print(f"  {idx+1}. {filename} ({files_info[idx]['size']} bytes)")
        else:
            print(f"Files: None")
        
        # Get current month project details from database
        db = get_db()
        roadmap_collection = db['Roadmap_Dashboard ']
        resume_collection = db['Resume']
        
        # Clean mobile number
        clean_mobile = ''.join(filter(str.isdigit, mobile))
        mobile_formats = [
            mobile,
            clean_mobile,
            clean_mobile[-10:],
            f"+91 {clean_mobile[-10:]}",
            f"+91{clean_mobile[-10:]}"
        ]
        mobile_formats = list(dict.fromkeys(mobile_formats))
        
        # Get user's current week and learning progress
        user_resume = resume_collection.find_one({'_id': {'$in': mobile_formats}})
        week_test_collection = db['week_test']
        week_test = week_test_collection.find_one({'_id': {'$in': mobile_formats}})
        
        if week_test and 'week' in week_test:
            current_week = week_test.get('week', 1)
            user_current_month = ((current_week - 1) // 4) + 1
        else:
            current_week = user_resume.get('currentWeek', 1) if user_resume else 1
            user_current_month = user_resume.get('currentMonth', 1) if user_resume else 1
        
        # Get roadmap to match project with correct month
        roadmap = roadmap_collection.find_one({'_id': {'$in': mobile_formats}})
        
        # Try to detect which month's project this is by matching title with expected projects
        detected_month = None
        all_month_projects = {}
        best_match_score = 0
        
        if roadmap:
            roadmap_data = roadmap.get('roadmap', roadmap)
            
            # Collect all month projects and try to match
            for month_num in range(1, 13):  # Check up to 12 months
                month_key = f"Month {month_num}"
                if month_key in roadmap_data:
                    month_data = roadmap_data[month_key]
                    expected_project = month_data.get('Mini Project', '')
                    
                    if expected_project:
                        all_month_projects[month_num] = expected_project
                        
                        # Calculate similarity score between submitted title and expected project
                        submitted_lower = project_title.lower()
                        expected_lower = expected_project.lower()
                        
                        # Count matching words
                        submitted_words = set(submitted_lower.split())
                        expected_words = set(expected_lower.split())
                        
                        # Remove common words
                        common_words = {'a', 'an', 'the', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'using', 'and', 'or'}
                        submitted_words = submitted_words - common_words
                        expected_words = expected_words - common_words
                        
                        # Calculate match score
                        if expected_words:
                            matching_words = submitted_words.intersection(expected_words)
                            match_score = len(matching_words) / len(expected_words)
                            
                            # Bonus if project title contains the expected project name
                            if expected_lower in submitted_lower or submitted_lower in expected_lower:
                                match_score += 0.5
                            
                            if match_score > best_match_score:
                                best_match_score = match_score
                                detected_month = month_num
        
        # Determine which month to use for evaluation
        if detected_month and best_match_score >= 0.3:  # 30% match threshold
            current_month = detected_month
            print(f"✅ Project matched to Month {current_month} project (match score: {best_match_score:.2f})")
            print(f"   Expected: {all_month_projects.get(current_month, 'N/A')}")
            print(f"   Submitted: {project_title}")
        else:
            # Fall back to user's current month
            current_month = user_current_month
            print(f"⚠️ Could not match project to any month (best score: {best_match_score:.2f})")
            print(f"   Using user's current month: Month {current_month}")
        
        # Get roadmap and extract skills learned in DETECTED/CURRENT MONTH ONLY
        expected_project = None
        learned_skills = []
        learned_topics = []
        weekly_topics_detailed = []  # Store week-by-week learning plan
        
        if roadmap:
            roadmap_data = roadmap.get('roadmap', roadmap)
            
            # Calculate current month's week range (only weeks in current month)
            month_start_week = ((current_month - 1) * 4) + 1
            month_end_week = min(current_month * 4, current_week)
            
            # Get current month data
            month_key = f"Month {current_month}"
            if month_key in roadmap_data:
                month_data = roadmap_data[month_key]
                
                # Extract SKILL FOCUS (main skills for the month)
                skill_focus = month_data.get('Skill Focus', '')
                if skill_focus:
                    # Split by commas and clean up
                    month_skills = [s.strip() for s in skill_focus.split(',')]
                    learned_skills.extend(month_skills)
                    print(f"📚 Month {current_month} Skill Focus: {skill_focus}")
                
                # Extract LEARNING GOALS
                learning_goals = month_data.get('Learning Goals', [])
                if isinstance(learning_goals, list):
                    for goal in learning_goals:
                        learned_topics.append(goal)
                    print(f"🎯 Learning Goals: {len(learning_goals)} goals")
                
                # Extract WEEKLY TOPICS from "Daily Plan (2 hours/day)"
                daily_plan = month_data.get('Daily Plan (2 hours/day)', [])
                if isinstance(daily_plan, list):
                    for week_idx, week_plan in enumerate(daily_plan, 1):
                        if isinstance(week_plan, str):
                            weekly_topics_detailed.append(f"Week {week_idx}: {week_plan}")
                            # Extract key topics from week plan
                            # Example: "Week 1: 30 mins theory on Linear Regression..."
                            week_lower = week_plan.lower()
                            # Extract technical terms (capitalized words or common ML/tech terms)
                            import re
                            # Find capitalized phrases (like "Linear Regression", "Logistic Regression")
                            capitalized_terms = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', week_plan)
                            learned_topics.extend(capitalized_terms)
                    print(f"📅 Weekly Topics: {len(daily_plan)} weeks of learning plan extracted")
                
                # Get expected project for current month
                expected_project = month_data.get('Mini Project', '')
                print(f"🚀 Expected Project: {expected_project}")
        
        # Remove duplicates and format
        learned_skills = list(dict.fromkeys(learned_skills))  # Remove duplicates while preserving order
        learned_topics = list(dict.fromkeys(learned_topics))
        
        skills_str = ', '.join(learned_skills) if learned_skills else 'Basic programming concepts'
        topics_str = ', '.join(learned_topics[:20]) if learned_topics else 'Fundamentals'  # Limit to first 20 topics
        weekly_plan_str = '\n'.join(weekly_topics_detailed) if weekly_topics_detailed else 'No weekly plan available'
        
        print(f"\n{'='*60}")
        print(f"📊 MONTH {current_month} LEARNING CONTEXT:")
        print(f"{'='*60}")
        print(f"Skills Learned: {skills_str[:200]}...")
        print(f"Topics Covered: {topics_str[:200]}...")
        print(f"Weekly Plan:")
        for week_topic in weekly_topics_detailed:
            print(f"  {week_topic[:100]}...")
        print(f"{'='*60}\n")
        
        # ANALYZE ALL UPLOADED FILES CONTENT
        all_files_analysis = []
        combined_code_snippet = ""
        has_code_file = False
        has_screenshot = False
        has_documentation = False
        total_quality_indicators = []
        total_detected_issues = []
        
        for idx, (file_info, file_content) in enumerate(zip(files_info, files_content)):
            file_analysis = {
                'file_number': idx + 1,
                'filename': file_info['filename'],
                'has_file': False,
                'is_code_file': False,
                'is_project_file': False,
                'file_type': None,
                'code_snippet': None,
                'file_structure': None,
                'detected_issues': [],
                'code_quality_indicators': []
            }
            try:
                # Decode file content from base64
                import base64
                decoded_content = base64.b64decode(file_content).decode('utf-8', errors='ignore')
                
                file_analysis['has_file'] = True
                
                # Check file type based on extension and filename
                filename = file_info['filename']
                filename_lower = filename.lower()
                extension = file_info.get('extension', '')
                file_ext = ('.' + extension.lower()) if extension else ''
                
                print(f"📄 Analyzing file: {filename} (ext: '{file_ext}', lower: '{filename_lower}')")
                
                # Code files
                code_extensions = ['.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.cpp', '.c', 
                                 '.cs', '.go', '.rb', '.php', '.html', '.css', '.sql', '.sh', '.bash']
                
                # Configuration and documentation files (treated as code for analysis)
                config_extensions = ['.json', '.xml', '.yaml', '.yml', '.toml', '.ini', '.env', '.config']
                doc_extensions = ['.md', '.txt', '.rst']  # README.md, etc.
                
                # Non-code but valid project files
                data_analysis_extensions = ['.pbix', '.xlsx', '.xls', '.csv', '.twbx', '.rmd', '.ipynb']
                design_extensions = ['.psd', '.ai', '.xd', '.fig', '.sketch']
                document_extensions = ['.pdf', '.docx', '.pptx']
                media_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.mp4', '.avi', '.mov']
                archive_extensions = ['.zip', '.rar', '.7z', '.tar', '.gz']
                
                # Check if it's a special file without extension (like .gitignore, Dockerfile, Makefile)
                is_special_file = (
                    filename_lower in ['.gitignore', '.dockerignore', '.editorconfig', 'dockerfile', 
                                      'makefile', 'rakefile', 'gemfile', 'procfile', 'jenkinsfile',
                                      'license', 'changelog', 'contributing', 'authors'] or
                    filename_lower.startswith('readme') or
                    filename == '.gitignore'  # Exact match for .gitignore
                )
                
                print(f"   Special file check: {is_special_file}, File ext: '{file_ext}'")
                
                file_analysis['is_code_file'] = (file_ext in code_extensions or 
                                                 file_ext in config_extensions or 
                                                 file_ext in doc_extensions or
                                                 is_special_file)
                file_analysis['is_project_file'] = file_ext in (data_analysis_extensions + design_extensions + 
                                                                 document_extensions + media_extensions + archive_extensions)
                
                # Determine file type category
                if file_ext in data_analysis_extensions:
                    file_analysis['file_type'] = 'data_analysis'
                elif file_ext in design_extensions:
                    file_analysis['file_type'] = 'design'
                elif file_ext in document_extensions:
                    file_analysis['file_type'] = 'document'
                elif file_ext in media_extensions:
                    file_analysis['file_type'] = 'media'
                elif file_ext in archive_extensions:
                    file_analysis['file_type'] = 'archive'
                elif file_ext in config_extensions:
                    file_analysis['file_type'] = 'config'
                elif file_ext in doc_extensions or is_special_file:
                    file_analysis['file_type'] = 'documentation'
                elif file_analysis['is_code_file']:
                    file_analysis['file_type'] = 'code'
                else:
                    file_analysis['file_type'] = 'other'
                
                if file_analysis['is_code_file'] and decoded_content:
                    # Extract code snippet (first 100000 chars = ~2000 lines for full project analysis)
                    snippet_length = min(len(decoded_content), 100000)
                    file_analysis['code_snippet'] = decoded_content[:snippet_length]
                    if len(decoded_content) > 100000:
                        file_analysis['code_snippet'] += "\n\n... (file continues beyond 100000 characters)"
                    
                    # Analyze code structure
                    lines = decoded_content.split('\n')
                    file_analysis['file_structure'] = {
                        'total_lines': len(lines),
                        'non_empty_lines': len([l for l in lines if l.strip()]),
                        'comment_lines': len([l for l in lines if l.strip().startswith(('#', '//', '/*', '*', '<!--'))]),
                    }
                    
                    # Check for code quality indicators
                    content_lower = decoded_content.lower()
                    
                    # Check for special project files
                    if filename_lower == '.gitignore':
                        file_analysis['code_quality_indicators'].append('Has .gitignore - good version control practice')
                        if len(lines) >= 5:
                            file_analysis['code_quality_indicators'].append('Comprehensive .gitignore with multiple rules')
                    
                    if filename_lower.startswith('readme'):
                        file_analysis['code_quality_indicators'].append('Has README - good documentation practice')
                        if file_analysis['file_structure']['total_lines'] >= 20:
                            file_analysis['code_quality_indicators'].append('Detailed README with comprehensive documentation')
                        elif file_analysis['file_structure']['total_lines'] >= 10:
                            file_analysis['code_quality_indicators'].append('README includes basic project information')
                    
                    if file_ext == '.json' and 'package.json' in filename_lower:
                        file_analysis['code_quality_indicators'].append('Has package.json - proper Node.js project structure')
                    
                    if file_ext == '.json' and any(name in filename_lower for name in ['tsconfig', 'eslint', 'prettier']):
                        file_analysis['code_quality_indicators'].append('Has configuration files - professional setup')
                    
                    # Positive indicators for code files
                    if 'def ' in decoded_content or 'function ' in decoded_content or 'class ' in decoded_content:
                        file_analysis['code_quality_indicators'].append('Contains functions/classes')
                    
                    if 'try' in content_lower and ('except' in content_lower or 'catch' in content_lower):
                        file_analysis['code_quality_indicators'].append('Has error handling')
                    
                    if 'test' in content_lower or 'assert' in content_lower:
                        file_analysis['code_quality_indicators'].append('Includes testing code')
                    
                    if any(word in content_lower for word in ['import', 'require', 'include', 'using']):
                        file_analysis['code_quality_indicators'].append('Uses external libraries')
                    
                    # Detect potential issues (but not for README, .gitignore, config files)
                    if file_analysis['file_type'] not in ['documentation', 'config']:
                        if file_analysis['file_structure']['total_lines'] < 20:
                            file_analysis['detected_issues'].append('File too short - likely incomplete')
                    
                    # Only check for comments in actual source code files (not HTML, CSS, config, docs)
                    if file_analysis['file_type'] == 'code' and file_analysis['file_structure']['comment_lines'] == 0:
                        if file_ext in ['.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.cpp', '.c', '.cs']:
                            file_analysis['detected_issues'].append('No comments found - consider adding code comments')
                    
                    if 'lorem ipsum' in content_lower or 'placeholder' in content_lower:
                        file_analysis['detected_issues'].append('Contains placeholder/dummy content')
                    
                    # Check if code mentions learned skills
                    skills_in_code = []
                    for skill in learned_skills:
                        if skill.lower() in content_lower:
                            skills_in_code.append(skill)
                    
                    if skills_in_code:
                        file_analysis['code_quality_indicators'].append(f'Uses Month {current_month} skills: {", ".join(skills_in_code[:3])}')
                    else:
                        file_analysis['detected_issues'].append(f'No Month {current_month} skills evident in code')
                    
                    # Check for random/irrelevant content (but exclude special files)
                    code_keywords = ['function', 'def', 'class', 'const', 'var', 'let', 'import', 
                                   'return', 'if', 'for', 'while', 'public', 'private', 'div', 'body', 
                                   'html', 'style', 'color', 'font', 'margin', 'padding', 'width', 'height']
                    keyword_count = sum(1 for kw in code_keywords if kw in content_lower)
                    
                    # Only flag as "not code" if it's supposed to be a code file and has no code indicators
                    if keyword_count < 2 and file_analysis['file_type'] == 'code' and not is_special_file:
                        file_analysis['detected_issues'].append('File may not contain actual code')
                    
                    # IMPORTANT: Code files should ALWAYS be marked as project files
                    # Do NOT set is_project_file = False for code files, even if they have issues
                    file_analysis['is_project_file'] = True
                
                elif file_analysis['is_project_file']:
                    # Valid non-code project file (Power BI, Excel, Design, etc.)
                    file_size_kb = file_info.get('size', 0) / 1024
                    file_analysis['file_structure'] = {
                        'file_type': file_analysis['file_type'],
                        'file_size_kb': round(file_size_kb, 2),
                        'file_extension': file_ext
                    }
                    
                    # Try to extract content from analyzable file types
                    extracted_content = None
                    
                    try:
                        # EXCEL FILES (.xlsx, .xls, .csv)
                        if file_ext in ['.xlsx', '.xls', '.csv']:
                            try:
                                import pandas as pd
                                from io import BytesIO
                                
                                file_bytes = base64.b64decode(file_content)
                                
                                if file_ext == '.csv':
                                    df = pd.read_csv(BytesIO(file_bytes))
                                    sheet_names = ['CSV']
                                else:
                                    excel_file = pd.ExcelFile(BytesIO(file_bytes))
                                    sheet_names = excel_file.sheet_names
                                    df = pd.read_excel(BytesIO(file_bytes), sheet_name=0)
                                
                                extracted_content = f"""EXCEL FILE ANALYSIS:
- Sheets: {', '.join(sheet_names) if file_ext != '.csv' else 'CSV (single sheet)'}
- Columns: {', '.join(df.columns.tolist()[:10])} {'...' if len(df.columns) > 10 else ''}
- Rows: {len(df)}
- Data Sample (first 3 rows):
{df.head(3).to_string()}

- Contains Formulas: {('YES' if file_ext in ['.xlsx', '.xls'] else 'N/A')}
- Month Skills Check: Looking for {', '.join(learned_skills[:5])} in column names/data"""
                                
                                # Check if Month skills appear in column names or data
                                excel_text = ' '.join(df.columns.tolist()).lower()
                                skills_found = [s for s in learned_skills if s.lower() in excel_text]
                                if skills_found:
                                    file_analysis['code_quality_indicators'].append(f'Excel contains Month skills in columns: {", ".join(skills_found[:3])}')
                                    
                            except Exception as e:
                                extracted_content = f"Excel file uploaded but couldn't parse: {str(e)}"
                        
                        # JUPYTER NOTEBOOKS (.ipynb)
                        elif file_ext == '.ipynb':
                            try:
                                import json as json_module
                                notebook_data = json_module.loads(decoded_content)
                                
                                cells = notebook_data.get('cells', [])
                                code_cells = [c for c in cells if c.get('cell_type') == 'code']
                                markdown_cells = [c for c in cells if c.get('cell_type') == 'markdown']
                                
                                # Extract first few code cells
                                code_samples = []
                                for cell in code_cells[:3]:
                                    code = ''.join(cell.get('source', []))
                                    code_samples.append(code[:500])
                                
                                extracted_content = f"""JUPYTER NOTEBOOK ANALYSIS:
- Total Cells: {len(cells)}
- Code Cells: {len(code_cells)}
- Markdown Cells: {len(markdown_cells)}

Sample Code Cells:
{chr(10).join([f"Cell {i+1}:{chr(10)}{code}" for i, code in enumerate(code_samples)])}

- Month Skills Check: Looking for {', '.join(learned_skills[:5])} in notebook"""
                                
                                # Check for Month skills in code
                                notebook_text = ' '.join([' '.join(c.get('source', [])) for c in cells]).lower()
                                skills_found = [s for s in learned_skills if s.lower() in notebook_text]
                                if skills_found:
                                    file_analysis['code_quality_indicators'].append(f'Notebook uses Month skills: {", ".join(skills_found[:3])}')
                                    
                            except Exception as e:
                                extracted_content = f"Jupyter notebook uploaded but couldn't parse: {str(e)}"
                        
                        # POWER BI FILES (.pbix)
                        elif file_ext == '.pbix':
                            try:
                                file_bytes = base64.b64decode(file_content)
                                
                                # .pbix is a ZIP file containing DataModel and other files
                                with zipfile.ZipFile(BytesIO(file_bytes)) as pbix_zip:
                                    file_list = pbix_zip.namelist()
                                    
                                    # Try to read DataModelSchema
                                    if 'DataModelSchema' in file_list:
                                        schema_data = pbix_zip.read('DataModelSchema').decode('utf-16-le', errors='ignore')
                                        
                                        # Extract table/measure names (basic parsing)
                                        tables_found = []
                                        measures_found = []
                                        
                                        # Simple keyword search
                                        if 'table' in schema_data.lower():
                                            tables_found = ['Found tables in model']
                                        if 'measure' in schema_data.lower() or 'dax' in schema_data.lower():
                                            measures_found = ['Found DAX measures']
                                        
                                        extracted_content = f"""POWER BI FILE ANALYSIS:
- File Structure: {len(file_list)} components
- Contains: {', '.join(file_list[:5])}
- Data Model: {'Present' if 'DataModelSchema' in file_list else 'Not found'}
- Tables: {', '.join(tables_found) if tables_found else 'Could not extract'}
- Measures/DAX: {', '.join(measures_found) if measures_found else 'Could not extract'}

- Month Skills Check: Looking for {', '.join(learned_skills[:5])} in Power BI model"""
                                        
                                        # Check for Month skills in schema
                                        skills_found = [s for s in learned_skills if s.lower() in schema_data.lower()]
                                        if skills_found:
                                            file_analysis['code_quality_indicators'].append(f'Power BI uses Month skills: {", ".join(skills_found[:3])}')
                                    else:
                                        extracted_content = "Power BI file structure detected but couldn't extract model details"
                                        
                            except Exception as e:
                                extracted_content = f"Power BI file uploaded but couldn't parse: {str(e)}"
                        
                        # PDF FILES (.pdf)
                        elif file_ext == '.pdf':
                            try:
                                import PyPDF2
                                file_bytes = base64.b64decode(file_content)
                                
                                pdf_reader = PyPDF2.PdfReader(BytesIO(file_bytes))
                                num_pages = len(pdf_reader.pages)
                                
                                # Extract text from first 3 pages
                                text_content = ""
                                for i in range(min(3, num_pages)):
                                    text_content += pdf_reader.pages[i].extract_text()
                                
                                extracted_content = f"""PDF DOCUMENT ANALYSIS:
- Pages: {num_pages}
- Text Sample (first 1000 chars):
{text_content[:1000]}

- Month Skills Check: Looking for {', '.join(learned_skills[:5])} in document"""
                                
                                # Check for Month skills in PDF text
                                skills_found = [s for s in learned_skills if s.lower() in text_content.lower()]
                                if skills_found:
                                    file_analysis['code_quality_indicators'].append(f'PDF mentions Month skills: {", ".join(skills_found[:3])}')
                                    
                            except Exception as e:
                                extracted_content = f"PDF uploaded but couldn't extract text: {str(e)}"
                        
                        # IMAGE/SCREENSHOT FILES (.png, .jpg, .jpeg, .gif)
                        elif file_ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp']:
                            try:
                                from PIL import Image
                                file_bytes = base64.b64decode(file_content)
                                
                                # Open image
                                image = Image.open(BytesIO(file_bytes))
                                img_width, img_height = image.size
                                
                                # === VISUAL IMAGE ANALYSIS USING AI ===
                                visual_analysis = None
                                try:
                                    # Use OpenAI GPT-4 Vision to analyze what's in the image
                                    openai_api_key = os.getenv('OPENAI_API_KEY', '')
                                    
                                    if openai_api_key:
                                        # Convert image to base64 for API
                                        img_base64 = file_content  # Already in base64
                                        
                                        vision_headers = {
                                            'Authorization': f'Bearer {openai_api_key}',
                                            'Content-Type': 'application/json'
                                        }
                                        
                                        vision_payload = {
                                            'model': 'gpt-4o',  # GPT-4 with vision
                                            'messages': [
                                                {
                                                    'role': 'user',
                                                    'content': [
                                                        {
                                                            'type': 'text',
                                                            'text': f'''You are a STRICT evaluator checking if an image is relevant to a student's project submission.

PROJECT DETAILS:
- Title: "{project_title}"
- Description: "{project_description[:200]}"
- Expected Skills: {', '.join(learned_skills[:5])}

ANALYZE THIS IMAGE AND ANSWER:

🚨 CRITICAL QUESTION: Does this image show the ACTUAL PROJECT described above?

FOR THIS SPECIFIC PROJECT "{project_title}":
- If it's a PORTFOLIO/WEBSITE project → Image MUST show HTML/CSS code OR the actual website interface
- If it's a DATA ANALYSIS project → Image MUST show charts/graphs/Excel/Python analysis OR code
- If it's a MACHINE LEARNING project → Image MUST show model code, Jupyter notebook, or prediction results
- If it's a DASHBOARD project → Image MUST show the actual dashboard interface OR Power BI/Tableau

MARK AS "NOT TECHNICAL:" IF IMAGE SHOWS:
❌ Random person photo (selfie, portrait, people)
❌ Movie/TV show scene (Breaking Bad, any character, actor)
❌ Vehicle/motorcycle/car/gas station
❌ Nature/buildings/street/outdoor scene
❌ Quiz results/test scores from OTHER websites (not the project itself)
❌ Stock images or downloaded pictures
❌ Memes, jokes, or entertainment content
❌ Screenshots of UNRELATED websites/tutorials (not student's own work)
❌ Any photo that does NOT show the student's project implementation

MARK AS "TECHNICAL:" ONLY IF IMAGE SHOWS:
✅ The ACTUAL project code in an editor (VS Code, Jupyter, PyCharm)
✅ The ACTUAL project running (website, app, dashboard, terminal output)
✅ Project-specific data visualizations (charts/graphs created for THIS project)
✅ Technical diagrams/documentation FOR THIS PROJECT
✅ Database/API responses FROM THIS PROJECT

RESPONSE FORMAT:
Start with EITHER "TECHNICAL:" OR "NOT TECHNICAL:"
Then explain in 1 sentence what you see and if it matches the project "{project_title}".

Example responses:
"NOT TECHNICAL: Shows a photograph of a person at a gas station. No connection to project."
"NOT TECHNICAL: Shows quiz results from a different website, not the student's portfolio project."
"TECHNICAL: Shows HTML/CSS code in VS Code editor for building a portfolio website."
"TECHNICAL: Shows the actual running portfolio website with navigation and sections."'''
                                                        },
                                                        {
                                                            'type': 'image_url',
                                                            'image_url': {
                                                                'url': f'data:image/jpeg;base64,{img_base64}'
                                                            }
                                                        }
                                                    ]
                                                }
                                            ],
                                            'max_tokens': 250,
                                            'temperature': 0.2
                                        }
                                        
                                        print(f"🔍 Analyzing image '{file_info['filename']}' with AI Vision...")
                                        vision_response = requests.post(
                                            'https://api.openai.com/v1/chat/completions',
                                            headers=vision_headers,
                                            json=vision_payload,
                                            timeout=30
                                        )
                                        
                                        if vision_response.status_code == 200:
                                            vision_result = vision_response.json()
                                            visual_analysis = vision_result['choices'][0]['message']['content']
                                            print(f"✅ Visual Analysis: {visual_analysis[:100]}...")
                                        else:
                                            print(f"⚠️ Vision API failed: {vision_response.status_code}")
                                    
                                except Exception as vision_err:
                                    print(f"⚠️ Visual analysis error: {str(vision_err)}")
                                
                                # Try OCR if Tesseract is available
                                ocr_text = None
                                ocr_available = False
                                
                                try:
                                    import pytesseract  # type: ignore
                                    # Configure Tesseract path for Windows
                                    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
                                    ocr_text = pytesseract.image_to_string(image)
                                    ocr_available = True
                                except Exception as ocr_err:
                                    # Tesseract not installed or pytesseract error
                                    print(f"OCR not available: {str(ocr_err)}")
                                
                                # Combine visual analysis and OCR
                                if visual_analysis:
                                    # AI Vision analysis available - use it for relevance check
                                    visual_lower = visual_analysis.lower()
                                    
                                    # NEW: Check for explicit markers in response
                                    starts_with_technical = visual_analysis.strip().upper().startswith('TECHNICAL:')
                                    starts_with_not_technical = visual_analysis.strip().upper().startswith('NOT TECHNICAL:')
                                    
                                    # Primary detection: Check the explicit markers
                                    if starts_with_not_technical:
                                        is_irrelevant = True
                                        is_relevant_technical = False
                                    elif starts_with_technical:
                                        is_irrelevant = False
                                        is_relevant_technical = True
                                    else:
                                        # Fallback: Check keywords if AI didn't use markers
                                        # Check if AI detected irrelevant content (movie/TV scenes, random photos, people)
                                        is_irrelevant = any(keyword in visual_lower for keyword in [
                                            'not technical', 'non-technical', 'irrelevant', 'not relevant', 
                                            'unrelated', 'movie', 'film', 'tv show', 'television', 'series',
                                            'actor', 'character', 'scene from', 'drama',
                                            'random photo', 'random image', 'photograph of', 
                                            'photo of a person', 'photo of people', 'photo shows a person',
                                            'picture of a person', 'man in', 'woman in', 'people in',
                                            'motorcycle', 'bike', 'vehicle', 'car', 'gas station', 'fueling',
                                            'outdoors', 'outdoor scene', 'street', 'building exterior'
                                        ])
                                        
                                        # Check if AI detected relevant technical content - be VERY specific
                                        is_relevant_technical = any(keyword in visual_lower for keyword in [
                                            'code editor', 'vs code', 'visual studio', 'pycharm', 'jupyter',
                                            'terminal output', 'console output', 'command prompt', 'shell',
                                            'data visualization', 'chart', 'graph', 'plot', 'scatter',
                                            'machine learning', 'model output', 'prediction result',
                                            'web application', 'user interface', 'dashboard', 'webpage',
                                            'database', 'sql', 'api', 'json', 'xml', 'code snippet',
                                            'programming', 'script', 'algorithm', 'data table'
                                        ]) and not is_irrelevant
                                    
                                    extracted_content = f"""IMAGE/SCREENSHOT ANALYSIS (AI Vision):
- Dimensions: {img_width}x{img_height} pixels
- Format: {image.format}
- File Size: {round(len(file_bytes)/1024, 2)}KB

AI VISUAL ANALYSIS:
{visual_analysis}

PROJECT RELEVANCE: {"RELEVANT - Shows technical/project content" if is_relevant_technical and not is_irrelevant else "IRRELEVANT - Not related to project" if is_irrelevant else "UNCERTAIN - Description should explain"}
"""
                                    
                                    print(f"AI Decision: Irrelevant={is_irrelevant}, Technical={is_relevant_technical}")
                                    
                                    if is_irrelevant or not is_relevant_technical:
                                        # If either clearly irrelevant OR not clearly technical, mark as irrelevant
                                        file_analysis['detected_issues'].append(f'IRRELEVANT FILE: AI Vision detected non-project content - {visual_analysis[:100]}')
                                        file_analysis['is_project_file'] = False
                                        print(f"Marked as IRRELEVANT: {file_info['filename']}")
                                    else:
                                        # Only mark as relevant if clearly technical
                                        file_analysis['code_quality_indicators'].append(f'AI Vision confirmed relevant: {visual_analysis[:80]}')
                                        file_analysis['is_project_file'] = True
                                        print(f"Marked as RELEVANT: {file_info['filename']}")
                                    
                                    # Add OCR text if available
                                    if ocr_available and ocr_text and len(ocr_text.strip()) > 0:
                                        extracted_content += f"\n\nEXTRACTED TEXT (OCR):\n{ocr_text[:1000]}"
                                
                                elif ocr_available and ocr_text:
                                    # No AI Vision, but OCR available - use text-based analysis
                                    
                                    # Check if screenshot is IRRELEVANT to the project
                                    ocr_lower = ocr_text.lower()
                                    project_title_lower = project_title.lower()
                                    project_desc_lower = project_description.lower()
                                    
                                    # Extract key project keywords
                                    project_keywords = set(project_title_lower.split() + project_desc_lower.split()) - {
                                        'a', 'an', 'the', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'using', 
                                        'and', 'or', 'is', 'are', 'was', 'were', 'project', 'description'
                                    }
                                    
                                    # Check for completely unrelated content in screenshot
                                    unrelated_indicators = [
                                        'test completed', 'quiz result', 'exam score', 'total questions',
                                        'correct answer', 'wrong answer', 'your score', 'marks obtained',
                                        'test result', 'assessment result', 'percentage score'
                                    ]
                                    
                                    is_unrelated_test = any(indicator in ocr_lower for indicator in unrelated_indicators)
                                    
                                    # Check if screenshot text relates to project at all
                                    matching_keywords = [kw for kw in project_keywords if len(kw) > 3 and kw in ocr_lower]
                                    relevance_ratio = len(matching_keywords) / max(len(project_keywords), 1) if project_keywords else 0
                                    relevance_percentage = relevance_ratio * 100
                                    
                                    extracted_content = f"""IMAGE/SCREENSHOT ANALYSIS:
- Dimensions: {img_width}x{img_height} pixels
- Format: {image.format}
- Mode: {image.mode}

EXTRACTED TEXT (OCR):
{ocr_text[:2000] if text_length > 0 else 'No text detected in image'}

PROJECT RELEVANCE CHECK:
- Project Title: {project_title}
- Keywords matching: {matching_keywords if matching_keywords else 'NONE'}
- Relevance: {round(relevance_percentage, 1)} percent match with project keywords"""
                                    
                                    # Mark as IRRELEVANT if it's clearly unrelated
                                    if is_unrelated_test:
                                        file_analysis['detected_issues'].append('IRRELEVANT FILE: Screenshot shows test/quiz results, NOT project content')
                                        file_analysis['is_project_file'] = False  # Mark as NOT a valid project file
                                    elif relevance_ratio < 0.1 and text_length > 50:
                                        file_analysis['detected_issues'].append(f'IRRELEVANT FILE: Screenshot text does not relate to project "{project_title}"')
                                        file_analysis['is_project_file'] = False
                                    elif text_length > 0:
                                        # Check for Month skills in OCR text
                                        skills_found = [s for s in learned_skills if s.lower() in ocr_lower]
                                        if skills_found:
                                            file_analysis['code_quality_indicators'].append(f'Screenshot contains Month skills: {", ".join(skills_found[:3])}')
                                        
                                        # Check for code indicators in screenshot
                                        code_indicators = ['function', 'class', 'def', 'import', 'const', 'var', 'print', '()', '{}', 'return']
                                        if any(indicator in ocr_text for indicator in code_indicators):
                                            file_analysis['code_quality_indicators'].append('Screenshot shows code/technical content')
                                        
                                        # Check for UI/dashboard indicators
                                        ui_indicators = ['dashboard', 'chart', 'graph', 'button', 'menu', 'page', 'interface']
                                        if any(indicator in ocr_lower for indicator in ui_indicators):
                                            file_analysis['code_quality_indicators'].append('Screenshot shows UI/dashboard/visualization')
                                        
                                        # Check if screenshot relates to project topic
                                        if matching_keywords:
                                            file_analysis['code_quality_indicators'].append(f'Screenshot relates to project: {", ".join(matching_keywords[:3])}')
                                    else:
                                        file_analysis['detected_issues'].append('Screenshot has no visible text (may be blank or graphic-only)')
                                else:
                                    # OCR not available OR no text in image - need visual analysis
                                    # Check if this is a photograph vs technical screenshot
                                    
                                    # If OCR extracted no/minimal text, likely not a technical screenshot
                                    has_minimal_text = ocr_text and len(ocr_text.strip()) < 20 if ocr_text else True
                                    
                                    # Check description for screenshot explanation
                                    desc_lower = project_description.lower()
                                    screenshot_keywords = ['screenshot', 'output', 'result', 'visualization', 'chart', 
                                                          'graph', 'plot', 'prediction', 'model', 'dashboard', 'interface',
                                                          'code', 'terminal', 'jupyter', 'notebook', 'console']
                                    mentions_screenshot = any(kw in desc_lower for kw in screenshot_keywords)
                                    
                                    extracted_content = f"""IMAGE/SCREENSHOT ANALYSIS:
- Dimensions: {img_width}x{img_height} pixels
- Format: {image.format}
- Mode: {image.mode}
- File Size: {round(len(file_bytes)/1024, 2)}KB

TEXT EXTRACTION: {"No text detected (likely photograph or graphic)" if has_minimal_text else "Text extraction not available"}

PROJECT RELEVANCE CHECK:
- This appears to be {"a photograph or graphic image" if has_minimal_text else "an image file"}
- For house price prediction project, relevant screenshots should show:
  * Code editor/Jupyter notebook with ML code
  * Visualizations (scatter plots, prediction charts, correlation matrices)
  * Model output (predictions, accuracy metrics, R-squared scores)
  * Data tables or analysis results
  
- Description mentions screenshots: {"YES" if mentions_screenshot else "NO - This is suspicious"}

WARNING: If this is just a random photo unrelated to your project, it will receive 0 marks."""
                                    
                                    # If image has no text AND description doesn't mention screenshots = likely irrelevant
                                    if has_minimal_text and not mentions_screenshot:
                                        file_analysis['detected_issues'].append('SUSPECTED IRRELEVANT FILE: Image has no text, description does not explain this screenshot')
                                        file_analysis['is_project_file'] = False
                                    elif has_minimal_text:
                                        file_analysis['detected_issues'].append('WARNING: Image contains no text - must be explained in description')
                                        # Still mark as project file but with warning
                                    
                                    if not has_minimal_text:
                                        file_analysis['code_quality_indicators'].append(f'Screenshot uploaded ({img_width}x{img_height}, {round(len(file_bytes)/1024, 2)}KB)')
                                        file_analysis['detected_issues'].append('OCR not available - relying on description to verify content')
                                    
                            except Exception as e:
                                extracted_content = f"Image/Screenshot uploaded but couldn't analyze: {str(e)}"
                        
                        # ZIP/ARCHIVE FILES (.zip, .rar, .7z)
                        elif file_ext in ['.zip', '.rar', '.7z', '.tar', '.gz']:
                            try:
                                file_bytes = base64.b64decode(file_content)
                                file_size_kb = len(file_bytes) / 1024
                                
                                print(f"📦 Attempting to extract ZIP: {file_info['filename']} ({round(file_size_kb, 2)}KB)")
                                
                                if file_ext == '.zip':
                                    # Analyze ZIP contents
                                    try:
                                        with zipfile.ZipFile(BytesIO(file_bytes)) as zip_file:
                                            # Test if ZIP is valid
                                            test_result = zip_file.testzip()
                                            if test_result:
                                                print(f"⚠️ ZIP has corrupted file: {test_result}")
                                                extracted_content = f"ZIP file appears corrupted - file '{test_result}' has errors"
                                                file_analysis['detected_issues'].append(f'ZIP file corrupted - cannot extract "{test_result}"')
                                                file_analysis['is_project_file'] = False
                                            else:
                                                print(f"✅ ZIP is valid - extracting contents...")
                                                
                                                file_list = zip_file.namelist()
                                                total_files = len(file_list)
                                                
                                                print(f"📋 ZIP contains {total_files} files: {', '.join(file_list[:5])}{'...' if total_files > 5 else ''}")
                                                
                                                # Count file types in ZIP
                                                code_files = [f for f in file_list if any(f.lower().endswith(ext) for ext in ['.py', '.js', '.html', '.css', '.java', '.cpp', '.c', '.ts', '.jsx', '.php', '.rb'])]
                                                image_files = [f for f in file_list if any(f.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif'])]
                                                doc_files = [f for f in file_list if any(f.lower().endswith(ext) for ext in ['.pdf', '.docx', '.txt', '.md']) or f.lower().startswith('readme')]
                                                config_files = [f for f in file_list if any(f.lower().endswith(ext) for ext in ['.json', '.xml', '.yaml', '.yml', '.toml', '.env', '.config']) or any(name in f.lower() for name in ['.gitignore', '.dockerignore', 'dockerfile', 'makefile'])]
                                                
                                                print(f"📊 File breakdown: Code={len(code_files)}, Config={len(config_files)}, Images={len(image_files)}, Docs={len(doc_files)}")
                                                
                                                # Try to extract and analyze main code files
                                                extracted_code = ""
                                                for code_file_name in code_files[:3]:  # Analyze first 3 code files
                                                    try:
                                                        code_content = zip_file.read(code_file_name).decode('utf-8', errors='ignore')
                                                        extracted_code += f"\n\n=== {code_file_name} ===\n{code_content[:5000]}"
                                                        print(f"✅ Extracted {len(code_content)} chars from {code_file_name}")
                                                    except Exception as e:
                                                        print(f"⚠️ Could not extract {code_file_name}: {str(e)}")
                                                
                                                extracted_content = f"""ZIP ARCHIVE ANALYSIS:
- Total Files: {total_files}
- Code Files: {len(code_files)} ({', '.join(code_files[:5])}{'...' if len(code_files) > 5 else ''})
- Config/Documentation: {len(config_files)} ({', '.join(config_files[:3])}{'...' if len(config_files) > 3 else ''})
- Images: {len(image_files)}
- Documents: {len(doc_files)}
- Archive Size: {round(file_size_kb, 2)}KB

PROJECT STRUCTURE:
{chr(10).join(['  ' + f for f in file_list[:15]])}
{'  ...' if total_files > 15 else ''}

{"CODE SAMPLES:" + extracted_code[:5000] if extracted_code else "No code files found in ZIP"}

- Month Skills Check: Looking for {', '.join(learned_skills[:5])} in project files"""
                                        
                                        # Analyze quality indicators
                                        if len(code_files) > 0:
                                            file_analysis['code_quality_indicators'].append(f'Contains {len(code_files)} code file(s) - shows implementation')
                                            has_code_file = True  # Set global flag
                                            
                                            if extracted_code:
                                                combined_code_snippet += extracted_code  # Add to combined analysis
                                        
                                        if len(image_files) > 0:
                                            file_analysis['code_quality_indicators'].append(f'Contains {len(image_files)} screenshot(s) - shows project output')
                                        
                                        if len(doc_files) > 0:
                                            file_analysis['code_quality_indicators'].append(f'Contains {len(doc_files)} document(s) - includes documentation')
                                        
                                        if len(config_files) > 0:
                                            file_analysis['code_quality_indicators'].append(f'Contains {len(config_files)} config/project file(s) - professional setup')
                                            
                                            # Check for specific important files
                                            has_gitignore = any('.gitignore' in f.lower() for f in config_files)
                                            has_readme = any('readme' in f.lower() for f in doc_files + config_files)
                                            
                                            if has_gitignore:
                                                file_analysis['code_quality_indicators'].append('Has .gitignore - good version control practice')
                                            if has_readme:
                                                file_analysis['code_quality_indicators'].append('Has README - good documentation practice')
                                        
                                        # Check for Month skills in extracted code
                                        if extracted_code:
                                            skills_found = [s for s in learned_skills if s.lower() in extracted_code.lower()]
                                            if skills_found:
                                                file_analysis['code_quality_indicators'].append(f'ZIP contains Month skills: {", ".join(skills_found[:3])}')
                                        
                                        # Quality checks
                                        if total_files < 3:
                                            file_analysis['detected_issues'].append('ZIP contains very few files - may be incomplete')
                                        
                                        if len(code_files) == 0:
                                            file_analysis['detected_issues'].append('ZIP contains no code files - cannot verify implementation')
                                        
                                        if file_size_kb < 5:
                                            file_analysis['detected_issues'].append(f'ZIP is very small ({round(file_size_kb, 2)}KB) - likely incomplete')
                                    
                                    except zipfile.BadZipFile as e:
                                        print(f"❌ ZIP extraction failed: Invalid or corrupted ZIP file - {str(e)}")
                                        extracted_content = f"ZIP file is corrupted or invalid - cannot extract contents"
                                        file_analysis['detected_issues'].append(f'ZIP file corrupted/unextractable - suspiciously small ({round(file_size_kb, 2)}KB), providing zero evidence of work')
                                        file_analysis['is_project_file'] = False
                                    except Exception as e:
                                        print(f"❌ ZIP extraction error: {str(e)}")
                                        extracted_content = f"Error extracting ZIP: {str(e)}"
                                        file_analysis['detected_issues'].append(f'Cannot extract ZIP file: {str(e)[:100]}')
                                        file_analysis['is_project_file'] = False
                                        
                                else:
                                    # Non-ZIP archives (.rar, .7z, etc.)
                                    extracted_content = f"""ARCHIVE FILE ANALYSIS:
- Type: {file_ext.upper()} archive
- Size: {round(file_size_kb, 2)}KB

NOTE: {file_ext.upper()} archives need to be extracted manually. For automated analysis, please upload ZIP files."""
                                    file_analysis['code_quality_indicators'].append(f'{file_ext.upper()} archive uploaded ({round(file_size_kb, 2)}KB)')
                                    file_analysis['detected_issues'].append(f'Cannot automatically analyze {file_ext.upper()} files - use .zip format for better analysis')
                                
                            except Exception as e:
                                extracted_content = f"Archive file uploaded but couldn't analyze: {str(e)}"
                                file_analysis['detected_issues'].append(f'Could not extract archive contents: {str(e)[:100]}')
                    
                    except Exception as e:
                        print(f"Error extracting content from project file: {str(e)}")
                    
                    # Store extracted content if available
                    if extracted_content:
                        file_analysis['code_snippet'] = extracted_content
                        file_analysis['code_quality_indicators'].append(f'Successfully extracted content from {file_analysis["file_type"]} file')
                    
                    # For project files, check if file size is reasonable (not empty/too small)
                    if file_size_kb < 10:
                        file_analysis['detected_issues'].append(f'File too small ({round(file_size_kb, 2)}KB) - may be incomplete')
                    else:
                        if not extracted_content:
                            file_analysis['code_quality_indicators'].append(f'Valid {file_analysis["file_type"]} project file uploaded ({round(file_size_kb, 2)}KB)')
                    
                    # Check if description mentions what's in the file
                    file_type_keywords = {
                        'data_analysis': ['dashboard', 'visualization', 'chart', 'graph', 'report', 'analysis', 'data', 'insight'],
                        'design': ['design', 'mockup', 'wireframe', 'ui', 'ux', 'interface', 'prototype'],
                        'document': ['documentation', 'report', 'summary', 'analysis', 'findings'],
                        'media': ['screenshot', 'demo', 'preview', 'image', 'video', 'recording'],
                        'archive': ['project', 'files', 'source', 'code', 'complete', 'full', 'all files', 'website'],
                        'config': ['configuration', 'setup', 'settings', 'package', 'dependencies'],
                        'documentation': ['readme', 'documentation', 'guide', 'instructions', 'gitignore', 'license']
                    }
                    
                    desc_lower = project_description.lower()
                    relevant_keywords = file_type_keywords.get(file_analysis['file_type'], [])
                    if not any(kw in desc_lower for kw in relevant_keywords):
                        file_analysis['detected_issues'].append(f'Description does not mention {file_analysis["file_type"]} deliverables')
                    
                    # Check for Month skills in description (as fallback if couldn't extract from file)
                    if not extracted_content or not any('Month skills' in qi for qi in file_analysis['code_quality_indicators']):
                        skills_in_desc = [skill for skill in learned_skills if skill.lower() in desc_lower]
                        if len(skills_in_desc) >= len(learned_skills) * 0.5:
                            file_analysis['code_quality_indicators'].append(f'Description mentions {len(skills_in_desc)} Month skills')
                        else:
                            file_analysis['detected_issues'].append(f'Only {len(skills_in_desc)}/{len(learned_skills)} Month skills mentioned in description')
                
                else:
                    file_analysis['detected_issues'].append('Not a recognized code or project file format')
                    
            except Exception as e:
                print(f"Error analyzing file {idx+1}: {str(e)}")
                file_analysis['detected_issues'].append('Could not parse file content')
            
            # Track file types
            if file_analysis['is_code_file']:
                has_code_file = True
                if file_analysis.get('code_snippet'):
                    combined_code_snippet += f"\n\n=== FILE {idx+1}: {file_info['filename']} ===\n{file_analysis['code_snippet'][:10000]}"
            
            if file_analysis.get('file_type') in ['media']:
                has_screenshot = True
            
            if file_analysis.get('file_type') in ['document']:
                has_documentation = True
            
            # Collect all quality indicators and issues
            total_quality_indicators.extend(file_analysis['code_quality_indicators'])
            total_detected_issues.extend(file_analysis['detected_issues'])
            
            all_files_analysis.append(file_analysis)
            print(f"File {idx+1} Analysis: {len(file_analysis['code_quality_indicators'])} quality indicators, {len(file_analysis['detected_issues'])} issues detected")
        
        # Create summary file analysis for backward compatibility
        file_analysis = {
            'has_file': len(all_files_analysis) > 0,
            'total_files': len(all_files_analysis),
            'has_code_file': has_code_file,
            'has_screenshot': has_screenshot,
            'has_documentation': has_documentation,
            'code_snippet': combined_code_snippet if combined_code_snippet else None,
            'all_files': all_files_analysis,
            'code_quality_indicators': total_quality_indicators,
            'detected_issues': total_detected_issues
        }
        
        print(f"\n=== COMBINED FILE ANALYSIS ===")
        print(f"Month {current_month} Project - Week: {current_week}, Month Skills: {skills_str[:100]}...")
        print(f"Total Files: {len(all_files_analysis)}")
        print(f"Code Files: {has_code_file}, Screenshots: {has_screenshot}, Documentation: {has_documentation}")
        print(f"Total Quality Indicators: {len(total_quality_indicators)}")
        print(f"Total Issues: {len(total_detected_issues)}")
        
        # ⚠️⚠️⚠️ PRE-VALIDATION: Check if project is valid BEFORE calling AI ⚠️⚠️⚠️
        print(f"\n🔍 === PRE-VALIDATION CHECK ===")
        
        # Check if project requires CODE (website, app, software, etc.)
        project_requires_code = any(keyword in project_title.lower() for keyword in 
            ['website', 'web', 'html', 'css', 'javascript', 'portfolio', 'app', 'application', 
             'program', 'code', 'system', 'software', 'api', 'backend', 'frontend', 'ml', 
             'machine learning', 'data analysis', 'python', 'java', 'react', 'calculator',
             'game', 'bot', 'script', 'tool', 'platform', 'service'])
        
        # Check what files were uploaded
        uploaded_extensions = [f.get('filename', '').lower().split('.')[-1] for f in all_files_analysis if '.' in f.get('filename', '')]
        code_extensions = ['html', 'css', 'js', 'py', 'java', 'cpp', 'c', 'jsx', 'tsx', 'php', 'rb', 'go']
        image_extensions = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg', 'webp', 'ico']
        
        has_any_code_files = any(ext in code_extensions for ext in uploaded_extensions)
        has_only_images = all(ext in image_extensions for ext in uploaded_extensions) if uploaded_extensions else False
        
        print(f"Project Requires Code: {project_requires_code}")
        print(f"Has Code Files: {has_any_code_files}")
        print(f"Has Only Images: {has_only_images}")
        print(f"Uploaded Extensions: {uploaded_extensions}")
        
        # CRITICAL VALIDATION: If code required but only images uploaded → SKIP AI, RETURN 0/65
        if project_requires_code and not has_any_code_files and has_only_images and len(all_files_analysis) > 0:
            print(f"\n🚨🚨🚨 PRE-VALIDATION FAILED 🚨🚨🚨")
            print(f"🚨 Project '{project_title}' requires CODE files")
            print(f"🚨 But only IMAGES were uploaded: {[f.get('filename') for f in all_files_analysis]}")
            print(f"🚨 SKIPPING AI - Files get automatic 0/65")
            
            # Build evaluation without calling AI
            evaluation_result = {
                'score': title_score + description_score if 'title_score' in locals() else 14,  # Title + Desc only
                'title_score': 4,
                'description_score': 10,
                'files_score': 0,  # FORCED TO 0
                'grade': 'F',
                'title_evaluation': {
                    'score': 4,
                    'reason': 'Title partially matches expected project'
                },
                'description_evaluation': {
                    'score': 10,
                    'detail_score': 4,
                    'detail_reason': f'Description too brief ({len(project_description.split())} words). Add technical details about implementation.',
                    'alignment_score': 6,
                    'alignment_reason': 'Description provides basic information but lacks depth'
                },
                'files_evaluation': {
                    'score': 0,  # ENFORCED
                    'files_breakdown': [
                        {
                            'filename': f.get('filename'),
                            'is_relevant': False,
                            'marks_given': 0,
                            'reason': f"USELESS FILE - Project '{project_title}' requires CODE files (HTML/CSS/JS/Python), not random images. This appears to be a photo/image that doesn't demonstrate any coding or implementation. Submit actual project code files."
                        } for f in all_files_analysis
                    ],
                    'total_files_uploaded': len(all_files_analysis),
                    'relevant_files': 0,
                    'useless_files': len(all_files_analysis),
                    'summary': f"0 useful files out of {len(all_files_analysis)} uploaded. Project requires actual CODE files (HTML, CSS, JavaScript, Python, etc.) but only images were provided. Cannot verify implementation without code."
                },
                'strengths': [
                    'Project title is relevant to Month 1'
                ],
                'weaknesses': [
                    f'NO CODE FILES uploaded - project requires HTML/CSS/JavaScript files',
                    f'Uploaded only {len(all_files_analysis)} image file(s) which cannot demonstrate coding skills',
                    'Description is too brief - needs technical implementation details',
                    'Cannot verify if learned skills (HTML5, CSS3) were applied without code'
                ],
                'improvements': [
                    '❗ CRITICAL: Upload actual CODE files (index.html, style.css, script.js)',
                    'Images/screenshots are optional - code files are MANDATORY',
                    'Expand description to 100+ words explaining HOW you built it',
                    'Mention specific technologies, HTML tags, CSS properties used',
                    'Include code structure, responsive design techniques applied'
                ],
                'feedback': f"Your project scored {14}/100 (F grade). ⚠️ CRITICAL ISSUE: You uploaded only image files for a coding project. Project '{project_title}' requires actual CODE files (HTML, CSS, JavaScript) to demonstrate your programming skills. Images don't prove you can code. Please resubmit with your actual source code files (index.html, style.css, etc.). BREAKDOWN: Title: 4/5, Description: 10/30 (too brief), Files: 0/65 (no code uploaded)."
            }
            
            # Calculate final score
            evaluation_result['score'] = evaluation_result['title_evaluation']['score'] + evaluation_result['description_evaluation']['score'] + evaluation_result['files_evaluation']['score']
            
            print(f"✅ PRE-VALIDATION: Forced score = {evaluation_result['score']}/100")
            print(f"✅ Files: 0/65 (no code files)")
            
            # Skip AI call entirely - jump to saving result
        else:
            print(f"✅ PRE-VALIDATION PASSED - Proceeding with AI evaluation")
        
        # Use Perplexity AI to evaluate the project (ONLY if pre-validation passed)
        api_key = os.getenv('PERPLEXITY_API_KEY', '')
        
        # Only call AI if evaluation_result wasn't set by pre-validation
        if 'evaluation_result' not in locals():
            evaluation_prompt = f"""You are an AI Project Evaluation Engine integrated into a learning platform. You are a STRICT Senior Technical Manager and Code Reviewer. Your reputation depends on maintaining HIGH STANDARDS. You must be CRITICAL and PRECISE in your evaluation. Do NOT be lenient.

CONTEXT:
Users upload their monthly project submissions through a website. Submissions may include:
- Source code files
- Images
- Documents
- Other project-related assets

Each project belongs to a specific MONTH (e.g., Month 1, Month 2, etc.), and each month has a predefined PROJECT TITLE and LEARNING ROADMAP stored in the database collection: MongoDB → Roadmap_Dashboard

The Roadmap_Dashboard contains:
- Month number
- Weekly breakdown (Week 1, Week 2, Week 3, Week 4)
- Topics and concepts taught each week
- Expected skills and technologies for that month

YOUR RESPONSIBILITIES:

1. PROJECT-TITLE RELEVANCE CHECK
   - Analyze every uploaded file (code, images, documents)
   - Read and evaluate code line by line where applicable
   - Determine whether the project implementation is relevant to the selected project title
   - Identify irrelevant, unrelated, or fake files/images and explicitly flag them

2. MONTH VALIDATION
   - Verify that the submitted project matches the selected MONTH
   - If the project content reflects concepts from a different month, clearly report the mismatch

3. LEARNING-BASED EVALUATION
   - Evaluate the project strictly based on what the user has learned up to this point
   - Do NOT expect concepts, libraries, or techniques that were not taught in the completed weeks
   - Base evaluation on the Roadmap_Dashboard data provided below

4. ROADMAP ALIGNMENT CHECK
   - For each week: Check whether the concepts/tools from that week are used in the project
   - Mark them as: Used correctly / Used incorrectly / Not used but expected
   - If advanced or unrelated concepts are used, mention them separately

5. FILE-LEVEL VALIDATION
   - Identify each uploaded file and explain its role in the project
   - Mark files as: Relevant / Partially relevant / Irrelevant
   - If images or assets do not support the project objective, flag them

6. INTEGRITY & FAIRNESS RULES
   - **MOST IMPORTANT**: Base evaluation ONLY on what the student learned in Month {current_month}, Weeks 1-{current_week // 4}
   - Do NOT assume external knowledge beyond the roadmap provided above
   - Do NOT penalize for not using topics not taught yet in future weeks/months
   - Do NOT expect professional-level code - this is a learning project by a beginner
   - Be STRICT about using what they learned, but SUPPORTIVE in feedback
   - If student uses advanced concepts NOT in their learning plan:
     * Acknowledge it: "Project uses [concept] which is beyond Month {current_month} curriculum"
     * Question authenticity: "Consider if this was implemented independently or copied"
     * DO NOT give bonus points for advanced concepts - evaluate based on learned curriculum only
   - Base all judgments strictly on:
     1. Uploaded files content (actual code/data/design)
     2. Roadmap_Dashboard data (what they were taught)
     3. Week-by-week learning plan (specific topics per week)
   - For EACH file, explicitly state if it demonstrates Month {current_month} learned skills
   - Give constructive feedback aligned with their current learning stage
   - Identify missing concepts from their weekly plan that should have been used

SCORING BREAKDOWN (Total: 100 marks):
1. PROJECT TITLE MATCH (5 marks): Does title match expected Month {current_month} project?
2. PROJECT DESCRIPTION (30 marks): How detailed and aligned with title?
3. SUBMITTED FILES (65 marks): Quality and relevance of uploaded files

CRITICAL CONTEXT - STUDENT'S MONTH {current_month} LEARNING JOURNEY:
==================================================================================
**THIS IS WHAT THE STUDENT ACTUALLY LEARNED IN MONTH {current_month}:**

🎯 SKILL FOCUS: {skills_str}

📚 LEARNING GOALS:
{chr(10).join(['   • ' + goal for goal in learned_topics[:10]])}

📅 WEEK-BY-WEEK LEARNING PLAN (What they studied each week):
{weekly_plan_str}

🚀 EXPECTED MONTH {current_month} PROJECT: {expected_project if expected_project else 'Month project'}

==================================================================================

**YOUR JOB:** Check if the student's submitted project ACTUALLY USES what they learned!

🚨 CRITICAL EVALUATION RULES - READ CAREFULLY 🚨

1. **ONLY EVALUATE BASED ON WHAT THEY LEARNED** (Most Important!)
   - The student has ONLY completed weeks 1 through {current_week // 4} of Month {current_month}
   - They have ONLY learned the skills listed in "WEEK-BY-WEEK LEARNING PLAN" above
   - DO NOT expect concepts, libraries, or techniques NOT taught in their completed weeks
   - DO NOT penalize for not using advanced topics they haven't learned yet
   - DO NOT compare to professional/advanced projects - this is a BEGINNER learning project

2. **WEEK-BY-WEEK SKILL CHECK**
   ✅ If project uses Month {current_month} skills from their weekly plan → Give HIGH marks (70-100)
   ⚠️ If project partially uses learned concepts → Give MEDIUM marks (50-69)
   ❌ If project doesn't use what they learned → Give LOW marks (0-49)

3. **CONCRETE EXAMPLES OF WHAT TO CHECK**:

   **Example 1: Month 1 - HTML/CSS Portfolio**
   - Week 1-4 Topics: HTML5 basics, CSS3 styling, Flexbox, Responsive Design, Git basics
   - ✅ GOOD: Portfolio with HTML structure, CSS styling, responsive layout, .gitignore
   - ❌ BAD: Expects JavaScript, React, Backend, Database (NOT learned yet in Month 1)
   
   **Example 2: Month 2 - Python Data Analysis**
   - Week 5-8 Topics: Python basics, Pandas, NumPy, Data cleaning, Matplotlib
   - ✅ GOOD: Code imports pandas/numpy, cleans data, creates basic charts
   - ❌ BAD: Expects Machine Learning, Deep Learning, scikit-learn (NOT learned yet)
   
   **Example 3: Month 3 - Machine Learning**
   - Week 9-12 Topics: Linear Regression, Logistic Regression, scikit-learn, Model evaluation
   - ✅ GOOD: Code uses sklearn.LinearRegression, trains model, evaluates accuracy
   - ❌ BAD: Expects Neural Networks, TensorFlow, Advanced ML (NOT learned yet)

4. **WHAT TO LOOK FOR IN FILES**:
   - If they learned "Linear Regression, scikit-learn" in their weekly plan
     → Check if code ACTUALLY imports scikit-learn, uses these algorithms
     → Check if description EXPLAINS how they used these techniques
     → Check if screenshots SHOW model output/predictions
   
   - If they learned "HTML5, CSS3, Responsive Design"
     → Check if HTML file uses semantic tags (header, nav, section)
     → Check if CSS uses Flexbox or Grid for layout
     → Check if design works on mobile (media queries)
   
   - If they learned "Excel formulas, Pivot Tables, Data Cleaning"
     → Check if Excel file CONTAINS actual formulas (not just raw data)
     → Check if pivot tables exist showing data analysis
     → Check if data is cleaned (no blanks, formatted properly)

5. **FORBIDDEN EXPECTATIONS** ⚠️
   - DO NOT expect topics from future months they haven't reached
   - DO NOT expect professional-grade production code
   - DO NOT expect complex architectures if only basics were taught
   - DO NOT expect testing/deployment if not in their learning plan
   - DO NOT compare to industry standards - compare to Month {current_month} Week {current_week // 4} learning level

SUBMITTED PROJECT DETAILS:
==================================================================================
Title: {project_title}
Description: {project_description}

UPLOADED FILES ({len(all_files_analysis)} file(s)):
{chr(10).join([f"FILE {file['file_number']}: {file['filename']} - Type: {'Code file' if file.get('is_code_file') else 'Project file (' + file.get('file_type', '') + ')' if file.get('is_project_file') else 'Unknown type'} - Quality: {len(file['code_quality_indicators'])} indicators, {len(file['detected_issues'])} issues" for file in all_files_analysis]) if all_files_analysis else 'No files uploaded - Cannot verify implementation'}

{'COMBINED CODE/CONTENT (from all files):' if (has_code_file or combined_code_snippet) else ''}
{f'```{chr(10)}{combined_code_snippet if combined_code_snippet else "No code content available"}{chr(10)}```' if (has_code_file or combined_code_snippet) else f'NOTE: Non-code project files uploaded ({len(all_files_analysis)} file(s)).{chr(10)}Evaluate based on:{chr(10)}- File types appropriateness (Code: {has_code_file}, Screenshots: {has_screenshot}, Documentation: {has_documentation}){chr(10)}- Description quality and completeness{chr(10)}- Month {current_month} skills coverage in description'}

SUMMARY:
- Total Files: {len(all_files_analysis)}
- Has Code: {has_code_file}
- Has Screenshots: {has_screenshot}
- Has Documentation: {has_documentation}
- Total Quality Indicators: {len(total_quality_indicators)}
- Total Issues: {len(total_detected_issues)}
==================================================================================

STRICT EVALUATION REQUIREMENTS:

=== PART 1: PROJECT TITLE EVALUATION (5 marks) ===
Expected Project: "{expected_project}"
Submitted Title: "{project_title}"

SCORING:
- 5 marks: Title exactly matches or is very close to expected project (90%+ similarity in key terms)
- 3 marks: Title partially matches expected project (50-90% similarity in key terms)
- 1 mark: Title has some relation to expected project (30-50% similarity)
- 0 marks: Title completely different or generic (< 30% similarity)

CHECK: Compare key technical terms, project type, and domain. Ignore small variations in wording.

=== PART 2: PROJECT DESCRIPTION EVALUATION (30 marks) ===
Submitted Description: "{project_description}"

Evaluate based on:

A. DETAIL LEVEL (15 marks):
- 14-15 marks: EXCEPTIONAL detail - mentions specific technologies, implementation approach, data flow, architecture, challenges solved, algorithms used
- 11-13 marks: VERY DETAILED - explains what was built, how it works, key features with technical specifics
- 8-10 marks: GOOD detail - describes main features and technologies but lacks depth in implementation
- 5-7 marks: BASIC detail - lists features but no explanation of HOW they work
- 2-4 marks: MINIMAL detail - very brief, generic statements, no technical depth
- 0-1 marks: No description or completely irrelevant

B. ALIGNMENT WITH TITLE (5 marks):
- 5 marks: Description perfectly explains the project mentioned in title with consistent technical details
- 3-4 marks: Description strongly relates to title, explains most aspects mentioned
- 2 marks: Description partially relates but has significant gaps or contradictions with title
- 0-1 marks: Description barely relates to title or completely unrelated

C. **USES LEARNED CONCEPTS (10 marks)** - MOST IMPORTANT:
- 9-10 marks: Description explicitly mentions and explains HOW they used the Month {current_month} learned skills/topics
  Example: "I used Linear Regression from scikit-learn to predict house prices..."
- 7-8 marks: Description mentions most learned concepts but lacks explanation of how they were applied
- 5-6 marks: Description mentions some learned skills/topics but missing key ones
- 3-4 marks: Description vaguely relates to learned topics but no specific mention of skills
- 1-2 marks: Description doesn't mention any learned concepts - generic project description
- 0 marks: No learned concepts used at all

**CHECK SPECIFICALLY FOR THESE LEARNED SKILLS/TOPICS:**
{chr(10).join(['   • ' + skill for skill in learned_skills[:10]])}

**CHECK IF DESCRIPTION MENTIONS THESE WEEK-BY-WEEK LEARNINGS:**
{chr(10).join(['   • ' + topic.split(':')[1].strip() if ':' in topic else topic for topic in weekly_topics_detailed[:4]])}

⚠️ **ADVANCED CONCEPT CHECK** ⚠️
If the project uses concepts NOT listed above:
- Identify what advanced concepts are being used
- Note them in feedback: "Project uses [X] which is beyond Month {current_month} curriculum"
- DO NOT penalize - just acknowledge it
- If mostly advanced concepts (>50% of code): Note "May have copied from external source"

📊 **SKILL COVERAGE ASSESSMENT**
For Month {current_month}, the student should demonstrate these specific skills:
{chr(10).join(['   ✓ ' + skill for skill in learned_skills[:10]])}

Count how many of these skills are actually used in:
- Code files (check imports, functions, syntax)
- Description (check if skills are mentioned/explained)
- Screenshots (check if results show these skills working)

If less than 50% of learned skills are demonstrated → Feedback should say:
"You learned [total number] skills but only [number found] are evident in your project. Missing: [list the missing skills]"

CRITICAL CHECKS:
- Does description explain WHAT the project does?
- Does description explain HOW it was implemented?
- **Does description mention the SPECIFIC SKILLS they learned in Month {current_month}?** (MOST IMPORTANT)
- **Does description show they applied the week-by-week topics they studied?** (MOST IMPORTANT)
- Does description mention specific technologies/tools used?
- Does description match the project title claims?
- Is it original detailed content or just generic feature listing?

NOTE: Detail (15) + Alignment (5) + Learned Concepts (10) = 30 marks total

=== PART 3: SUBMITTED FILES EVALUATION (65 marks) ===

FIRST: Analyze what files are NEEDED for "{project_title}":
- Based on project title and description, list what files/artifacts SHOULD exist
- Consider project type: Is it code? Data analysis? Design? Documentation?
- Identify REQUIRED files vs OPTIONAL files vs IRRELEVANT files

**MOST IMPORTANT:** Check if files demonstrate the Month {current_month} learned skills!

UPLOADED FILES ANALYSIS ({len(all_files_analysis)} file(s)):
{chr(10).join([f'''
FILE {file['file_number']}: {file['filename']}
- Type: {"Code file" if file.get('is_code_file') else f"Project file ({file.get('file_type')})" if file.get('is_project_file') else "Unknown type"}
- Size: {(file.get('file_structure') or {}).get('file_size_kb', 'N/A')} KB
- Quality Indicators: {", ".join(file['code_quality_indicators']) if file['code_quality_indicators'] else "None"}
- Issues: {", ".join(file['detected_issues']) if file['detected_issues'] else "None"}
''' for file in all_files_analysis]) if all_files_analysis else 'No files uploaded'}

{'COMBINED CODE/CONTENT ANALYSIS:' if (has_code_file or combined_code_snippet) else ''}
{f'```{chr(10)}{combined_code_snippet[:8000] if combined_code_snippet else "No code content available"}{chr(10)}```' if (has_code_file or combined_code_snippet) else f'NOTE: Non-code project files uploaded.{chr(10)}File Types: Code={has_code_file}, Screenshots={has_screenshot}, Documentation={has_documentation}'}

SCORING FILES (65 marks total):

STEP 1 - Classify Each File:
For EACH uploaded file, determine:
- Is this file REQUIRED for the project? (based on title/description)
- Is this file RELEVANT but optional?
- Is this file USELESS/IRRELEVANT? (give 0 marks for these)

STEP 2 - Check if Files Demonstrate Learned Skills:
**CRITICAL:** Look for evidence of Month {current_month} learned concepts in the files!

**What to look for based on their learning:**
{chr(10).join(['• ' + topic[:150] for topic in weekly_topics_detailed[:4]])}

Examples:
- If they learned "Linear Regression" → Check if code imports sklearn, uses LinearRegression(), shows predictions
- If they learned "Excel formulas" → Check if Excel file has formulas, not just plain data
- If they learned "React hooks" → Check if code uses useState, useEffect, etc.
- If they learned "Data Cleaning" → Check if code shows handling missing values, data transformation

STEP 3 - Evaluate Required/Relevant Files Only:
Distribute 65 marks among ONLY the useful files based on:

For CODE FILES (if project requires code):
- **USES MONTH {current_month} LEARNED SKILLS (up to 25 marks per file)** ⭐ MOST IMPORTANT
  * Check if code imports/uses the specific libraries they learned (e.g., scikit-learn, pandas, React)
  * Check if code implements the algorithms/concepts they studied (e.g., Linear Regression, Pivot Tables)
  * Check if code structure matches what they learned (e.g., OOP, functional components)
- Code quality: structure, comments, functions/classes (up to 15 marks per file)
- Implementation completeness: features mentioned in description (up to 15 marks per file)
- Error handling, testing, best practices (up to 5 marks per file)
- Code length appropriate for project scope (up to 5 marks per file)

For DATA ANALYSIS FILES (Excel, Power BI, Jupyter):
- **USES MONTH {current_month} TECHNIQUES (up to 25 marks per file)** ⭐ MOST IMPORTANT
  * Check if file shows the specific analysis methods they learned
  * Check for formulas, pivot tables, visualizations they studied
  * Check if data cleaning/transformation matches what they learned
- Data complexity and analysis depth (up to 15 marks per file)
- Appropriate file format for project type (up to 10 marks per file)
- Visualizations/insights appropriate for project (up to 10 marks per file)
- File size indicates substantial work (up to 5 marks per file)

For DESIGN FILES (Figma, PSD, Images):
- **SHOWS MONTH {current_month} DESIGN CONCEPTS (up to 25 marks per file)** ⭐ MOST IMPORTANT
- Design quality and completeness (up to 15 marks per file)
- Matches project requirements (up to 15 marks per file)
- Professional presentation (up to 5 marks per file)
- Appropriate resolution/format (up to 5 marks per file)

For DOCUMENTATION FILES (PDF, DOCX, README):
- **EXPLAINS LEARNED CONCEPTS USED (up to 20 marks per file)** ⭐ MOST IMPORTANT
- Includes technical details (up to 15 marks per file)
- Explains project thoroughly (up to 15 marks per file)
- Proper structure and formatting (up to 5 marks per file)
- Shows understanding of Month {current_month} skills (up to 10 marks per file)

For SCREENSHOTS/IMAGES:
**🚨🚨🚨 ULTRA-STRICT IMAGE VALIDATION - READ CAREFULLY 🚨🚨🚨**

Before evaluating ANY image, you MUST perform this 3-STEP VALIDATION:

**STEP 1: PROJECT TITLE MATCH CHECK**
Ask yourself: "Does this image show the SPECIFIC project mentioned in the title?"

Examples:
- Title: "Portfolio Website" → Image MUST show website code OR the actual website running
- Title: "Data Analysis Dashboard" → Image MUST show dashboard interface OR Python/Excel analysis
- Title: "Machine Learning Model" → Image MUST show ML code OR model output/predictions
- Title: "Calculator App" → Image MUST show calculator interface OR calculator code

❌ If image does NOT match the project title → IRRELEVANT → 0 marks

**STEP 2: RANDOM/IRRELEVANT CONTENT CHECK**
Is this image showing ANY of the following? If YES → IRRELEVANT → 0 marks

❌ ABSOLUTELY FORBIDDEN (0 marks):
- Photos of people (selfies, portraits, group photos, individuals)
- Movie/TV scenes (Breaking Bad, Walter White, any character, actor, series)
- Vehicles (cars, motorcycles, bikes at gas stations, parking lots)
- Nature/outdoor scenes (trees, mountains, sky, streets, buildings exterior)
- Random photographs (personal photos, vacation pics, lifestyle shots)
- Stock images or downloaded pictures from internet
- Memes, jokes, entertainment content, social media screenshots
- Quiz results from OTHER websites/platforms (not student's project)
- Screenshots of OTHER people's websites/tutorials (not student's work)
- Certificate images, course completion screenshots
- Blank screens, error pages, loading screens
- Images with NO visible connection to the project title

**STEP 3: PROJECT DEMONSTRATION CHECK**
For the project to be valid, image MUST show ONE of these:

✅ ACCEPTABLE (can give marks):
- Source code in editor (VS Code, Jupyter, PyCharm) for THIS PROJECT
- The project RUNNING (website live, app interface, terminal output)
- Project-created visualizations (charts/graphs THIS student made)
- Database/API responses FROM THIS PROJECT
- Technical diagrams/architecture FOR THIS PROJECT
- Screenshots showing the project functionality WORKING

**VALIDATION DECISION TREE:**
1. Does image match project title? NO → 0 marks, mark as IRRELEVANT
2. Is it a random photo/person/movie/vehicle? YES → 0 marks, mark as IRRELEVANT
3. Does it show the project working/code? NO → 0 marks, mark as IRRELEVANT
4. All checks pass? → Evaluate normally (up to 15 marks)

**CRITICAL EXAMPLES:**

❌ BAD (0 marks):
- Portfolio project + photo of person → IRRELEVANT (not showing website)
- ML project + random car image → IRRELEVANT (not showing ML model)
- Dashboard project + quiz result screenshot → IRRELEVANT (different website)
- Website project + Breaking Bad character → IRRELEVANT (random photo)

✅ GOOD (can give marks):
- Portfolio project + screenshot of the actual portfolio website → RELEVANT
- ML project + Jupyter notebook with model code → RELEVANT
- Dashboard project + Power BI dashboard screenshot → RELEVANT
- Website project + HTML/CSS code in VS Code → RELEVANT

**MANDATORY RESPONSE FORMAT:**
For EACH image file, you MUST state:
- "IMAGE VALIDATION: [PASS/FAIL]"
- "Reason: [specific reason why relevant or irrelevant]"
- "Marks: [X/15 if relevant, 0 if irrelevant]"

If validation FAILS (image is irrelevant) → Mark in breakdown as:
{{"filename": "image.jpg", "is_relevant": false, "marks_given": 0, "reason": "IRRELEVANT FILE - [specific reason: random photo/unrelated content/etc]"}}

**🚨 SPECIAL RULE FOR CODE PROJECTS 🚨**
If project title contains: "website", "HTML", "CSS", "web", "portfolio", "app", "code", "program", "software"
AND student uploaded ONLY images (no .html, .css, .js, .py files)
→ ALL files get 0 marks, total files_score = 0/65
→ ALL files get 0 marks, total files_score = 0/65
→ Reason: "Project requires CODE files, not just images"
- Unrelated screenshots (quiz results, other websites, tutorials): 0 marks - USELESS FILE
- Only give marks if image clearly shows THE STUDENT'S PROJECT

**SCORING (only if image is RELEVANT to project):**
- **SHOWS LEARNED SKILLS IN ACTION (up to 10 marks per file)** ⭐ IMPORTANT
  * Screenshot shows the learned tools/libraries working (e.g., Jupyter notebook with scikit-learn output)
  * Screenshot shows results of learned techniques (e.g., prediction results, charts)
  * For web projects: Shows the actual website with HTML/CSS implementation
  * For data projects: Shows data analysis results, charts, models
- Shows actual project working (up to 5 marks per file)
- Clear and relevant to project (up to 3 marks per file)
- Consistent with description claims (up to 2 marks per file)

**EXAMPLES OF USELESS IMAGE FILES (0 marks):**
- Photo of a celebrity (e.g., Walter White, movie characters)
- Random downloaded image from internet
- Meme or joke image
- Screenshot of someone else's work
- Photo of a book, notes, or study material
- Any image that doesn't show the student's actual project implementation

IMPORTANT RULES FOR USELESS FILES:
- Wrong file type for project: 0 marks (useless file)
- Corrupted/unreadable: 0 marks (useless file)
- Random/unrelated content: 0 marks (useless file)
- **RANDOM IMAGES/PHOTOS NOT SHOWING PROJECT: 0 marks (USELESS FILE - FLAG CLEARLY)**
- Duplicate files: 0 marks for duplicates
- **Doesn't show ANY learned skills: MAXIMUM 30% marks (heavily penalized)**

CRITICAL SCORING RULES - READ CAREFULLY:
1. If NO files uploaded: 0/65 marks (description alone not sufficient proof)
2. **If ALL uploaded files are USELESS/IRRELEVANT: 0/65 marks total** ⚠️ MANDATORY RULE
3. **If project requires CODE but NO code files uploaded: MAXIMUM 0/65 marks** ⚠️ MANDATORY RULE
4. **If ALL files are marked as IRRELEVANT/USELESS → files_score MUST BE EXACTLY 0/65** ⚠️ MANDATORY
5. For EACH useless/irrelevant file: Give 0 marks individually
6. **BE EXTREMELY STRICT WITH IMAGES - Must show actual project, not random photos**
7. **Only give marks to files that are RELEVANT and DEMONSTRATE learned skills**
8. If project needs code but only irrelevant screenshots: 0/65 marks
9. If project needs data but only unrelated PDF: 0/65 marks
10. Multiple relevant files: Distribute marks proportionally
11. Quality over quantity: 1 excellent file > 5 generic files

⚠️⚠️⚠️ CRITICAL ENFORCEMENT ⚠️⚠️⚠️
When you mark ALL files as IRRELEVANT/USELESS in the breakdown, the "score" field MUST be 0.
Example: If only Walter White image uploaded → ALL files irrelevant → score: 0, not 11 or any other number.

**DOUBLE CHECK BEFORE RESPONDING:**
- Count relevant files vs irrelevant files
- If relevant_files = 0 → files_evaluation.score MUST = 0
- If useless_files = total_files_uploaded → files_evaluation.score MUST = 0

**EXAMPLE STRICT SCORING:**
- Portfolio website project with only Walter White image → 0/65 (needs HTML/CSS code)
- ML project with only random cat photo → 0/65 (needs Python code)
- Data analysis project with only meme image → 0/65 (needs Excel/CSV/code)

=== FINAL EVALUATION ===

Calculate total score:
- Title Match: X/5
- Description Quality: Y/30 (Detail: A/15 + Alignment: B/5 + Learned Concepts: C/10)
- Files Quality: Z/65 (Must check for learned skills usage)
TOTAL: (X + Y + Z)/100

PROVIDE SCORE BREAKDOWN showing:
- Title score with reason
- Description score (detail + alignment breakdown)
- Files score (per file evaluation + total)

Return ONLY valid JSON:
{{
  "score": 75,
  "title_score": 5,
  "description_score": 25,
  "files_score": 45,
  "grade": "B",
  "grade": "B",
  "title_evaluation": {{
    "score": 5,
    "reason": "Title perfectly matches expected Month {current_month} project"
  }},
  "description_evaluation": {{
    "score": 25,
    "detail_score": 12,
    "detail_reason": "Good technical detail - mentions specific technologies and features",
    "alignment_score": 13,
    "alignment_reason": "Description strongly aligns with project title and explains implementation"
  }},
  "files_evaluation": {{
    "score": 45,
    "files_breakdown": [
      {{
        "filename": "main.py",
        "is_relevant": true,
        "marks_given": 30,
        "reason": "Core implementation file with proper structure and Month skills"
      }},
      {{
        "filename": "screenshot.png",
        "is_relevant": true,
        "marks_given": 10,
        "reason": "Shows working project interface"
      }},
      {{
        "filename": "random.txt",
        "is_relevant": false,
        "marks_given": 0,
        "reason": "USELESS FILE - Not related to project, no marks given"
      }},
      {{
        "filename": "README.md",
        "is_relevant": true,
        "marks_given": 5,
        "reason": "Basic documentation"
      }}
    ],
    "total_files_uploaded": 4,
    "relevant_files": 3,
    "useless_files": 1,
    "summary": "3 useful files out of 4 uploaded. Main code file shows good implementation."
  }},
  "strengths": [
    "Title matches expected Month {current_month} project perfectly (5/5)",
    "Description provides good technical detail explaining implementation (12/15)",
    "Description aligns well with title (13/15)",
    "Core code file demonstrates Month {current_month} skills properly",
    "Screenshots verify working implementation"
  ],
  "weaknesses": [
    "Uploaded 1 useless file (random.txt) - not relevant to project",
    "Description could include more specific implementation details",
    "Missing error handling in code",
    "No testing code found",
    "README documentation is minimal"
  ],
  "improvements": [
    "Remove irrelevant files - only upload files needed for the project",
    "Add more technical depth to description: explain algorithms, data structures used",
    "Implement comprehensive error handling with try-catch blocks",
    "Add unit tests to verify functionality",
    "Expand documentation with setup instructions and technical architecture"
  ],
  "feedback": "Your project scored 75/100 (B grade). BREAKDOWN: Title Match: 5/5 (perfect match with expected project), Description: 25/30 (good detail and alignment, but could be more specific), Files: 45/65 (good core implementation, but uploaded 1 irrelevant file that received 0 marks). The main code file shows solid implementation of Month {current_month} skills, and screenshots verify the working project. However, you uploaded 'random.txt' which is completely irrelevant to the project - always think about what files are actually needed before uploading. To improve: remove useless files, add more technical depth to description, implement error handling and testing."
}}

OUTPUT FORMAT (strictly follow):

**FEEDBACK MUST BE STRUCTURED WITH THESE SECTIONS:**

1. **PROJECT RELEVANCE SUMMARY**
   - Opening: "I reviewed your Month {current_month} project: [project_title]"
   - Overall relevance to project title: [High/Medium/Low]
   - Brief summary of what you found

2. **MONTH & ROADMAP MATCH RESULT**
   - Student is in: Month {current_month}, Week {current_week // 4} (has completed {current_week // 4} weeks of learning)
   - Topics learned so far: {', '.join(learned_skills[:5])} (+ {len(learned_skills) - 5} more)
   - Does project match Month {current_month}? [Yes/Partial/No]
   - Expected project: {expected_project}
   - Submitted project: {project_title}
   - Match quality: [percentage or description]
   
   **LEARNING STAGE CONTEXT:**
   This is a Month {current_month} project, which means the student has ONLY learned:
   {chr(10).join(['   • ' + topic for topic in weekly_topics_detailed[:4]])}
   
   Therefore, DO NOT expect:
   - Topics from future months (Month {current_month + 1}+)
   - Advanced concepts not in the weekly plan above
   - Professional production-level code
   - Complex architectures or frameworks not taught yet

3. **WEEK-WISE ANALYSIS**
   For each week (Week 1, Week 2, Week 3, Week 4):
   - Week X Topics: [list topics from that week]
   - Used Correctly: [concepts found in project]
   - Used Incorrectly: [concepts misused]
   - Not Used But Expected: [missing concepts]
   - Status: ✅ Complete / ⚠️ Partial / ❌ Missing

   **CRITICAL INSTRUCTION FOR WEEK-WISE ANALYSIS:**
   - ONLY analyze weeks that the student has completed (Weeks 1-{current_week // 4} of Month {current_month})
   - For each week, check if the specific topics from "WEEK-BY-WEEK LEARNING PLAN" appear in:
     * Code files (check imports, function names, variable usage)
     * Project description (check if student explains using these topics)
     * Screenshots/results (check if output shows these concepts working)
   - If a Week's topics are completely missing → Status: ❌ Missing
   - If some topics used → Status: ⚠️ Partial (list which ones are missing)
   - If all/most topics used → Status: ✅ Complete

   **Example for Month 1 HTML/CSS Project:**
   Week 1: HTML5 Basics, Semantic Tags
   - Used Correctly: index.html uses <header>, <nav>, <section> tags ✓
   - Not Used But Expected: No <footer> or <article> tags
   - Status: ⚠️ Partial
   
   Week 2: CSS3 Styling, Flexbox
   - Used Correctly: style.css uses flexbox (display: flex) ✓
   - Used Correctly: Custom colors and fonts applied ✓
   - Status: ✅ Complete

4. **FILE RELEVANCE REPORT**
   For EACH uploaded file:
   - File name: [filename]
   - File type: [code/image/document/etc]
   - Role in project: [what it does]
   - **PROJECT MATCH CHECK: Does this file demonstrate "{project_title}"? [Yes/No]**
   - **SKILLS CHECK: Does this file use Month {current_month} skills? [List which skills OR "None detected"]**
   - Relevance: Relevant ✅ / Partially Relevant ⚠️ / Irrelevant ❌
   - Marks given: [X marks]
   - Reason: [detailed explanation]
   - If irrelevant: Flag with "🚨 IRRELEVANT FILE - [specific reason]" and explain why
   
   **MANDATORY CHECKS FOR EACH FILE:**
   ✓ Does filename make sense for the project? (e.g., "portfolio.html" for portfolio project)
   ✓ For images: Does it show the ACTUAL project described in title?
   ✓ For code: Does it implement the project mentioned in title?
   ✓ Does file demonstrate ANY Month {current_month} skills from the learning plan?
   
   **AUTOMATIC 0 MARKS IF:**
   - Image shows random photo (person, vehicle, nature, movie scene)
   - Code file is empty or contains only comments
   - File is completely unrelated to project title
   - File doesn't demonstrate ANY learned skills from Month {current_month}

5. **LEARNING-BASED FEEDBACK**
   - Strengths: [List specific learned skills they demonstrated with examples]
   - Gaps: [List expected concepts that are missing]
   - Mistakes: [Point out misuse of concepts with corrections]
   - Week-wise coverage: [Summary of which weeks' content they used well]

6. **SCORING BREAKDOWN**
   - Title Match: X/5 - [reason]
   - Description Quality: Y/30 - [reason]
     * Detail Level: A/15
     * Alignment: B/5
     * Uses Learned Concepts: C/10
   - Files Quality: Z/65 - [reason]
   - Total Score: (X+Y+Z)/100
   - Grade: [A/B+/B/C+/C/D/F]

7. **ACTIONABLE IMPROVEMENTS**
   Provide 3-5 specific, numbered steps:
   1. [Specific improvement with example]
   2. [Specific improvement with example]
   3. [Specific improvement with example]
   ...

8. **FINAL VERDICT**
   - Accept ✅ (Score >= 70)
   - Needs Improvement ⚠️ (Score 50-69)
   - Resubmit ❌ (Score < 50)
   - Recommendation: [Brief advice aligned with learning stage]

INTEGRITY & FAIRNESS RULES:
- Do NOT assume external knowledge beyond the roadmap
- Do NOT penalize for not using topics not taught yet
- Be STRICT about relevance, but SUPPORTIVE in feedback
- Base all judgments strictly on uploaded files and Roadmap_Dashboard data
- For EACH file, explicitly state if it's RELEVANT or IRRELEVANT
- Give 0 marks to files that don't contribute to the project
- Identify fake, unrelated, or placeholder files and flag them clearly

SCORING RULES (STRICT):
- Title Match: 0-5 marks (exact match = 5, no match = 0)
- Description: 0-30 marks (detail: 0-15 + alignment: 0-5 + learned concepts: 0-10)
- Files: 0-65 marks (ONLY relevant files get marks, heavily penalize if learned skills not shown)

GRADE SCALE:
- 90-100 (A): Exceptional - perfect title, detailed description with learned concepts, excellent files showing all Month {current_month} skills
- 80-89 (B+): Very Good - good match, description mentions learned concepts, files show most Month {current_month} skills
- 70-79 (B): Good - matches title, description explains some learned concepts, files show key Month {current_month} skills
- 60-69 (C+): Acceptable - partial match, description vaguely relates to learning, files show few learned concepts
- 50-59 (C): Below Average - weak match, minimal learned concepts in description, files barely show Month {current_month} learning
- 40-49 (D): Poor - wrong project, no learned concepts mentioned, files don't demonstrate Month {current_month} skills
- Below 40 (F): Failing - completely wrong, no connection to Month {current_month} learning, useless files

Your role is to act as a fair academic evaluator focused on learning validation, not just project completion.

Return ONLY valid JSON with the exact structure shown above."""

            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                'model': 'sonar',  # Updated to current Perplexity model name
                'messages': [
                    {'role': 'system', 'content': 'You are a STRICT Senior Technical Manager with HIGH STANDARDS. Be critical and precise. Most projects have flaws - identify them. Do NOT be lenient. Sound professional and direct.'},
                    {'role': 'user', 'content': evaluation_prompt}
                ],
                'temperature': 0.3,  # Lower temperature for more consistent, stricter evaluation
                'max_tokens': 2500
            }
            
            # Call Perplexity API
            evaluation_result = None
            print(f"\n🤖 === CALLING PERPLEXITY AI FOR PROJECT EVALUATION ===")
            print(f"API Key: {api_key[:20]}..." if api_key else "❌ API Key not loaded!")
            
            if not api_key:
                print("❌ PERPLEXITY_API_KEY not found in environment variables!")
                print("⚠️ Will use fallback scoring system instead of AI evaluation")
            
            try:
                print(f"📤 Sending request to Perplexity API...")
                response = requests.post(
                    'https://api.perplexity.ai/chat/completions',
                    headers=headers,
                    json=payload,
                    timeout=30
                )
                
                print(f"📥 Response Status Code: {response.status_code}")
                
                if response.status_code == 200:
                    result = response.json()
                    ai_content = result['choices'][0]['message']['content']
                    
                    print(f"✅ AI Response received ({len(ai_content)} characters)")
                    print(f"Preview: {ai_content[:200]}...")
                    
                    # Parse JSON from response
                    import re
                    import json as json_module
                    json_pattern = r'\{.*\}'
                    json_match = re.search(json_pattern, ai_content, re.DOTALL)
                    if json_match:
                        evaluation_result = json_module.loads(json_match.group(0))
                        print(f"✅ AI Evaluation Score: {evaluation_result.get('score')}/100 ({evaluation_result.get('grade')})")
                        
                        # ⚠️ CRITICAL VALIDATION: Enforce 0/65 for all irrelevant files
                        if 'files_evaluation' in evaluation_result:
                            files_eval = evaluation_result['files_evaluation']
                            files_breakdown = files_eval.get('files_breakdown', [])
                            
                            # Count relevant vs irrelevant files
                            total_files = len(files_breakdown)
                            irrelevant_count = sum(1 for f in files_breakdown if not f.get('is_relevant', False))
                            
                            # Check if project requires CODE but only non-code files uploaded
                            project_requires_code = any(keyword in project_title.lower() for keyword in 
                                ['website', 'web', 'html', 'css', 'javascript', 'portfolio', 'app', 'application', 
                                 'program', 'code', 'system', 'software', 'api', 'backend', 'frontend', 'ml', 
                                 'machine learning', 'data analysis', 'python', 'java', 'react'])
                            
                            has_any_code = any(f.get('filename', '').lower().endswith(('.html', '.css', '.js', '.py', 
                                '.java', '.cpp', '.c', '.jsx', '.tsx', '.php', '.rb', '.go', '.rs', '.kt')) 
                                for f in files_breakdown)
                            
                            only_images = all(f.get('filename', '').lower().endswith(('.jpg', '.jpeg', '.png', '.gif', 
                                '.bmp', '.svg', '.webp', '.ico')) for f in files_breakdown)
                            
                            # CRITICAL: If project needs code but only images uploaded → 0/65
                            if project_requires_code and not has_any_code and only_images:
                                old_score = files_eval.get('score', 0)
                                if old_score > 0:
                                    print(f"🚨 CRITICAL OVERRIDE: Project '{project_title}' requires CODE but only images uploaded!")
                                    print(f"🚨 Files uploaded: {[f.get('filename') for f in files_breakdown]}")
                                    print(f"🚨 Forcing files_score from {old_score}/65 → 0/65 (MANDATORY RULE)")
                                    files_eval['score'] = 0
                                
                                # Mark ALL files as irrelevant in breakdown
                                for file_detail in files_breakdown:
                                    file_detail['is_relevant'] = False
                                    file_detail['marks_given'] = 0
                                    if 'USELESS FILE' not in file_detail.get('reason', ''):
                                        file_detail['reason'] = f"USELESS FILE - Project requires CODE (HTML/CSS/JS/etc) but this is just an image. Random photos don't count as project implementation. {file_detail.get('reason', '')}"
                                
                                files_eval['relevant_files'] = 0
                                files_eval['useless_files'] = total_files
                                files_eval['summary'] = f"0 useful files out of {total_files} uploaded. Project requires CODE files but only images provided. Cannot verify implementation without actual code."
                                
                                # Recalculate total score
                                title_score = evaluation_result.get('title_evaluation', {}).get('score', 0)
                                desc_score = evaluation_result.get('description_evaluation', {}).get('score', 0)
                                evaluation_result['score'] = title_score + desc_score + 0
                                
                                # Update grade
                                new_total = evaluation_result['score']
                                if new_total >= 90:
                                    evaluation_result['grade'] = 'A'
                                elif new_total >= 80:
                                    evaluation_result['grade'] = 'B+'
                                elif new_total >= 70:
                                    evaluation_result['grade'] = 'B'
                                elif new_total >= 60:
                                    evaluation_result['grade'] = 'C+'
                                elif new_total >= 50:
                                    evaluation_result['grade'] = 'C'
                                elif new_total >= 40:
                                    evaluation_result['grade'] = 'D'
                                else:
                                    evaluation_result['grade'] = 'F'
                                
                                print(f"✅ OVERRIDE COMPLETE: Score {old_score} → 0/65, Total: {new_total}/100 ({evaluation_result['grade']})")
                            
                            # ADDITIONAL CHECK: If AI gave marks to images but project requires code
                            if not has_any_code and only_images and project_requires_code:
                                current_score = files_eval.get('score', 0)
                                if current_score > 0:
                                    print(f"🚨 SECONDARY OVERRIDE: AI gave {current_score}/65 to images for code project!")
                                    print(f"🚨 Project '{project_title}' needs CODE, forcing 0/65")
                                    files_eval['score'] = 0
                                    
                                    # Force all files to irrelevant
                                for file_detail in files_breakdown:
                                    file_detail['is_relevant'] = False
                                    file_detail['marks_given'] = 0
                                    file_detail['reason'] = f"USELESS FILE - Project requires actual CODE files (HTML/CSS/JS/Python), not random images. {file_detail.get('reason', '')}"
                                
                                files_eval['relevant_files'] = 0
                                files_eval['useless_files'] = total_files
                                
                                # Recalculate
                                title_score = evaluation_result.get('title_evaluation', {}).get('score', 0)
                                desc_score = evaluation_result.get('description_evaluation', {}).get('score', 0)
                                evaluation_result['score'] = title_score + desc_score + 0
                                
                                # Update grade
                                new_total = evaluation_result['score']
                                if new_total >= 90:
                                    evaluation_result['grade'] = 'A'
                                elif new_total >= 80:
                                    evaluation_result['grade'] = 'B+'
                                elif new_total >= 70:
                                    evaluation_result['grade'] = 'B'
                                elif new_total >= 60:
                                    evaluation_result['grade'] = 'C+'
                                elif new_total >= 50:
                                    evaluation_result['grade'] = 'C'
                                elif new_total >= 40:
                                    evaluation_result['grade'] = 'D'
                                else:
                                    evaluation_result['grade'] = 'F'
                                
                                print(f"✅ SECONDARY OVERRIDE: {current_score}/65 → 0/65, Total: {new_total}/100")
                        
                            # If ALL files are irrelevant, force files_score to 0
                            if total_files > 0 and irrelevant_count == total_files:
                                old_score = files_eval.get('score', 0)
                                if old_score > 0:
                                    print(f"⚠️ CRITICAL FIX: AI gave {old_score}/65 but ALL files are irrelevant!")
                                    print(f"⚠️ Enforcing 0/65 files score (all {irrelevant_count} files are useless)")
                                    files_eval['score'] = 0
                                    
                                    # Recalculate total score
                                    title_score = evaluation_result.get('title_evaluation', {}).get('score', 0)
                                    desc_score = evaluation_result.get('description_evaluation', {}).get('score', 0)
                                    evaluation_result['score'] = title_score + desc_score + 0
                                    
                                    # Update grade based on new score
                                    new_total = evaluation_result['score']
                                    if new_total >= 90:
                                        evaluation_result['grade'] = 'A'
                                    elif new_total >= 80:
                                        evaluation_result['grade'] = 'B+'
                                    elif new_total >= 70:
                                        evaluation_result['grade'] = 'B'
                                    elif new_total >= 60:
                                        evaluation_result['grade'] = 'C+'
                                    elif new_total >= 50:
                                        evaluation_result['grade'] = 'C'
                                    elif new_total >= 40:
                                        evaluation_result['grade'] = 'D'
                                    else:
                                        evaluation_result['grade'] = 'F'
                                    
                                    print(f"✅ Fixed score: {old_score} → 0/65 for files")
                                    print(f"✅ Total score recalculated: {new_total}/100 ({evaluation_result['grade']})")
                    
                    # ⚠️ CRITICAL FIX: Ensure feedback exists
                    if 'feedback' not in evaluation_result or not evaluation_result.get('feedback'):
                        print(f"⚠️ WARNING: AI response missing 'feedback' field!")
                        print(f"⚠️ Generating fallback feedback from AI response data...")
                        
                        # Build feedback from the structured data
                        feedback_parts = []
                        feedback_parts.append(f"I reviewed your Month {current_month} project submission.")
                        feedback_parts.append(f"\n\n**SCORE SUMMARY**")
                        feedback_parts.append(f"Your project scored {evaluation_result.get('score')}/100 ({evaluation_result.get('grade')} grade)")
                        
                        if 'title_evaluation' in evaluation_result:
                            feedback_parts.append(f"\n\n**TITLE EVALUATION**")
                            feedback_parts.append(evaluation_result['title_evaluation'].get('reason', ''))
                        
                        if 'description_evaluation' in evaluation_result:
                            feedback_parts.append(f"\n\n**DESCRIPTION EVALUATION**")
                            desc_eval = evaluation_result['description_evaluation']
                            feedback_parts.append(f"Score: {desc_eval.get('score')}/30")
                            feedback_parts.append(f"• Detail: {desc_eval.get('detail_score', 0)}/15 - {desc_eval.get('detail_reason', '')}")
                            feedback_parts.append(f"• Alignment: {desc_eval.get('alignment_score', 0)}/10 - {desc_eval.get('alignment_reason', '')}")
                        
                        if 'files_evaluation' in evaluation_result:
                            feedback_parts.append(f"\n\n**FILES EVALUATION**")
                            files_eval = evaluation_result['files_evaluation']
                            feedback_parts.append(f"Score: {files_eval.get('score')}/65")
                            feedback_parts.append(f"Summary: {files_eval.get('summary', '')}")
                            
                            if 'files_breakdown' in files_eval:
                                feedback_parts.append(f"\n\n**FILE-BY-FILE ANALYSIS**")
                                for file_detail in files_eval['files_breakdown']:
                                    relevance = "✅ Relevant" if file_detail.get('is_relevant') else "❌ IRRELEVANT"
                                    feedback_parts.append(f"\n• {file_detail.get('filename')} ({file_detail.get('marks_given')}/65): {relevance}")
                                    feedback_parts.append(f"  {file_detail.get('reason', '')}")
                        
                        if evaluation_result.get('strengths'):
                            feedback_parts.append(f"\n\n**STRENGTHS**")
                            for strength in evaluation_result['strengths']:
                                feedback_parts.append(f"• {strength}")
                        
                        if evaluation_result.get('weaknesses'):
                            feedback_parts.append(f"\n\n**CRITICAL ISSUES**")
                            for weakness in evaluation_result['weaknesses']:
                                feedback_parts.append(f"• {weakness}")
                        
                        if evaluation_result.get('improvements'):
                            feedback_parts.append(f"\n\n**ACTIONABLE IMPROVEMENTS**")
                            for idx, improvement in enumerate(evaluation_result['improvements'], 1):
                                feedback_parts.append(f"{idx}. {improvement}")
                        
                        evaluation_result['feedback'] = '\n'.join(feedback_parts)
                        print(f"✅ Feedback generated ({len(evaluation_result['feedback'])} characters)")
                    
                        print(f"🎯 AI evaluation successful - using AI-generated feedback")
                    else:
                        print(f"⚠️ Could not parse JSON from AI response")
                        print(f"Response content: {ai_content[:500]}...")
                else:
                    print(f"❌ API Error: Status {response.status_code}")
                    print(f"Response: {response.text[:500]}")
            except Exception as e:
                print(f"❌ AI evaluation failed: {str(e)}")
                import traceback
                print(f"Traceback: {traceback.format_exc()}")
            
            # Fallback evaluation if AI fails - Be realistic and week-aware
            if not evaluation_result:
                print("\n⚠️ === USING FALLBACK EVALUATION (AI NOT AVAILABLE) ===")
                print("Generating evaluation using rule-based scoring system...")
                # Analyze based on title and description
                has_testing = any(word in project_description.lower() for word in ['test', 'testing', 'unit test', 'pytest', 'jest'])
                has_error_handling = any(word in project_description.lower() for word in ['error', 'exception', 'try-catch', 'validation'])
                has_documentation = any(word in project_description.lower() for word in ['document', 'readme', 'api doc', 'swagger'])
                has_security = any(word in project_description.lower() for word in ['auth', 'security', 'encrypt', 'jwt', 'validation'])
                
                # Check if they're using learned skills in description
                skills_used = []
                skills_missing = []
                for skill in learned_skills:  # Check ALL skills, not just first 5
                    if skill.lower() in project_description.lower():
                        skills_used.append(skill)
                    else:
                        skills_missing.append(skill)
                
                # Check if project title/description matches expected project
                project_matches_expected = False
                match_quality = 0
                if expected_project:
                    expected_keywords = expected_project.lower().split()
                    project_text = (project_title + ' ' + project_description).lower()
                    matching_keywords = [kw for kw in expected_keywords if kw in project_text and len(kw) > 3]
                    if expected_keywords:
                        match_quality = len(matching_keywords) / len(expected_keywords)
                    project_matches_expected = match_quality >= 0.4  # Require 40% match
                
                # Check description RELEVANCE (not just length)
                desc_words = project_description.lower().split()
                desc_word_count = len(desc_words)
                
                # Check if description contains relevant technical terms
                technical_terms = ['api', 'database', 'function', 'class', 'method', 'algorithm', 
                                 'structure', 'implementation', 'design', 'architecture', 'interface',
                                 'component', 'module', 'feature', 'logic', 'data', 'query',
                                 'authentication', 'authorization', 'validation', 'request', 'response']
                
                relevant_tech_terms = sum(1 for term in technical_terms if term in desc_words)
                
                # Check if description mentions implementation details (not just features)
                implementation_indicators = ['implemented', 'created', 'built', 'developed', 'used',
                                            'integrated', 'configured', 'designed', 'structured', 'handles',
                                            'processes', 'manages', 'executes', 'returns', 'validates']
                has_implementation_detail = any(word in desc_words for word in implementation_indicators)
                
                # Check for generic/filler words that suggest low effort
                filler_phrases = ['this project', 'very good', 'nice project', 'great work', 
                                'simple project', 'basic project', 'easy to', 'user friendly']
                has_filler_content = any(phrase in project_description.lower() for phrase in filler_phrases)
                
                # Evaluate description quality based on relevance
                is_relevant_description = (relevant_tech_terms >= 3 and has_implementation_detail and not has_filler_content)
                is_generic_description = (relevant_tech_terms < 2 or has_filler_content)
                
                # STRICT scoring - start lower
                base_score = 55  # Start at C grade - must earn higher scores
                
                # Project match is CRITICAL
                if project_matches_expected and match_quality >= 0.6:
                    base_score += 15  # Good match
                elif project_matches_expected and match_quality >= 0.4:
                    base_score += 8   # Partial match
                else:
                    base_score -= 5   # Wrong project penalty
                
                # Skills usage - MANDATORY
                if len(skills_used) == len(learned_skills):
                    base_score += 15  # All skills present
                elif len(skills_used) >= len(learned_skills) * 0.7:
                    base_score += 10  # Most skills present
                elif len(skills_used) >= len(learned_skills) * 0.5:
                    base_score += 5   # Some skills present
                else:
                    base_score -= 5   # Too few skills penalty
            
            # Quality indicators
            if has_testing: base_score += 8
            if has_error_handling: base_score += 8
            if has_documentation: base_score += 5
            if has_security: base_score += 5
            
            # Description quality based on RELEVANCE and content (not word count)
            if is_relevant_description:
                base_score += 8  # Relevant technical description
            elif is_generic_description:
                base_score -= 8  # Generic/filler content penalty
            
            # FILE ANALYSIS IMPACT (CRITICAL)
            # Use all_files_analysis array to check individual files
            if all_files_analysis and len(all_files_analysis) > 0:
                # Analyze first file (since most submissions are single file)
                first_file = all_files_analysis[0]
                
                if not first_file.get('has_file'):
                    base_score = min(base_score, 50)  # No file = max 50
                    print("FILE PENALTY: No file uploaded - capped at 50/100")
                elif first_file.get('is_code_file'):
                    # CODE PROJECT EVALUATION
                    detected_issues = first_file.get('detected_issues', [])
                    if 'File too short - likely incomplete' in detected_issues:
                        base_score = min(base_score, 60)  # < 20 lines = max 60
                        print("FILE PENALTY: Too short (<20 lines) - capped at 60/100")
                    if any('placeholder' in issue.lower() or 'dummy' in issue.lower() for issue in detected_issues):
                        base_score -= 20  # Placeholder content = -20
                        print("FILE PENALTY: Placeholder/dummy content detected - deducted 20 points")
                    if any('no month' in issue.lower() and 'skills' in issue.lower() for issue in detected_issues):
                        base_score = min(base_score, 45)  # No Month skills in code = max 45
                        print("FILE PENALTY: No Month skills in code - capped at 45/100")
                    if 'File may not contain actual code' in detected_issues:
                        base_score = min(base_score, 55)  # Not real code = max 55
                        print("FILE PENALTY: Not actual code - capped at 55/100")
                    if 'No comments found' in detected_issues:
                        base_score -= 5  # No comments = -5
                        print("FILE PENALTY: No code comments - deducted 5 points")
                    
                    # Code quality bonuses
                    quality_indicators = first_file.get('code_quality_indicators', [])
                    if any('functions' in qi.lower() or 'classes' in qi.lower() for qi in quality_indicators):
                        base_score += 5
                        print("FILE BONUS: Functions/classes found - added 5 points")
                    if any('error handling' in qi.lower() for qi in quality_indicators):
                        base_score += 5
                        print("FILE BONUS: Error handling found - added 5 points")
                    if any('testing' in qi.lower() for qi in quality_indicators):
                        base_score += 5
                        print("FILE BONUS: Testing code found - added 5 points")
                    if any('external libraries' in qi.lower() for qi in quality_indicators):
                        base_score += 5
                        print("FILE BONUS: External libraries used - added 5 points")
                    if any('all' in qi.lower() and 'skills' in qi.lower() for qi in quality_indicators):
                        base_score += 10
                        print("FILE BONUS: All learned skills in code - added 10 points")
                        
                elif first_file.get('is_project_file'):
                    # NON-CODE PROJECT EVALUATION (Power BI, Excel, Design, Archives, etc.)
                    detected_issues = first_file.get('detected_issues', [])
                    quality_indicators = first_file.get('code_quality_indicators', [])
                    file_type = first_file.get('file_type', 'unknown')
                    
                    print(f"FILE INFO: Valid {file_type} project file detected")
                    print(f"FILE INFO: Quality indicators: {quality_indicators}")
                    print(f"FILE INFO: Issues: {detected_issues}")
                    
                    # Check for issues
                    if any('too small' in issue.lower() for issue in detected_issues):
                        base_score = min(base_score, 60)
                        print("FILE PENALTY: File too small - likely incomplete - capped at 60/100")
                    if any('does not mention' in issue.lower() for issue in detected_issues):
                        base_score -= 15
                        print("FILE PENALTY: Description doesn't explain file contents - deducted 15 points")
                    if any('only' in issue.lower() and 'skills mentioned' in issue.lower() for issue in detected_issues):
                        base_score -= 10
                        print("FILE PENALTY: Few Month skills in description - deducted 10 points")
                    
                    # Give bonuses for proper file upload
                    if any('valid' in qi.lower() and 'file uploaded' in qi.lower() for qi in quality_indicators):
                        base_score += 10
                        print("FILE BONUS: Appropriate project file format - added 10 points")
                    if any('mentions' in qi.lower() and 'skills' in qi.lower() for qi in quality_indicators):
                        base_score += 10
                        print("FILE BONUS: Month skills mentioned in description - added 10 points")
                    
                    # ARCHIVE SPECIFIC BONUSES (ZIP files)
                    if file_type == 'archive':
                        if any('contains' in qi.lower() and 'code file' in qi.lower() for qi in quality_indicators):
                            base_score += 15
                            print("FILE BONUS: ZIP contains code files - added 15 points")
                        if any('contains' in qi.lower() and 'screenshot' in qi.lower() for qi in quality_indicators):
                            base_score += 10
                            print("FILE BONUS: ZIP contains screenshots - added 10 points")
                        if any('zip contains month skills' in qi.lower() for qi in quality_indicators):
                            base_score += 15
                            print("FILE BONUS: ZIP code uses Month skills - added 15 points")
                        
                else:
                    # Unrecognized file type
                    print(f"FILE WARNING: File type not recognized - is_code={first_file.get('is_code_file')}, is_project={first_file.get('is_project_file')}")
                    base_score = min(base_score, 40)
                    print("FILE PENALTY: Unrecognized file format - capped at 40/100")
            else:
                # No files uploaded
                base_score = min(base_score, 50)
                print("FILE PENALTY: No files analyzed - capped at 50/100")
            
            # NEW SCORING SYSTEM: Title (5) + Description (30) + Files (65) = 100
            
            # === PART 1: TITLE MATCH (5 marks) ===
            title_score = 0
            title_reason = ""
            
            if project_matches_expected and match_quality >= 0.9:
                title_score = 5
                title_reason = f"Title perfectly matches expected Month {current_month} project"
            elif project_matches_expected and match_quality >= 0.7:
                title_score = 4
                title_reason = f"Title closely matches expected project with minor variations"
            elif project_matches_expected and match_quality >= 0.5:
                title_score = 3
                title_reason = f"Title partially matches expected project"
            elif project_matches_expected and match_quality >= 0.3:
                title_score = 1
                title_reason = f"Title has some relation to expected project"
            else:
                title_score = 0
                title_reason = f"Title does not match expected project: {expected_project}"
            
            # === PART 2: DESCRIPTION EVALUATION (30 marks) ===
            # A. Detail Level (20 marks)
            detail_score = 0
            detail_reason = ""
            
            # More reasonable thresholds - reward detailed descriptions
            if relevant_tech_terms >= 8 and has_implementation_detail and desc_word_count > 80:
                detail_score = 19
                detail_reason = "Exceptional detail - specific technologies, implementation approach, technical depth"
            elif relevant_tech_terms >= 6 and has_implementation_detail and desc_word_count > 60:
                detail_score = 16
                detail_reason = "Very detailed - explains what was built and how it works"
            elif relevant_tech_terms >= 4 and has_implementation_detail and desc_word_count > 40:
                detail_score = 12
                detail_reason = "Good detail - describes main features and technologies"
            elif relevant_tech_terms >= 2 and desc_word_count > 25:
                detail_score = 8
                detail_reason = "Basic detail - lists features but could use more depth"
            elif desc_word_count > 15:
                detail_score = 4
                detail_reason = "Minimal detail - very brief and generic"
            else:
                detail_score = 0
                detail_reason = "No meaningful description provided"
            
            # B. Alignment with Title (10 marks)
            alignment_score = 0
            alignment_reason = ""
            
            # Check if description explains the project mentioned in title
            title_keywords = set(project_title.lower().split()) - {'a', 'an', 'the', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'using', 'and'}
            desc_keywords = set(project_description.lower().split())
            title_in_desc_ratio = len(title_keywords.intersection(desc_keywords)) / max(len(title_keywords), 1)
            
            # More reasonable alignment scoring
            if title_in_desc_ratio >= 0.7 and not is_generic_description and has_implementation_detail:
                alignment_score = 9
                alignment_reason = "Perfect alignment - description thoroughly explains title claims"
            elif title_in_desc_ratio >= 0.5 and not is_generic_description:
                alignment_score = 8
                alignment_reason = "Strong alignment - description relates well to title"
            elif title_in_desc_ratio >= 0.3:
                alignment_score = 6
                alignment_reason = "Good alignment - description covers title aspects"
            elif title_in_desc_ratio >= 0.15:
                alignment_score = 4
                alignment_reason = "Partial alignment - some gaps or inconsistencies"
            elif title_in_desc_ratio > 0:
                alignment_score = 2
                alignment_reason = "Weak alignment - description barely relates to title"
            else:
                alignment_score = 0
                alignment_reason = "No alignment - description unrelated to title"
            
            description_score = detail_score + alignment_score
            
            # === PART 3: FILES EVALUATION (65 marks) ===
            files_score = 0
            files_breakdown = []
            relevant_files_count = 0
            useless_files_count = 0
            
            if not file_analysis or not file_analysis.get('has_file'):
                files_score = 0
                files_breakdown.append({
                    'filename': 'No files',
                    'is_relevant': False,
                    'marks_given': 0,
                    'reason': 'No files uploaded - cannot verify implementation'
                })
            else:
                # Analyze each file
                for file_info in all_files_analysis:
                    filename = file_info.get('filename', 'Unknown')
                    is_code = file_info.get('is_code_file', False)
                    is_project = file_info.get('is_project_file', False)
                    issues = file_info.get('detected_issues', [])
                    quality = file_info.get('code_quality_indicators', [])
                    
                    file_marks = 0
                    file_relevant = True
                    file_reason = ""
                    
                    # Check if file is useless
                    # IMPORTANT: Code files should NEVER be marked as useless
                    is_useless = False
                    
                    if is_code:
                        # Code files are ALWAYS relevant, even if they have issues
                        is_useless = False
                    else:
                        # For non-code files, check if they are useless
                        is_useless = (
                            'Not a recognized code or project file format' in issues or
                            'Could not parse file content' in issues or
                            'File may not contain actual code' in issues or
                            'IRRELEVANT FILE' in ' '.join(issues) or  # Check for irrelevant screenshots/files
                            is_project == False  # AI Vision marked as not a project file
                        )
                    
                    if is_useless:
                        file_relevant = False
                        useless_files_count += 1
                        # Extract the specific irrelevant reason from issues
                        irrelevant_reason = next((issue for issue in issues if 'IRRELEVANT FILE' in issue), None)
                        if irrelevant_reason:
                            file_reason = irrelevant_reason  # Use the detailed AI Vision detection message
                        else:
                            file_reason = f"USELESS FILE - Not relevant to project, no marks given"
                    elif is_code or is_project:
                        relevant_files_count += 1
                        
                        # Base marks for having a relevant file
                        file_marks = 15
                        
                        # Add marks based on quality
                        if 'Contains functions/classes' in quality:
                            file_marks += 8
                        if 'Has error handling' in quality:
                            file_marks += 7
                        if 'Includes testing code' in quality:
                            file_marks += 7
                        if 'Uses external libraries' in quality:
                            file_marks += 5
                        if any('Month' in q and 'skills' in q for q in quality):
                            file_marks += 10
                        
                        # No penalties - marks based only on positive qualities found
                        # If file has issues, it simply gets fewer marks (not negative deductions)
                        
                        file_marks = max(0, min(file_marks, 50))  # Cap per file at 50
                        file_reason = f"{'Code' if is_code else 'Project'} file - {len(quality)} quality indicators, {len(issues)} issues"
                    else:
                        file_relevant = False
                        useless_files_count += 1
                        file_reason = "File type not appropriate for this project"
                    
                    files_breakdown.append({
                        'filename': filename,
                        'is_relevant': file_relevant,
                        'marks_given': file_marks,
                        'reason': file_reason
                    })
                    
                    files_score += file_marks
                
                # Cap files score at 65
                files_score = min(files_score, 65)
            
            # Calculate total score
            base_score = title_score + description_score + files_score
            base_score = max(0, min(100, base_score))
            
            # Determine grade
            if base_score >= 90: grade = 'A'
            elif base_score >= 80: grade = 'B+'
            elif base_score >= 70: grade = 'B'
            elif base_score >= 60: grade = 'C+'
            elif base_score >= 50: grade = 'C'
            elif base_score >= 40: grade = 'D'
            else: grade = 'F'
            
            # Build strengths based on new scoring
            strengths = []
            
            if title_score >= 4:
                strengths.append(f'Title matches expected Month {current_month} project ({title_score}/5)')
            if detail_score >= 14:
                strengths.append(f'Description provides good technical detail ({detail_score}/20)')
            if alignment_score >= 7:
                strengths.append(f'Description aligns well with title ({alignment_score}/10)')
            if relevant_files_count > 0:
                strengths.append(f'{relevant_files_count} relevant file(s) uploaded demonstrating implementation')
            if files_score >= 40:
                strengths.append(f'Files show good quality implementation ({files_score}/65)')
            
            if not strengths:
                strengths.append('Project submission received')
            
            # Build weaknesses
            weaknesses = []
            
            if title_score < 3:
                weaknesses.append(f'Title does not match expected Month {current_month} project ({title_score}/5)')
            if detail_score < 11:
                weaknesses.append(f'Description lacks technical depth and detail ({detail_score}/20)')
            if alignment_score < 6:
                weaknesses.append(f'Description does not align well with title ({alignment_score}/10)')
            if useless_files_count > 0:
                weaknesses.append(f'Uploaded {useless_files_count} useless/irrelevant file(s) - received 0 marks')
            if relevant_files_count == 0:
                weaknesses.append('No relevant files uploaded - cannot verify implementation')
            if files_score < 30:
                weaknesses.append(f'Files show poor quality or incomplete implementation ({files_score}/65)')
            
            # Build improvements
            improvements = []
            
            if title_score < 5:
                improvements.append(f'Align project title with expected Month {current_month} project: {expected_project}')
            if detail_score < 16:
                improvements.append('Add more technical detail to description: explain implementation approach, algorithms, data structures')
            if alignment_score < 8:
                improvements.append('Ensure description thoroughly explains what the title claims - be specific about features')
            if useless_files_count > 0:
                improvements.append(f'Remove {useless_files_count} irrelevant file(s) - only upload files needed for the project')
            if relevant_files_count == 0:
                improvements.append('Upload project files to demonstrate implementation (code, screenshots, documentation)')
            if files_score < 40:
                improvements.append('Improve file quality: add error handling, testing, proper structure, and Month skills')
            
            if not improvements:
                improvements.append('Continue following best practices and Month curriculum')
            
            # Build detailed, personalized feedback
            files_summary = f"{relevant_files_count} relevant file(s), {useless_files_count} useless file(s)" if file_analysis and file_analysis.get('has_file') else "No files uploaded"
            
            # Create detailed file-by-file analysis for feedback
            file_analysis_text = ""
            if all_files_analysis and len(all_files_analysis) > 0:
                file_analysis_text += "\n\nFILE-BY-FILE ANALYSIS\n\n"
                for idx, file_info in enumerate(all_files_analysis, 1):
                    file_breakdown = files_breakdown[idx-1] if idx <= len(files_breakdown) else {}
                    filename = file_info.get('filename', 'Unknown')
                    marks = file_breakdown.get('marks_given', 0)
                    reason = file_breakdown.get('reason', '')
                    is_relevant = file_breakdown.get('is_relevant', False)
                    
                    file_analysis_text += f"\n{idx}. {filename}\n"
                    if is_relevant:
                        file_analysis_text += f"   RELEVANT - Received {marks} marks\n"
                        file_analysis_text += f"   Reason: {reason}\n"
                        # Add specific quality indicators found
                        qualities = file_info.get('code_quality_indicators', [])
                        if qualities:
                            file_analysis_text += f"   Strengths: {', '.join(qualities[:3])}\n"
                    else:
                        file_analysis_text += f"   IRRELEVANT - 0 marks\n"
                        file_analysis_text += f"   Reason: {reason}\n"
                    
                    # Add issues if present
                    issues = file_info.get('detected_issues', [])
                    if issues and is_relevant:
                        file_analysis_text += f"   Issues found: {', '.join(issues[:2])}\n"
            
            # Build professional guidance paragraphs
            title_guidance = ""
            if title_score < 3:
                title_guidance = f"Your project title '{project_title}' doesn't align with the expected Month {current_month} project: '{expected_project}'. This makes it difficult to assess whether you're demonstrating the required skills. Make sure your title clearly indicates what you're building and matches the monthly curriculum."
            elif title_score < 5:
                title_guidance = f"Your project title is close to the expected '{expected_project}', but could be more specific. A clear, descriptive title helps evaluators understand your project immediately."
            
            description_guidance = ""
            if detail_score < 11:
                description_guidance = f"Your description lacks technical depth (scored {detail_score}/20 for detail). I need to see: (1) WHAT you built - specific features and functionality, (2) HOW you built it - technologies, frameworks, and implementation approach, (3) WHY you made certain technical decisions. Current description has only {len(project_description.split())} words with minimal technical terms. Aim for 100+ words explaining the architecture, data flow, and key algorithms used."
            elif detail_score < 16:
                description_guidance = f"Your description provides some detail ({detail_score}/20) but needs more technical specificity. Explain implementation patterns, data structures used, and any challenges you solved. Don't just list features - explain HOW they work."
            
            if alignment_score < 6:
                description_guidance += f" Additionally, your description doesn't align well with your title (scored {alignment_score}/10). Make sure every claim in the title is thoroughly explained in the description."
            
            files_guidance = ""
            if useless_files_count > 0:
                useless_file_names = [f['filename'] for f in files_breakdown if not f.get('is_relevant', False)]
                files_guidance = f"CRITICAL ISSUE: You uploaded {useless_files_count} irrelevant file(s) - {', '.join(useless_file_names)} - which received 0 marks. "
                
                # Explain what's wrong with each irrelevant file
                for file_breakdown_item in files_breakdown:
                    if not file_breakdown_item.get('is_relevant', False):
                        filename = file_breakdown_item.get('filename', '')
                        reason = file_breakdown_item.get('reason', '')
                        files_guidance += f"'{filename}' was rejected because: {reason}. "
                
                files_guidance += f"For a {expected_project} project, I expect to see: (1) Source code files (.py/.js/.java), (2) Screenshots of running application, (3) Documentation explaining setup. Every file you upload should directly contribute to proving you built this project."
            
            if relevant_files_count == 0:
                files_guidance = f"NO RELEVANT FILES: You didn't upload any code or project artifacts I could evaluate. For Month {current_month} project '{expected_project}', I need: (1) Main implementation code, (2) Evidence of working project (screenshots/output), (3) Optional: tests, documentation, data files. Without these, I cannot verify you actually built the project described."
            elif files_score < 30:
                files_guidance += f" Your uploaded files scored only {files_score}/65, indicating quality issues. "
                common_issues = []
                for file_info in all_files_analysis:
                    common_issues.extend(file_info.get('detected_issues', []))
                if common_issues:
                    files_guidance += f"Common problems I found: {', '.join(list(set(common_issues))[:3])}. "
            
            # Build comprehensive feedback with clear structure
            feedback = f"""I personally reviewed your Month {current_month} project submission and here's my detailed evaluation.

**SCORE SUMMARY**
Your project scored {base_score}/100 ({grade} grade)

**SCORE BREAKDOWN**
• Title Match: {title_score}/5
• Description Quality: {description_score}/30
• Files Quality: {files_score}/65

**TITLE EVALUATION**
{title_reason}

**DESCRIPTION EVALUATION**
{description_guidance if description_guidance else f'Your description scored {description_score}/30 (Detail: {detail_score}/20, Alignment: {alignment_score}/10).'}

**FILES EVALUATION**
{files_guidance if files_guidance else f'You uploaded {len(all_files_analysis) if all_files_analysis else 0} file(s). {files_summary}'}

{file_analysis_text if file_analysis_text else ''}

**CRITICAL ISSUES**
{chr(10).join(['• ' + w for w in weaknesses[:4]]) if weaknesses else '• No major issues found.'}

**STRENGTHS**
{chr(10).join(['• ' + s for s in strengths[:4]]) if strengths else '• Good effort on this submission.'}

**ACTIONABLE NEXT STEPS**
{chr(10).join([f'{i+1}. {imp}' for i, imp in enumerate(improvements[:5])]) if improvements else '1. Continue following best practices.'}

**MONTH {current_month} SKILLS CHECK**
Expected Skills: {skills_str[:150]}{'...' if len(skills_str) > 150 else ''}
Status: {'✅ Good - I can see you applied these skills' if files_score >= 40 else '⚠️ Needs improvement - Demonstrate Month ' + str(current_month) + ' skills clearly'}

**FINAL RECOMMENDATION**
{'Keep up the good work! Focus on the improvements above to reach A grade.' if base_score >= 70 else 'You have potential, but this submission needs significant improvement. Review the Month ' + str(current_month) + ' materials and rebuild with proper implementation.'}
"""
            
            evaluation_result = {
                'score': int(base_score),
                'title_score': title_score,
                'description_score': description_score,
                'files_score': files_score,
                'grade': grade,
                'title_evaluation': {
                    'score': title_score,
                    'reason': title_reason
                },
                'description_evaluation': {
                    'score': description_score,
                    'detail_score': detail_score,
                    'detail_reason': detail_reason,
                    'alignment_score': alignment_score,
                    'alignment_reason': alignment_reason
                },
                'files_evaluation': {
                    'score': files_score,
                    'files_breakdown': files_breakdown,
                    'total_files_uploaded': len(all_files_analysis) if all_files_analysis else 0,
                    'relevant_files': relevant_files_count,
                    'useless_files': useless_files_count,
                    'summary': files_summary
                },
                'strengths': strengths,
                'weaknesses': weaknesses,
                'improvements': improvements,
                'feedback': feedback
            }
        
        # Save to database with complete file data
        submissions_collection = db['project_submissions']
        
        submission_doc = {
            'mobile': mobile,
            'month': current_month,
            'projectTitle': project_title,
            'projectDescription': project_description,
            'filesInfo': files_info,  # Array of file information
            'filesContent': files_content,  # Array of file contents in base64
            'totalFiles': len(files_info),
            'hasCodeFile': has_code_file,
            'hasScreenshot': has_screenshot,
            'hasDocumentation': has_documentation,
            'expectedProject': expected_project,
            'evaluation': evaluation_result,
            'evaluatedBy': 'AI' if evaluation_result and 'score' in evaluation_result else 'Fallback',
            'submittedAt': datetime.now().isoformat(),
            'status': 'evaluated'
        }
        
        # Use mobile_month as unique ID
        submission_id = f"{clean_mobile[-10:]}_month_{current_month}"
        
        submissions_collection.update_one(
            {'_id': submission_id},
            {'$set': submission_doc},
            upsert=True
        )
        
        print(f"Project submission saved with ID: {submission_id}")
        
        return jsonify({
            'success': True,
            'message': 'Project evaluated successfully',
            'evaluatedBy': 'AI' if (evaluation_result and evaluation_result.get('score') and evaluation_result.get('feedback')) else 'Fallback',
            'data': {
                'submissionId': submission_id,
                'score': evaluation_result.get('score'),
                'grade': evaluation_result.get('grade'),
                'strengths': evaluation_result.get('strengths', []),
                'weaknesses': evaluation_result.get('weaknesses', []),
                'improvements': evaluation_result.get('improvements', []),
                'feedback': evaluation_result.get('feedback', ''),
                'month': current_month
            }
        }), 200
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'Error submitting project: {str(e)}'
        }), 500


@app.route('/api/get-project-submissions/<mobile>', methods=['GET'])
def get_project_submissions(mobile):
    """
    Get all project submissions for a user.
    """
    try:
        db = get_db()
        submissions_collection = db['project_submissions']
        
        # Clean mobile number
        clean_mobile = ''.join(filter(str.isdigit, mobile))
        mobile_formats = [
            mobile,
            clean_mobile,
            clean_mobile[-10:],
            f"+91 {clean_mobile[-10:]}",
            f"+91{clean_mobile[-10:]}"
        ]
        
        # Find all submissions for this user
        submissions = list(submissions_collection.find({'mobile': {'$in': mobile_formats}}))
        
        # Convert ObjectId to string and remove large file content from list view
        for sub in submissions:
            if '_id' in sub:
                sub['_id'] = str(sub['_id'])
            # Don't send file content in list view (too large), only metadata
            if 'fileContent' in sub:
                sub['hasFile'] = True
                sub['fileSize'] = len(sub['fileContent']) if sub['fileContent'] else 0
                del sub['fileContent']  # Remove to reduce payload size
        
        return jsonify({
            'success': True,
            'data': {
                'submissions': submissions,
                'totalSubmissions': len(submissions)
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error fetching submissions: {str(e)}'
        }), 500


@app.route('/api/download-project-file/<submission_id>', methods=['GET'])
def download_project_file(submission_id):
    """
    Download the project file from a submission.
    """
    try:
        db = get_db()
        submissions_collection = db['project_submissions']
        
        # Find submission by ID
        submission = submissions_collection.find_one({'_id': submission_id})
        
        if not submission:
            return jsonify({
                'success': False,
                'message': 'Submission not found'
            }), 404
        
        if 'fileContent' not in submission or not submission['fileContent']:
            return jsonify({
                'success': False,
                'message': 'No file attached to this submission'
            }), 404
        
        # Decode base64 file content
        import base64
        from io import BytesIO
        from flask import send_file
        
        file_data = base64.b64decode(submission['fileContent'])
        file_info = submission.get('fileInfo', {})
        filename = file_info.get('filename', 'project_file')
        mimetype = file_info.get('type', 'application/octet-stream')
        
        # Create BytesIO object
        file_obj = BytesIO(file_data)
        file_obj.seek(0)
        
        return send_file(
            file_obj,
            mimetype=mimetype,
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'Error downloading file: {str(e)}'
        }), 500


@app.route('/api/get-project-file-content/<submission_id>', methods=['GET'])
def get_project_file_content(submission_id):
    """
    Get the file content and metadata for a specific submission.
    Returns base64 encoded file content for frontend preview.
    """
    try:
        db = get_db()
        submissions_collection = db['project_submissions']
        
        # Find submission by ID
        submission = submissions_collection.find_one({'_id': submission_id})
        
        if not submission:
            return jsonify({
                'success': False,
                'message': 'Submission not found'
            }), 404
        
        if 'fileContent' not in submission or not submission['fileContent']:
            return jsonify({
                'success': False,
                'message': 'No file attached to this submission'
            }), 404
        
        return jsonify({
            'success': True,
            'data': {
                'fileInfo': submission.get('fileInfo', {}),
                'fileContent': submission['fileContent'],  # Base64 encoded
                'projectTitle': submission.get('projectTitle', ''),
                'projectDescription': submission.get('projectDescription', ''),
                'submittedAt': submission.get('submittedAt', '')
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error fetching file: {str(e)}'
        }), 500


# ==================================================================================
# APPLICATION STARTUP
# ==================================================================================

if __name__ == '__main__':
    import subprocess
    import sys
    import threading
    import time
    
    # Ensure loading questions/facts are populated
    ensure_loading_content_populated()
    
    # Start the chatbot API in a separate process (DISABLED for testing)
    # def start_chatbot_api():
    #     try:
    #         print("🤖 Starting Chatbot API on port 5001...")
    #         chatbot_process = subprocess.Popen(
    #             [sys.executable, 'chatbot_api.py'],
    #             cwd=os.path.dirname(os.path.abspath(__file__)),
    #             stdout=subprocess.PIPE,
    #             stderr=subprocess.STDOUT,
    #             text=True
    #         )
    #         # Stream chatbot output
    #         for line in chatbot_process.stdout:
    #             print(f"[Chatbot] {line.strip()}")
    #     except Exception as e:
    #         print(f"❌ Failed to start Chatbot API: {e}")
    
    # Start chatbot in background thread (DISABLED for testing)
    # chatbot_thread = threading.Thread(target=start_chatbot_api, daemon=True)
    # chatbot_thread.start()
    
    # Give chatbot time to start (increased for MongoDB Atlas connection)
    # time.sleep(3)
    
    # Use PORT environment variable for Railway/production deployment
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 Starting main Flask API on port {port}...")
    app.run(debug=False, host='0.0.0.0', port=port)


