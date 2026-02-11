from pymongo import MongoClient

# MongoDB connection
mongo_uri = "mongodb+srv://ayush_bahuguna:081281Ab@cluster0.qejklcf.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

print("Connecting to MongoDB...")
print("=" * 80)

try:
    # Connect to MongoDB
    client = MongoClient(mongo_uri)
    
    # Check Placement_Ai database (lowercase 'i')
    print("\n🔍 Checking 'Placement_Ai' database:\n")
    db = client["Placement_Ai"]
    collections = db.list_collection_names()
    
    if collections:
        print(f"Total collections: {len(collections)}\n")
        for i, collection_name in enumerate(collections, 1):
            collection = db[collection_name]
            count = collection.count_documents({})
            print(f"  {i}. {collection_name} ({count} documents)")
    else:
        print("❌ No collections found in 'Placement_Ai'")
    
    print("\n" + "=" * 80)
    
except Exception as e:
    print(f"❌ Error: {str(e)}")
    import traceback
    traceback.print_exc()
