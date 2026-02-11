"""Check Roadmap_Dashboard collection structure"""
import os
import json
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

# Get MongoDB connection
mongo_uri = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
db_name = os.getenv('MONGODB_DB', 'Placement_Ai')

client = MongoClient(mongo_uri)
db = client[db_name]

# Get Roadmap_Dashboard collection (Note: has trailing space)
roadmap_col = db['Roadmap_Dashboard ']
count = roadmap_col.count_documents({})

print(f"\n{'='*80}")
print(f"ROADMAP_DASHBOARD COLLECTION")
print(f"{'='*80}")
print(f"Total documents: {count}\n")

if count > 0:
    # Get a sample document
    sample = roadmap_col.find_one()
    
    print(f"Sample User ID: {sample.get('_id')}")
    print(f"\nDocument Keys: {list(sample.keys())}\n")
    
    # Check structure
    print("Document Structure:")
    print("-" * 80)
    
    for key, value in sample.items():
        if key == '_id':
            print(f"  {key}: {value}")
        elif isinstance(value, dict):
            print(f"  {key}: (dict with {len(value)} keys)")
            if len(value) <= 5:
                for sub_key in value.keys():
                    print(f"    - {sub_key}")
        elif isinstance(value, list):
            print(f"  {key}: (list with {len(value)} items)")
            if len(value) > 0:
                print(f"    First item type: {type(value[0])}")
        else:
            print(f"  {key}: {type(value).__name__}")
    
    print("\n" + "-" * 80)
    print("\nFull Sample Document (formatted):")
    print("-" * 80)
    print(json.dumps(sample, indent=2, default=str)[:2000] + "...")
    
else:
    print("⚠️ Roadmap_Dashboard collection is empty!")

print("\n" + "="*80)
