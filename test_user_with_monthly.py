"""
Test if backend endpoints are working correctly for a user with existing monthly test
"""
from pymongo import MongoClient
import os
from dotenv import load_dotenv
import requests

load_dotenv()

# Connect to MongoDB
mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI")
client = MongoClient(mongo_uri)
db = client[os.getenv("MONGODB_DB", "Placement_Ai")]

print("="*100)
print("TESTING BACKEND ENDPOINTS FOR USER WITH EXISTING MONTHLY TEST")
print("="*100)

# Test users who have monthly tests
test_users = [
    "+91 9084117332",
    "+91 9346333208"
]

for mobile in test_users:
    print(f"\n{'='*100}")
    print(f"USER: {mobile}")
    print(f"{'='*100}")
    
    # Check database directly
    print("\n1. DATABASE CHECK:")
    print("-"*100)
    
    monthly_test_col = db["monthly_test"]
    weekly_analysis_col = db["Weekly_test_analysis"]
    monthly_result_col = db["monthly_test_result"]
    
    # Check weekly tests
    weekly_docs = list(weekly_analysis_col.find({'mobile': mobile}))
    print(f"Weekly tests completed: {len(weekly_docs)}")
    weeks = [doc.get('analysis', {}).get('week') for doc in weekly_docs]
    print(f"Weeks: {sorted(weeks)}")
    
    # Check monthly test
    monthly_doc = monthly_test_col.find_one({'mobile': mobile, 'month': 1})
    print(f"\nMonthly test in DB: {'✅ EXISTS' if monthly_doc else '❌ NOT FOUND'}")
    if monthly_doc:
        print(f"  _id: {monthly_doc.get('_id')}")
        print(f"  mobile: {monthly_doc.get('mobile')}")
        print(f"  month: {monthly_doc.get('month')}")
    
    # Check monthly result
    result_doc = monthly_result_col.find_one({'mobile': mobile, 'month': 1})
    print(f"Monthly result in DB: {'✅ EXISTS' if result_doc else '❌ NOT FOUND'}")
    if result_doc:
        print(f"  Score: {result_doc.get('percentage', 0)}%")
    
    # Test backend endpoints
    print(f"\n2. BACKEND ENDPOINT TESTS:")
    print("-"*100)
    
    # Test eligibility endpoint
    print(f"\nTesting /api/check-month-test-eligibility/{mobile.replace('+91 ', '')}")
    try:
        # Remove +91 and space for URL
        mobile_for_url = mobile.replace("+91 ", "").replace("+91", "")
        response = requests.get(f"http://localhost:5000/api/check-month-test-eligibility/{mobile_for_url}")
        print(f"  Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                unlocked = data.get('data', {}).get('unlocked_months', [])
                print(f"  Unlocked months: {len(unlocked)}")
                for month_data in unlocked:
                    print(f"    Month {month_data.get('month')}: {month_data.get('is_unlocked')}")
            else:
                print(f"  Error: {data.get('message')}")
        else:
            print(f"  Error: HTTP {response.status_code}")
    except Exception as e:
        print(f"  ❌ Connection error: {e}")
        print(f"  (Backend might not be running)")
    
    # Test monthly test status endpoint
    print(f"\nTesting /api/monthly-test-status/{mobile_for_url}/1")
    try:
        response = requests.get(f"http://localhost:5000/api/monthly-test-status/{mobile_for_url}/1")
        print(f"  Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                test_data = data.get('data', {})
                print(f"  test_generated: {test_data.get('test_generated')}")
                print(f"  test_completed: {test_data.get('test_completed')}")
                print(f"  can_start_test: {test_data.get('can_start_test')}")
                print(f"  timer_remaining: {test_data.get('timer_remaining')}s")
                
                print(f"\n  📱 FRONTEND SHOULD SHOW:")
                if test_data.get('test_completed'):
                    print(f"     'Monthly Test Analysis' button")
                elif test_data.get('test_generated') and not test_data.get('can_start_test'):
                    print(f"     Timer countdown: {test_data.get('timer_remaining')} seconds")
                elif test_data.get('test_generated') and test_data.get('can_start_test'):
                    print(f"     'Start Monthly Test' button")
                else:
                    print(f"     'Generate Month 1 Test' button")
            else:
                print(f"  Error: {data.get('error')}")
        else:
            print(f"  Error: HTTP {response.status_code}")
    except Exception as e:
        print(f"  ❌ Connection error: {e}")
        print(f"  (Backend might not be running)")

print(f"\n{'='*100}")
print("RECOMMENDATIONS")
print(f"{'='*100}")
print("""
If backend endpoints are working but frontend still shows 'Generate Test':

1. Check browser console for:
   - [useEffect] monthTestEligibility changed
   - [useEffect] Fetching status for unlocked months
   - [fetchMonthlyTestStatus] Response
   - [Button Render] Month X

2. Check if monthlyTestStatus state is being updated:
   - Open React DevTools
   - Look for monthlyTestStatus in Dashboard component state
   - Should see: {1: {test_generated: true, ...}}

3. Verify mobile number format:
   - Frontend sends: "9084117332" (without +91)
   - Backend normalizes to search: ["+91 9084117332", "919084117332", "9084117332"]
   - Database has: "+91 9084117332"

4. Try:
   - Hard refresh browser (Ctrl+Shift+R)
   - Clear localStorage
   - Re-login to refresh user session
""")

client.close()
