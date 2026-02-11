from pymongo import MongoClient

client = MongoClient('mongodb://localhost:27017/')

print("\n" + "="*80)
print("ALL DATABASES AND THEIR COLLECTIONS")
print("="*80)

for db_name in client.list_database_names():
    if db_name not in ['admin', 'local', 'config']:
        db = client[db_name]
        collections = db.list_collection_names()
        
        print(f"\n📁 Database: {db_name}")
        print(f"   Collections ({len(collections)}):")
        
        for col in sorted(collections):
            count = db[col].count_documents({})
            print(f"      - {col} ({count} documents)")

print("\n" + "="*80)
