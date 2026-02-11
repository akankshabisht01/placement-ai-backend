"""List all collections in Placement_Ai database"""
import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

mongo_uri = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
db_name = os.getenv('MONGODB_DB', 'Placement_Ai')

client = MongoClient(mongo_uri)
db = client[db_name]

print(f"\n{'='*80}")
print(f"ALL COLLECTIONS IN '{db_name}' DATABASE")
print(f"{'='*80}\n")

collections = db.list_collection_names()

for col_name in sorted(collections):
    count = db[col_name].count_documents({})
    print(f"  {col_name:<40} ({count} documents)")

print(f"\n{'='*80}")

# Check if there's any collection with "roadmap" in the name
roadmap_collections = [c for c in collections if 'roadmap' in c.lower()]
if roadmap_collections:
    print(f"\nCollections containing 'roadmap':")
    for col in roadmap_collections:
        count = db[col].count_documents({})
        print(f"  - {col} ({count} documents)")
        
        if count > 0:
            sample = db[col].find_one()
            print(f"    Sample keys: {list(sample.keys())[:10]}")

print(f"\n{'='*80}\n")
