from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()

client = MongoClient(os.getenv('MONGODB_URI'))
db = client['Placement_Ai']
collection = db['week_test_result']

print("=" * 100)
print("Checking current week_test_result documents")
print("=" * 100)

# Find all documents
docs = list(collection.find({}))

print(f"\nTotal documents: {len(docs)}\n")

for doc in docs:
    _id = doc.get('_id')
    mobile = doc.get('mobile')
    week = doc.get('week')
    month = doc.get('month')
    
    print(f"{'='*100}")
    print(f"_id: {_id}")
    print(f"Mobile: {mobile}")
    print(f"Week: {week}, Month: {month}")
    print(f"TestType: {doc.get('testType', 'N/A')}")
    print(f"SavedAt: {doc.get('savedAt', 'N/A')}")

print("\n" + "=" * 100)
