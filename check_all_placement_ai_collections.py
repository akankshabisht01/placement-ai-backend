from pymongo import MongoClient
from dotenv import load_dotenv
import os
import json
from datetime import datetime

load_dotenv()

# Connect to MongoDB
mongo_uri = os.getenv('MONGODB_URI')
if not mongo_uri:
    print("❌ MONGODB_URI not found in .env file")
    exit(1)

client = MongoClient(mongo_uri)
db = client['Placement_Ai']

print("=" * 100)
print("PLACEMENT_AI DATABASE - ALL COLLECTIONS ANALYSIS")
print("=" * 100)
print(f"Database: Placement_Ai")
print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 100)

# Get all collection names
collection_names = db.list_collection_names()
print(f"\n📊 Total Collections: {len(collection_names)}\n")

# Analyze each collection
for idx, collection_name in enumerate(sorted(collection_names), 1):
    print(f"\n{'='*100}")
    print(f"{idx}. COLLECTION: {collection_name}")
    print(f"{'='*100}")
    
    collection = db[collection_name]
    
    # Get document count
    count = collection.count_documents({})
    print(f"📈 Total Documents: {count}")
    
    if count > 0:
        # Get a sample document
        sample = collection.find_one()
        
        # Get all unique field names from first 10 documents
        all_keys = set()
        for doc in collection.find().limit(10):
            all_keys.update(doc.keys())
        
        print(f"\n🔑 Fields ({len(all_keys)}):")
        for key in sorted(all_keys):
            # Show sample value type
            if key in sample:
                value = sample[key]
                value_type = type(value).__name__
                if isinstance(value, str):
                    value_preview = value[:50] + "..." if len(value) > 50 else value
                elif isinstance(value, (list, dict)):
                    value_preview = f"{len(value)} items" if isinstance(value, list) else f"{len(value)} keys"
                else:
                    value_preview = str(value)[:50]
                print(f"  - {key:30s} ({value_type:15s}): {value_preview}")
            else:
                print(f"  - {key:30s}")
        
        # Show _id format examples
        print(f"\n📋 Sample _id values:")
        sample_ids = collection.find().limit(5)
        for doc in sample_ids:
            print(f"  - {doc.get('_id')}")
        
        # Check if there are week-related fields
        week_related = [k for k in all_keys if 'week' in k.lower()]
        if week_related:
            print(f"\n📅 Week-related fields: {', '.join(week_related)}")
        
        # Show sample document structure (condensed)
        print(f"\n📄 Sample Document Structure:")
        print(json.dumps(sample, indent=2, default=str, ensure_ascii=False)[:1000] + "...")
    else:
        print("⚠️  Collection is empty")
    
    print(f"\n{'='*100}\n")

print("\n" + "=" * 100)
print("SUMMARY")
print("=" * 100)
print(f"Total Collections: {len(collection_names)}")
print(f"Collections: {', '.join(sorted(collection_names))}")
print("=" * 100)
