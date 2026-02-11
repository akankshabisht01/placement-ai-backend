#!/usr/bin/env python3
"""
Enhanced API endpoint to save student analysis data with duplicate prevention
This will be used by n8n to store analysis data only once per phone number
"""

import os
from flask import jsonify, request
from datetime import datetime
from utils.db import get_db

def sync_resume_to_student_analysis(resume_data):
    """
    MANUAL/BULK SYNC ONLY: Sync resume data to student analysis collection
    This function converts resume collection data to student analysis format
    
    NOTE: This is for manual/bulk sync operations only. 
    Normal flow: Prediction → n8n processing → n8n calls /api/save-student-analysis
    
    Args:
        resume_data (dict): Data from resume collection
        
    Returns:
        dict: Result of the sync operation
    """
    try:
        # Extract key information from resume data
        mobile = resume_data.get('phone', '').replace('+', '').replace('-', '').replace(' ', '')
        
        if not mobile:
            return {'success': False, 'error': 'No mobile number found in resume data'}
        
        # Extract prediction scores and info
        prediction = resume_data.get('prediction', {})
        placement_score = prediction.get('placementScore', 0)
        
        # Prepare analysis data
        analysis_data = {
            'mobile': mobile,
            'name': resume_data.get('name', ''),
            'email': resume_data.get('email', ''),
            'summary': f"Resume analysis completed. Placement score: {placement_score}%",
            'resume_score': placement_score,
            'strengths': prediction.get('strongProjects', []),
            'weaknesses': prediction.get('recommendations', [])[:3],  # First 3 as weaknesses
            'missing_skills': prediction.get('missingSkills', []),
            'ats_tips': prediction.get('recommendations', [])[-3:],  # Last 3 as ATS tips
            'project_suggestions': prediction.get('recommendations', []),
            'source': 'placement-ai-resume-sync',
            'action': 'resume_to_analysis_sync',
            'resume_data': resume_data,
            'prediction_data': prediction
        }
        
        # Save to student analysis
        return save_student_analysis_safe(analysis_data)
        
    except Exception as e:
        return {'success': False, 'error': f'Sync failed: {str(e)}'}

def bulk_sync_resumes_to_analysis():
    """
    MANUAL/BULK SYNC ONLY: Bulk sync all resume data to student analysis collection
    This can be used to populate student analysis from existing resume data
    
    WARNING: This bypasses n8n processing and should only be used for:
    - Bulk migration of existing data
    - Emergency data recovery
    - Testing purposes
    
    Normal flow should use n8n: Prediction → n8n → /api/save-student-analysis
    
    Returns:
        dict: Summary of sync results
    """
    try:
        db = get_db()
        resume_collection = db.Resume  # or db.resumes based on your collection name
        
        # Get all resumes that have prediction data
        resumes = list(resume_collection.find({'prediction': {'$exists': True}}))
        
        sync_results = {
            'total_resumes': len(resumes),
            'synced': 0,
            'errors': 0,
            'details': []
        }
        
        for resume in resumes:
            result = sync_resume_to_student_analysis(resume)
            
            if result.get('success'):
                sync_results['synced'] += 1
                sync_results['details'].append({
                    'mobile': resume.get('phone', 'unknown'),
                    'name': resume.get('name', 'unknown'),
                    'status': 'synced'
                })
            else:
                sync_results['errors'] += 1
                sync_results['details'].append({
                    'mobile': resume.get('phone', 'unknown'),
                    'name': resume.get('name', 'unknown'),
                    'status': 'error',
                    'error': result.get('error', 'Unknown error')
                })
        
        return {
            'success': True,
            'results': sync_results
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': f'Bulk sync failed: {str(e)}'
        }

