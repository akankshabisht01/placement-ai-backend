from pymongo import MongoClient
import os
from dotenv import load_dotenv
import json

load_dotenv()

client = MongoClient(os.getenv('MONGODB_URI'))
db = client['Placement_Ai']

print("=" * 80)
print("PLACEMENT_AI DATABASE - ALL COLLECTIONS")
print("=" * 80)

collection_names = sorted(db.list_collection_names())
print(f"\nTotal Collections: {len(collection_names)}\n")

for idx, coll_name in enumerate(collection_names, 1):
    collection = db[coll_name]
    count = collection.count_documents({})
    
    print(f"\n{idx}. {coll_name}")
    print(f"   Documents: {count}")
    
    if count > 0:
        # Get one sample document
        sample = collection.find_one()
        if sample:
            # Show _id and a few key fields
            print(f"   Sample _id: {sample.get('_id')}")
            
            # Show relevant fields based on collection name
            if 'mobile' in sample:
                print(f"   Sample mobile: {sample.get('mobile')}")
            if 'analysis' in sample:
                analysis = sample.get('analysis', {})
                if isinstance(analysis, dict):
                    week = analysis.get('week')
                    month = analysis.get('month')
                    if week:
                        print(f"   Sample week: {week}, month: {month}")
            if 'week' in sample and 'month' in sample:
                print(f"   Sample week: {sample.get('week')}, month: {sample.get('month')}")
            if 'month' in sample:
                print(f"   Sample month: {sample.get('month')}")
    else:
        print(f"   (Empty)")

print("\n" + "=" * 80)
print("SPECIFIC COLLECTIONS OF INTEREST:")
print("=" * 80)

# Check Weekly_test_analysis
print("\n📊 Weekly_test_analysis:")
weekly_analysis = list(db['Weekly_test_analysis'].find())
if weekly_analysis:
    print(f"   Total: {len(weekly_analysis)} documents")
    for doc in weekly_analysis:
        mobile = doc.get('mobile')
        analysis = doc.get('analysis', {})
        week = analysis.get('week') if isinstance(analysis, dict) else None
        month = analysis.get('month') if isinstance(analysis, dict) else None
        print(f"   - {doc.get('_id')}: mobile={mobile}, week={week}, month={month}")
else:
    print("   (Empty - No weekly analyses)")

# Check monthly_test_result
print("\n📅 monthly_test_result:")
monthly_results = list(db['monthly_test_result'].find())
if monthly_results:
    print(f"   Total: {len(monthly_results)} documents")
    for doc in monthly_results:
        mobile = doc.get('mobile')
        month = doc.get('month')
        percentage = doc.get('percentage', 0)
        print(f"   - {doc.get('_id')}: mobile={mobile}, month={month}, score={percentage}%")
else:
    print("   (Empty - No monthly test results)")

# Check monthly_test_analysis
print("\n📈 monthly_test_analysis:")
monthly_analysis = list(db['monthly_test_analysis'].find())
if monthly_analysis:
    print(f"   Total: {len(monthly_analysis)} documents")
    for doc in monthly_analysis:
        mobile = doc.get('mobile')
        month = doc.get('month')
        print(f"   - {doc.get('_id')}: mobile={mobile}, month={month}")
else:
    print("   (Empty - No monthly analyses)")

print("\n" + "=" * 80)
