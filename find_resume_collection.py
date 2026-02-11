from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

mongo_uri = os.getenv('MONGO_URI') or os.getenv('MONGODB_URI')
client = MongoClient(mongo_uri)
db = client[os.getenv("MONGODB_DB", "Placement_Ai")]

# Try different collection names
collection_variations = ['Resume', 'Resume ', ' Resume', 'resume']

print("\n" + "="*80)
print("FINDING RESUME COLLECTION AND JOB SELECTION")
print("="*80)

for col_name in collection_variations:
    col = db[col_name]
    count = col.count_documents({})
    print(f"\n'{col_name}' ({len(col_name)} chars): {count} documents")
    
    if count > 0:
        # This is the right collection!
        print(f"   ✅ FOUND THE COLLECTION!")
        
        # Check first few documents
        docs = list(col.find().limit(3))
        for doc in docs:
            has_job = 'jobSelection' in doc
            job_role = doc.get('jobSelection', {}).get('jobRole') if has_job else None
            print(f"      _id: {doc['_id']:20s} | jobSelection: {has_job}")
            if has_job:
                print(f"         jobRole: {job_role}")
        
        # Check for user 8864862270
        print(f"\n   🔍 Looking for user 8864862270:")
        mobile_formats = ['+91 8864862270', '+918864862270', '8864862270', '918864862270']
        for fmt in mobile_formats:
            user = col.find_one({'_id': fmt})
            if user:
                print(f"      ✅ Found with _id: '{fmt}'")
                has_job = 'jobSelection' in user
                print(f"         Has jobSelection: {has_job}")
                if has_job:
                    import json
                    print(f"         jobSelection: {json.dumps(user['jobSelection'], indent=12)}")
                else:
                    print(f"         Available fields: {list(user.keys())}")
                break

print("\n" + "="*80)
