"""
Test the fixed monthly test detection logic
"""
from pymongo import MongoClient
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

# Connect to MongoDB
mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI")
client = MongoClient(mongo_uri)
db = client[os.getenv("MONGODB_DB", "Placement_Ai")]

monthly_test_collection = db["monthly_test"]
result_collection = db["monthly_test_result"]

def simulate_monthly_test_status(mobile, month):
    """
    Simulate the FIXED backend endpoint logic
    """
    print(f"\n{'='*80}")
    print(f"SIMULATING FIXED /api/monthly-test-status ENDPOINT")
    print(f"{'='*80}")
    print(f"Mobile: {mobile}")
    print(f"Month: {month}")
    print(f"{'='*80}\n")
    
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
    
    print(f"Search patterns: {search_ids}\n")
    
    # NEW FIXED LOGIC: Search by mobile + month fields first
    test_doc = None
    test_id = None
    
    print("Step 1: Search by mobile field + month field (N8N format)")
    for search_id in search_ids:
        print(f"  Trying mobile: {search_id}")
        test_doc = monthly_test_collection.find_one({"mobile": search_id, "month": {"$in": [month, str(month)]}})
        if test_doc:
            test_id = str(test_doc.get('_id'))
            print(f"  ✅ FOUND! _id: {test_id}")
            break
        else:
            print(f"  ❌ Not found")
    
    # Fallback to old format
    if not test_doc:
        print("\nStep 2: Fallback - Search by _id pattern (old format)")
        for search_id in search_ids:
            test_id_variant = f"{search_id}_month_{month}"
            print(f"  Trying _id: {test_id_variant}")
            test_doc = monthly_test_collection.find_one({'_id': test_id_variant})
            if test_doc:
                test_id = test_id_variant
                print(f"  ✅ FOUND!")
                break
            else:
                print(f"  ❌ Not found")
    
    test_generated = test_doc is not None
    
    print(f"\n--- RESULTS ---")
    print(f"test_generated: {test_generated}")
    
    if test_generated:
        print(f"test_id: {test_id}")
        
        # Check timestamp
        test_generated_at = (
            test_doc.get('createdAt') or 
            test_doc.get('timestamp') or 
            test_doc.get('created_at')
        )
        print(f"test_generated_at: {test_generated_at}")
        
        # Check if completed
        result_id = f"{mobile}_month_{month}"
        result_doc = result_collection.find_one({'_id': result_id})
        
        if not result_doc:
            for search_id in search_ids:
                result_id_variant = f"{search_id}_month_{month}"
                result_doc = result_collection.find_one({'_id': result_id_variant})
                if result_doc:
                    break
        
        test_completed = result_doc is not None
        print(f"test_completed: {test_completed}")
        
        # Calculate timer
        if test_generated_at:
            print(f"Has timestamp - calculating elapsed time...")
            timer_remaining = 0
            can_start_test = True
        else:
            print(f"No timestamp - starting 5-minute timer...")
            timer_remaining = 300
            can_start_test = False
        
        print(f"can_start_test: {can_start_test}")
        print(f"timer_remaining: {timer_remaining}")
        
        print(f"\n✅ FRONTEND SHOULD SHOW:")
        if test_completed:
            print(f"   'Monthly Test Analysis' button")
        elif not can_start_test and timer_remaining > 0:
            print(f"   Timer countdown: {timer_remaining} seconds")
        elif can_start_test:
            print(f"   'Start Monthly Test' button")
    else:
        print(f"\n❌ TEST NOT FOUND")
        print(f"FRONTEND SHOULD SHOW:")
        print(f"   'Generate Month {month} Test' button")
    
    print(f"{'='*80}\n")

# Test with users who have completed 4 weeks
test_users = [
    ("+91 9084117332", 1),
    ("9084117332", 1),
    ("+91 9346333208", 1),
]

for mobile, month in test_users:
    simulate_monthly_test_status(mobile, month)

client.close()
