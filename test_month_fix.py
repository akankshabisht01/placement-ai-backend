"""
Test the month eligibility logic directly without Flask
"""
from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

# Connect to MongoDB
mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI")
client = MongoClient(mongo_uri)
db = client[os.getenv("MONGODB_DB", "Placement_Ai")]

def check_month_eligibility(mobile):
    """Simulate the backend endpoint logic"""
    print(f"\n{'='*80}")
    print(f"Testing month eligibility for: {mobile}")
    print(f"{'='*80}")
    
    # Normalize mobile number
    normalized_mobile = ''.join(filter(str.isdigit, mobile))
    mobile_10 = normalized_mobile[-10:] if len(normalized_mobile) >= 10 else normalized_mobile
    
    # Build search query for multiple mobile formats
    search_ids = [mobile, normalized_mobile, mobile_10]
    if len(normalized_mobile) == 10:
        search_ids.extend([
            f"91{normalized_mobile}", 
            f"+91{normalized_mobile}",
            f"+91 {mobile_10}"  # Add format with space after +91
        ])
    
    print(f"Search patterns: {search_ids}")
    
    analysis_collection = db['Weekly_test_analysis']
    monthly_result_collection = db['monthly_test_result']
    
    # OLD LOGIC (BUGGY):
    print(f"\n--- OLD LOGIC (searching by _id first) ---")
    completed_tests_old = []
    for search_id in search_ids:
        found_docs = list(analysis_collection.find({'_id': search_id}))
        if found_docs:
            print(f"Found {len(found_docs)} docs by _id: {search_id}")
            completed_tests_old.extend(found_docs)
            break
    
    if not completed_tests_old:
        for search_id in search_ids:
            found_docs = list(analysis_collection.find({'mobile': search_id}))
            if found_docs:
                print(f"Found {len(found_docs)} docs by mobile: {search_id}")
                completed_tests_old.extend(found_docs)
                break
    
    print(f"OLD LOGIC: Found {len(completed_tests_old)} completed tests")
    
    # NEW LOGIC (FIXED):
    print(f"\n--- NEW LOGIC (searching by mobile field) ---")
    completed_tests_new = []
    for search_id in search_ids:
        found_docs = list(analysis_collection.find({'mobile': search_id}))
        if found_docs:
            print(f"Found {len(found_docs)} docs by mobile: {search_id}")
            completed_tests_new.extend(found_docs)
            break
    
    print(f"NEW LOGIC: Found {len(completed_tests_new)} completed tests")
    
    # Process with new logic
    if completed_tests_new:
        weeks_completed = []
        for doc in completed_tests_new:
            analysis = doc.get('analysis', {})
            week = analysis.get('week')
            if week and week not in weeks_completed:
                weeks_completed.append(week)
        
        weeks_completed.sort()
        print(f"Weeks completed: {weeks_completed}")
        
        # Check Month 1 eligibility
        expected_weeks = [1, 2, 3, 4]
        all_weeks_completed = weeks_completed == expected_weeks
        
        print(f"\nMonth 1 eligibility:")
        print(f"  Expected weeks: {expected_weeks}")
        print(f"  Actual weeks: {weeks_completed}")
        print(f"  All weeks completed: {all_weeks_completed}")
        
        if all_weeks_completed:
            print(f"  ✅ MONTH 1 IS UNLOCKED!")
        else:
            print(f"  ❌ Month 1 is locked (missing weeks)")
    else:
        print(f"❌ No weekly tests found")
    
    print(f"{'='*80}\n")

# Test with the problematic user
check_month_eligibility("+91 9084117332")
check_month_eligibility("9084117332")

client.close()
