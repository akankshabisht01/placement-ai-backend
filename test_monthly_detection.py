"""
Comprehensive test of monthly test detection logic
Tests both the endpoint logic and database queries
"""
from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

# Connect to MongoDB
mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI")
client = MongoClient(mongo_uri)
db = client[os.getenv("MONGODB_DB", "Placement_Ai")]

monthly_test_collection = db["monthly_test"]
result_collection = db["monthly_test_result"]

def test_monthly_test_detection(mobile, month):
    """
    Simulate the backend endpoint logic for checking if monthly test exists
    """
    print(f"\n{'='*80}")
    print(f"TESTING MONTHLY TEST DETECTION")
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
    
    print(f"Search patterns to try:")
    for i, sid in enumerate(search_ids, 1):
        print(f"  {i}. {sid}")
    
    print(f"\n--- CHECKING monthly_test COLLECTION ---")
    
    # Method 1: Check by _id pattern (used in /api/monthly-test-status)
    print(f"\nMethod 1: Search by _id = 'mobile_month_X'")
    test_id = f"{mobile}_month_{month}"
    test_doc = monthly_test_collection.find_one({'_id': test_id})
    print(f"  Searching for _id: {test_id}")
    print(f"  Result: {'✅ FOUND' if test_doc else '❌ NOT FOUND'}")
    
    # Try with other mobile formats
    found_with_format = None
    if not test_doc:
        print(f"\n  Trying alternative mobile formats...")
        for search_id in search_ids:
            test_id_variant = f"{search_id}_month_{month}"
            print(f"    Trying _id: {test_id_variant}")
            test_doc = monthly_test_collection.find_one({'_id': test_id_variant})
            if test_doc:
                print(f"    ✅ FOUND with format: {search_id}")
                found_with_format = search_id
                test_id = test_id_variant
                break
            else:
                print(f"    ❌ Not found")
    
    # Method 2: Check by mobile field (used in monthly_test_fetcher)
    print(f"\nMethod 2: Search by mobile field + month field")
    test_doc_v2 = monthly_test_collection.find_one({"mobile": mobile, "month": {"$in": [month, str(month)]}})
    print(f"  Searching for mobile: {mobile}, month: {month}")
    print(f"  Result: {'✅ FOUND' if test_doc_v2 else '❌ NOT FOUND'}")
    
    # Try with alternative formats
    if not test_doc_v2:
        print(f"\n  Trying alternative mobile formats...")
        for search_id in search_ids:
            print(f"    Trying mobile: {search_id}")
            test_doc_v2 = monthly_test_collection.find_one({"mobile": search_id, "month": {"$in": [month, str(month)]}})
            if test_doc_v2:
                print(f"    ✅ FOUND with format: {search_id}")
                break
            else:
                print(f"    ❌ Not found")
    
    # Show what actually exists in the database
    print(f"\n--- ACTUAL DATABASE CONTENTS ---")
    print(f"Searching for ANY document with mobile patterns...")
    
    all_matching_docs = []
    for search_id in search_ids:
        # Check by _id pattern
        pattern_docs = list(monthly_test_collection.find({'_id': {'$regex': f'^{search_id}'}}))
        # Check by mobile field
        mobile_docs = list(monthly_test_collection.find({'mobile': search_id}))
        all_matching_docs.extend(pattern_docs)
        all_matching_docs.extend(mobile_docs)
    
    # Remove duplicates
    seen_ids = set()
    unique_docs = []
    for doc in all_matching_docs:
        doc_id = str(doc.get('_id'))
        if doc_id not in seen_ids:
            seen_ids.add(doc_id)
            unique_docs.append(doc)
    
    if unique_docs:
        print(f"\nFound {len(unique_docs)} document(s) in monthly_test collection:")
        for doc in unique_docs:
            doc_id = doc.get('_id')
            doc_mobile = doc.get('mobile')
            doc_month = doc.get('month')
            doc_keys = list(doc.keys())
            print(f"\n  Document:")
            print(f"    _id: {doc_id}")
            print(f"    mobile field: {doc_mobile}")
            print(f"    month field: {doc_month}")
            print(f"    Available keys: {doc_keys}")
            
            # Check timestamps
            has_timestamp = False
            if doc.get('createdAt'):
                print(f"    createdAt: {doc.get('createdAt')}")
                has_timestamp = True
            if doc.get('timestamp'):
                print(f"    timestamp: {doc.get('timestamp')}")
                has_timestamp = True
            if doc.get('created_at'):
                print(f"    created_at: {doc.get('created_at')}")
                has_timestamp = True
            if not has_timestamp:
                print(f"    ⚠️ NO TIMESTAMP FIELDS FOUND")
    else:
        print(f"\n❌ NO documents found for any mobile format")
        print(f"\nLet me list ALL documents in monthly_test collection:")
        all_docs = list(monthly_test_collection.find())
        print(f"Total documents: {len(all_docs)}")
        for doc in all_docs[:10]:  # Show first 10
            print(f"  _id: {doc.get('_id')}, mobile: {doc.get('mobile')}, month: {doc.get('month')}")
    
    # Check test results
    print(f"\n--- CHECKING monthly_test_result COLLECTION ---")
    result_id = f"{mobile}_month_{month}"
    result_doc = result_collection.find_one({'_id': result_id})
    print(f"Searching for _id: {result_id}")
    print(f"Result: {'✅ FOUND' if result_doc else '❌ NOT FOUND'}")
    
    if not result_doc:
        print(f"\nTrying alternative formats...")
        for search_id in search_ids:
            result_id_variant = f"{search_id}_month_{month}"
            print(f"  Trying _id: {result_id_variant}")
            result_doc = result_collection.find_one({'_id': result_id_variant})
            if result_doc:
                print(f"  ✅ FOUND")
                if result_doc.get('percentage'):
                    print(f"  Score: {result_doc.get('percentage')}%")
                break
    
    # SUMMARY
    print(f"\n{'='*80}")
    print(f"DETECTION SUMMARY")
    print(f"{'='*80}")
    test_exists = test_doc is not None or test_doc_v2 is not None
    result_exists = result_doc is not None
    
    print(f"Monthly test exists: {'✅ YES' if test_exists else '❌ NO'}")
    print(f"Test result exists: {'✅ YES' if result_exists else '❌ NO'}")
    
    if test_exists:
        print(f"\n✅ Backend should show:")
        if result_exists:
            print(f"   - 'Monthly Test Analysis' button (test completed)")
        else:
            print(f"   - Timer (if < 5 min since generation) OR")
            print(f"   - 'Start Monthly Test' button (if timer ended)")
    else:
        print(f"\n❌ Backend should show:")
        print(f"   - 'Generate Month {month} Test' button")
    
    print(f"{'='*80}\n")

# Test with different users
print("\n" + "="*80)
print("TESTING MULTIPLE USERS")
print("="*80)

test_cases = [
    ("+91 9084117332", 1),  # User who completed 4 weeks
    ("+91 9346333208", 1),  # User who has test and result
    ("9084117332", 1),      # Same user, different format
]

for mobile, month in test_cases:
    test_monthly_test_detection(mobile, month)

client.close()
