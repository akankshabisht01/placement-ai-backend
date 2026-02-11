from pymongo import MongoClient
import json

# MongoDB connection
mongo_uri = "mongodb+srv://ayush_bahuguna:081281Ab@cluster0.qejklcf.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

print("Connecting to MongoDB...")
print("=" * 80)

try:
    # Connect to MongoDB
    client = MongoClient(mongo_uri)
    db = client["Placement_Ai"]
    collection = db["monthly_test"]
    
    # Get all documents
    documents = list(collection.find({}))
    
    print(f"\n📊 monthly_test collection - {len(documents)} documents found:\n")
    print("=" * 80)
    
    for i, doc in enumerate(documents, 1):
        print(f"\n--- Document {i} ---")
        # Convert ObjectId to string for better display
        if '_id' in doc:
            doc['_id'] = str(doc['_id'])
        print(json.dumps(doc, indent=2, default=str))
        print("-" * 80)
    
    if not documents:
        print("❌ No documents found in monthly_test collection")
    
except Exception as e:
    print(f"❌ Error: {str(e)}")
    import traceback
    traceback.print_exc()
