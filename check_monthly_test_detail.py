from pymongo import MongoClient
import json

# MongoDB connection
mongo_uri = "mongodb+srv://ayush_bahuguna:081281Ab@cluster0.qejklcf.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

print("Connecting to MongoDB...")

try:
    client = MongoClient(mongo_uri)
    db = client["Placement_Ai"]
    collection = db["monthly_test"]
    
    # Get all documents
    documents = list(collection.find({}))
    
    print(f"\n📊 monthly_test collection - {len(documents)} documents found:\n")
    
    for i, doc in enumerate(documents, 1):
        print(f"\n--- Document {i} ---")
        print(f"Mobile: {doc.get('mobile')}")
        print(f"Month: {doc.get('month')}")
        print(f"Test Title: {doc.get('test_title')}")
        print(f"Status: {doc.get('status')}")
        print(f"Generated At: {doc.get('generated_at')}")
        print(f"_id: {doc.get('_id')}")
        print("-" * 80)
    
except Exception as e:
    print(f"❌ Error: {str(e)}")
    import traceback
    traceback.print_exc()
