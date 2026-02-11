from pymongo import MongoClient
import json

client = MongoClient('mongodb://localhost:27017/')

print("\n" + "="*80)
print("CHECKING SKILL_WEEK_MAPPING ACROSS ALL DATABASES")
print("="*80)

# Check all databases
for db_name in client.list_database_names():
    if db_name not in ['admin', 'local', 'config']:
        db = client[db_name]
        collections = db.list_collection_names()
        
        if 'skill_week_mapping' in collections:
            print(f"\n✅ Found skill_week_mapping in database: {db_name}")
            
            mappings = list(db['skill_week_mapping'].find())
            print(f"   Total documents: {len(mappings)}")
            
            for mapping in mappings:
                print(f"\n   User ID: {mapping.get('_id')}")
                
                # Show all months
                for key, value in mapping.items():
                    if key.startswith('month_') and isinstance(value, dict):
                        print(f"\n   {key}:")
                        for skill, weeks in value.items():
                            print(f"      {skill}: {weeks}")

print("\n" + "="*80)
print("CHECKING PLACEMENT_AI DATABASE COLLECTIONS")
print("="*80)

db = client['Placement_Ai']
collections = db.list_collection_names()
print(f"\nCollections in Placement_Ai: {collections}")

if 'skill_week_mapping' in collections:
    mappings = list(db['skill_week_mapping'].find())
    print(f"\nDocuments in skill_week_mapping: {len(mappings)}")
else:
    print("\n❌ skill_week_mapping collection does not exist yet")
    print("   It will be created when you:")
    print("   1. View your roadmap page, OR")
    print("   2. Click 'Refresh Stars' button")
