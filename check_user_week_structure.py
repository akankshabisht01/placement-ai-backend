from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

# Connect to MongoDB
mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI")
client = MongoClient(mongo_uri)
db = client[os.getenv("MONGODB_DB", "Placement_Ai")]

analysis_collection = db["Weekly_test_analysis"]

# The user who has completed 4 weeks
test_mobile = "+91 9084117332"

print(f"Checking Weekly_test_analysis structure for: {test_mobile}")
print("="*80)

# Try different search patterns
search_patterns = [
    test_mobile,
    "919084117332",
    "9084117332",
    "+919084117332"
]

for pattern in search_patterns:
    print(f"\nSearching by _id: {pattern}")
    docs_by_id = list(analysis_collection.find({'_id': pattern}))
    print(f"  Found {len(docs_by_id)} documents")
    
    print(f"Searching by mobile: {pattern}")
    docs_by_mobile = list(analysis_collection.find({'mobile': pattern}))
    print(f"  Found {len(docs_by_mobile)} documents")
    
    if docs_by_id or docs_by_mobile:
        all_docs = docs_by_id + docs_by_mobile
        print(f"\n  Document details:")
        for doc in all_docs:
            doc_id = doc.get('_id')
            mobile = doc.get('mobile')
            analysis = doc.get('analysis', {})
            week = analysis.get('week')
            month = analysis.get('month')
            print(f"    _id: {doc_id}")
            print(f"    mobile field: {mobile}")
            print(f"    week: {week}, month: {month}")
            print()

# Also get all documents to see structure
print("\n" + "="*80)
print("ALL DOCUMENTS IN Weekly_test_analysis:")
print("="*80)
all_docs = list(analysis_collection.find())
for doc in all_docs:
    doc_id = doc.get('_id')
    mobile = doc.get('mobile')
    analysis = doc.get('analysis', {})
    week = analysis.get('week')
    month = analysis.get('month')
    print(f"_id: {doc_id}, mobile: {mobile}, week: {week}, month: {month}")

client.close()
