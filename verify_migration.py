from pymongo import MongoClient
from dotenv import load_dotenv
import os
import json

load_dotenv()

client = MongoClient(os.getenv('MONGODB_URI'))
db = client['Placement_Ai']

print("=" * 100)
print("VERIFICATION: week_test_answers and week_test_result collections")
print("=" * 100)

for collection_name in ['week_test_answers', 'week_test_result']:
    print(f"\n{'='*100}")
    print(f"Collection: {collection_name}")
    print(f"{'='*100}")
    
    collection = db[collection_name]
    docs = list(collection.find({}))
    
    print(f"Total Documents: {len(docs)}")
    print(f"\n📋 All _id values:")
    
    for doc in docs:
        _id = doc['_id']
        week = doc.get('week', 'N/A')
        mobile = doc.get('mobile', 'N/A')
        print(f"  - _id: {_id}")
        print(f"    Week: {week}")
        print(f"    Mobile: {mobile}")
        print()

print("=" * 100)
