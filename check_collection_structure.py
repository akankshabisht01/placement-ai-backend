from pymongo import MongoClient
import json

# Connect to MongoDB
client = MongoClient('mongodb://localhost:27017/')
db = client['Placement_Ai']

print("="*100)
print("Checking all collections and week_test structure")
print("="*100)

# List all collections
collections = db.list_collection_names()
print(f"\nAll collections: {collections}\n")

# Check week_test collection
week_test_collection = db['week_test']
count = week_test_collection.count_documents({})
print(f"week_test collection has {count} documents\n")

# Get a sample document
sample = week_test_collection.find_one({})
if sample:
    print("Sample document structure:")
    print(json.dumps(sample, indent=2, default=str))
else:
    print("No documents found in week_test collection")

print("\n" + "="*100)
