from pymongo import MongoClient
from dotenv import load_dotenv
import os
import json

load_dotenv()

# Connect to MongoDB
mongo_uri = os.getenv('MONGODB_URI')
client = MongoClient(mongo_uri)
db = client['Placement_Ai']
collection = db['week_test']

print("=" * 80)
print("WEEK_TEST COLLECTION ANALYSIS")
print("=" * 80)

# Get total count
count = collection.count_documents({})
print(f"\n📊 Total documents: {count}")

if count > 0:
    # Get first document to see structure
    print("\n📄 Sample document structure:")
    sample = collection.find_one()
    print(json.dumps(sample, indent=2, default=str))
    
    # Get all field names
    print("\n🔑 All field names found:")
    all_keys = set()
    for doc in collection.find().limit(10):
        all_keys.update(doc.keys())
    for key in sorted(all_keys):
        print(f"  - {key}")
    
    # Count by mobile if available
    print("\n📱 Documents by mobile number:")
    pipeline = [
        {"$group": {"_id": "$mobile", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10}
    ]
    for item in collection.aggregate(pipeline):
        print(f"  {item['_id']}: {item['count']} documents")

else:
    print("\n⚠️  Collection is empty!")

print("\n" + "=" * 80)

client.close()