def save_student_analysis_safe(data):
    """
    Save student analysis data to MongoDB with duplicate prevention
    Uses upsert operation to avoid creating duplicate entries
    
    Args:
        data (dict): Student analysis data including mobile, analysis results, etc.
        
    Returns:
        dict: Result with success status and details
    """
    try:
        print(f"🔧 save_student_analysis_safe called with data keys: {list(data.keys())}")
        
        db = get_db()
        collection = db["student analysis "]  # Collection name with trailing space!
        
        # Get phone number - keep the original format (don't clean)
        mobile = data.get('mobile') or data.get('phone') or data.get('phoneNumber') or ''
        mobile = str(mobile).strip()  # Only strip whitespace, keep +91, -, etc.
        
        print(f"📱 Extracted mobile: '{mobile}' (type: {type(mobile).__name__})")
        
        if not mobile:
            print("❌ No mobile number found in data!")
            return {
                'success': False,
                'error': 'Mobile number is required'
            }
        
        # Prepare the document with all analysis data
        # Use mobile number as _id for easy identification
        document = {
            '_id': mobile,  # Set _id to mobile number
            'mobile': mobile,
            'name': data.get('name', ''),
            'email': data.get('email', ''),
            'summary': data.get('summary', ''),
            'resume_score': data.get('resume_score', 0),
            'strengths': data.get('strengths', []),
            'weaknesses': data.get('weaknesses', []),
            'ats_tips': data.get('ats_tips', []),
            'missing_skills': data.get('missing_skills', []),
            'project_suggestions': data.get('project_suggestions', []),
            
            # Company suggestions (handle both array and object formats)
            'company_1_name': data.get('company_1_name', ''),
            'company_1_eligible': data.get('company_1_eligible', ''),
            'company_1_reason': data.get('company_1_reason', ''),
            'company_2_name': data.get('company_2_name', ''),
            'company_2_eligible': data.get('company_2_eligible', ''),
            'company_2_reason': data.get('company_2_reason', ''),
            'company_3_name': data.get('company_3_name', ''),
            'company_3_eligible': data.get('company_3_eligible', ''),
            'company_3_reason': data.get('company_3_reason', ''),
            'company_4_name': data.get('company_4_name', ''),
            'company_4_eligible': data.get('company_4_eligible', ''),
            'company_4_reason': data.get('company_4_reason', ''),
            
            # Metadata
            'source': data.get('source', 'placement-ai'),
            'action': data.get('action', 'analysis_save'),
            'created_at': data.get('timestamp') or datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        
        # Use replace_one with upsert to ensure _id is set correctly
        # replace_one will completely replace the document (including _id on insert)
        print(f"💾 About to call replace_one with _id: '{mobile}'")
        print(f"📄 Document _id field: '{document.get('_id')}'")
        
        result = collection.replace_one(
            {'_id': mobile},     # Filter: find document with this _id (mobile number)
            document,            # Replace with this document (includes _id: mobile)
            upsert=True          # Insert if not found
        )
        
        print(f"✅ Database operation complete. Upserted ID: {result.upserted_id}, Modified: {result.modified_count}")
        
        if result.upserted_id:
            return {
                'success': True,
                'action': 'inserted',
                'document_id': mobile,  # Now _id is the mobile number
                'mobile': mobile,
                'message': 'New student analysis record created'
            }
        else:
            return {
                'success': True,
                'action': 'updated',
                'mobile': mobile,
                'message': 'Existing student analysis record updated'
            }
            
    except Exception as e:
        return {
            'success': False,
            'error': f'Failed to save analysis data: {str(e)}'
        }

# Add this function to app.py
def add_student_analysis_endpoint(app):
    """Add the student analysis endpoint to the Flask app"""
    
    @app.route('/api/save-student-analysis', methods=['POST'])
    def save_student_analysis_endpoint():
        """
        API endpoint to save student analysis data (used by n8n)
        Prevents duplicate entries by using upsert operation
        """
        try:
            data = request.get_json()
            
            if not data:
                return jsonify({
                    'success': False,
                    'error': 'No data provided'
                }), 400
            
            # Save with duplicate prevention
            result = save_student_analysis_safe(data)
            
            if result['success']:
                return jsonify(result), 200
            else:
                return jsonify(result), 400
                
        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

if __name__ == "__main__":
    # Test the function
    sample_data = {
        'mobile': '9876543210',
        'name': 'Test User',
        'email': 'test@example.com',
        'summary': 'Sample analysis summary',
        'resume_score': 85,
        'strengths': ['Good technical skills', 'Strong communication'],
        'weaknesses': ['Needs more experience', 'Limited project portfolio'],
        'ats_tips': ['Use more keywords', 'Improve formatting'],
        'missing_skills': ['Docker', 'Kubernetes'],
        'company_1_name': 'TechCorp',
        'company_1_eligible': 'Yes',
        'company_1_reason': 'Strong technical background'
    }
    
    result = save_student_analysis_safe(sample_data)
    print("Test result:", result)