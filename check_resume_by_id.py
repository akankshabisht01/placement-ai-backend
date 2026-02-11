"""Check resume using _id field"""
import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

mongo_uri = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
db_name = os.getenv('MONGODB_DB', 'Placement_Ai')

client = MongoClient(mongo_uri)
db = client[db_name]

mobile = "+91 8864862270"

print(f"\n{'='*80}")
print(f"CHECKING RESUME BY _id")
print(f"{'='*80}\n")

resume_col = db['Resume']
resume = resume_col.find_one({'_id': mobile})

if resume:
    print(f"✅ Resume found!")
    print(f"   _id: {resume.get('_id')}")
    print(f"   name: {resume.get('name')}")
    print(f"   skills: {resume.get('skills', [])}")
    print(f"\n   Total skills: {len(resume.get('skills', []))}")
else:
    print(f"❌ No resume found with _id: {mobile}")
    
    # List all resume _ids
    print(f"\nAll resume _ids in collection:")
    all_ids = list(resume_col.find({}, {'_id': 1}).limit(20))
    for doc in all_ids:
        print(f"  - {doc.get('_id')}")

print(f"\n{'='*80}\n")
