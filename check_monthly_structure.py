from pymongo import MongoClient
import json

# MongoDB connection
mongo_uri = "mongodb+srv://ayush_bahuguna:081281Ab@cluster0.qejklcf.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

print("Connecting to MongoDB...")

try:
    client = MongoClient(mongo_uri)
    db = client["Placement_Ai"]
    collection = db["monthly_test"]
    
    # Get one document to see full structure
    doc = collection.find_one({})
    
    if doc:
        print("\n📊 Full structure of monthly_test document:\n")
        print("Top-level keys:", list(doc.keys()))
        print("\nFull document (first 2000 chars):")
        doc['_id'] = str(doc['_id'])
        print(json.dumps(doc, indent=2, default=str)[:2000])
    
except Exception as e:
    print(f"❌ Error: {str(e)}")
    import traceback
    traceback.print_exc()
