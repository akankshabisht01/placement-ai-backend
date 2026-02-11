"""
Simple check of monthly_test collection structure
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

print("="*80)
print("CHECKING monthly_test COLLECTION STRUCTURE")
print("="*80)

# Check for user +91 9084117332
mobile = "+91 9084117332"
month = 1

print(f"\nUser: {mobile}, Month: {month}")
print("-"*80)

# Method 1: Search by _id pattern
test_id = f"{mobile}_month_{month}"
doc1 = monthly_test_collection.find_one({'_id': test_id})
print(f"\n1. Searching by _id = '{test_id}'")
print(f"   Result: {'✅ FOUND' if doc1 else '❌ NOT FOUND'}")

# Method 2: Search by mobile + month fields
doc2 = monthly_test_collection.find_one({"mobile": mobile, "month": {"$in": [month, str(month)]}})
print(f"\n2. Searching by mobile field = '{mobile}' AND month = {month}")
print(f"   Result: {'✅ FOUND' if doc2 else '❌ NOT FOUND'}")

if doc2:
    print(f"\n   Document found!")
    print(f"   _id field value: {doc2.get('_id')}")
    print(f"   mobile field value: {doc2.get('mobile')}")
    print(f"   month field value: {doc2.get('month')}")
    print(f"   All keys: {list(doc2.keys())}")

# Check what other users have monthly tests
print(f"\n" + "="*80)
print("ALL DOCUMENTS IN monthly_test COLLECTION")
print("="*80)

all_docs = list(monthly_test_collection.find())
print(f"Total documents: {len(all_docs)}\n")

for i, doc in enumerate(all_docs[:10], 1):
    doc_id = doc.get('_id')
    doc_mobile = doc.get('mobile')
    doc_month = doc.get('month')
    print(f"{i}. _id: {doc_id}")
    print(f"   mobile: {doc_mobile}")
    print(f"   month: {doc_month}")
    print()

client.close()
