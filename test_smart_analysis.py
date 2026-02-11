"""
Test script to verify Smart AI Resume Analysis integration
"""
from dotenv import load_dotenv
load_dotenv()
import os
import requests
from pymongo import MongoClient

# Test Configuration
BACKEND_URL = "http://localhost:5000"
TEST_PHONE = "+91 9548418927"  # First document in the collection

def test_mongo_connection():
    """Test MongoDB connection and data retrieval"""
    print("\n" + "="*60)
    print("1. Testing MongoDB Connection")
    print("="*60)
    
    try:
        uri = os.environ.get('MONGODB_URI')
        client = MongoClient(uri)
        db = client['Placement_Ai']
        coll = db['student analysis ']  # Note: trailing space
        
        doc = coll.find_one({'_id': TEST_PHONE})
        
        if doc:
            print(f"✅ Found document for {TEST_PHONE}")
            print(f"   - Resume Score: {doc.get('resume_score', 'N/A')}")
            print(f"   - Strengths: {len(doc.get('strengths', []))} items")
            print(f"   - Weaknesses: {len(doc.get('weaknesses', []))} items")
            print(f"   - Missing Skills: {len(doc.get('missing_skills', []))} items")
            print(f"   - ATS Tips: {len(doc.get('ats_tips', []))} items")
            print(f"   - Project Suggestions: {len(doc.get('project_suggestions', []))} items")
            print(f"   - Company Suggestions: {len(doc.get('company_suggestions', []))} items")
            return True
        else:
            print(f"❌ No document found for {TEST_PHONE}")
            return False
            
    except Exception as e:
        print(f"❌ MongoDB Error: {e}")
        return False

def test_backend_api():
    """Test backend API endpoint"""
    print("\n" + "="*60)
    print("2. Testing Backend API Endpoint")
    print("="*60)
    
    try:
        # Test with mobile parameter
        url = f"{BACKEND_URL}/api/student-analysis"
        params = {'mobile': TEST_PHONE}
        
        print(f"   Requesting: {url}?mobile={TEST_PHONE}")
        response = requests.get(url, params=params, timeout=10)
        
        print(f"   Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                analysis = data.get('data', {})
                print(f"✅ API returned success")
                print(f"   - ID: {analysis.get('id')}")
                print(f"   - Resume Score: {analysis.get('resume_score')}")
                print(f"   - Strengths: {len(analysis.get('strengths', []))} items")
                print(f"   - Weaknesses: {len(analysis.get('weaknesses', []))} items")
                print(f"   - Missing Skills: {len(analysis.get('missing_skills', []))} items")
                print(f"   - ATS Tips: {len(analysis.get('ats_tips', []))} items")
                return True
            else:
                print(f"❌ API returned error: {data.get('message', 'Unknown error')}")
                return False
        else:
            print(f"❌ API request failed with status {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return False
            
    except requests.exceptions.ConnectionError:
        print(f"❌ Cannot connect to backend at {BACKEND_URL}")
        print("   Make sure the backend is running (python app.py)")
        return False
    except Exception as e:
        print(f"❌ API Error: {e}")
        return False

def print_frontend_instructions():
    """Print instructions for testing the frontend"""
    print("\n" + "="*60)
    print("3. Frontend Testing Instructions")
    print("="*60)
    print("""
To test the frontend integration:

1. Make sure the React app is running:
   cd placement-prediction-system
   npm start

2. Log in with a user that has mobile number: {TEST_PHONE}
   (or update localStorage with this mobile number)

3. Navigate to Dashboard → Resume Analysis section

4. Click the "🤖 Smart AI Resume Analysis" button

5. The data should be fetched and displayed with sections:
   - Executive Summary
   - Strengths
   - Weaknesses
   - Actionable Suggestions
   - Missing Skills
   - ATS Optimization Tips
   - Project Suggestions
   - Company Suggestions
   - Skills Identified
   - Company Eligibility Analysis

Expected Behavior:
- If analysis exists: Data displays immediately
- If no analysis: Shows "No existing analysis found. Generating new analysis..."
  (then triggers resume analysis generation via n8n webhook)

Console Logs to Check:
- Open browser DevTools → Console
- Look for: "🤖 Smart Analysis Data Received:"
- Should show all the analysis data fields
""".replace("{TEST_PHONE}", TEST_PHONE))

def main():
    print("\n" + "="*80)
    print(" Smart AI Resume Analysis - Integration Test")
    print("="*80)
    
    # Test MongoDB
    mongo_ok = test_mongo_connection()
    
    # Test Backend API
    api_ok = test_backend_api()
    
    # Print frontend instructions
    print_frontend_instructions()
    
    # Summary
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)
    print(f"   MongoDB Connection: {'✅ PASS' if mongo_ok else '❌ FAIL'}")
    print(f"   Backend API: {'✅ PASS' if api_ok else '❌ FAIL'}")
    print(f"   Frontend: ⏳ Manual testing required (see instructions above)")
    print()
    
    if mongo_ok and api_ok:
        print("✅ All automated tests passed! Ready for frontend testing.")
    else:
        print("❌ Some tests failed. Please fix the issues above.")
    
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
