from pymongo import MongoClient
import os
import json
from dotenv import load_dotenv

load_dotenv()

mongo_uri = os.getenv('MONGO_URI') or os.getenv('MONGODB_URI')
client = MongoClient(mongo_uri)
db = client[os.getenv("MONGODB_DB", "Placement_Ai")]

resume_col = db['Resume']

print("\n" + "="*80)
print("RESUME COLLECTION STRUCTURE")
print("="*80)

total = resume_col.count_documents({})
print(f"\nTotal documents: {total}")

# Get all unique fields across all documents
all_fields = set()
for doc in resume_col.find():
    all_fields.update(doc.keys())

print(f"\n📋 All fields found in Resume collection:")
for field in sorted(all_fields):
    print(f"   - {field}")

# Show your specific resume
print(f"\n" + "="*80)
print("YOUR RESUME (8864862270)")
print("="*80)

mobile_formats = ['+91 8864862270', '+918864862270', '8864862270']
resume = None
for fmt in mobile_formats:
    resume = resume_col.find_one({'_id': fmt})
    if resume:
        print(f"\n✅ Found with _id: '{resume['_id']}'")
        break

if resume:
    print(f"\n📄 Full Document Structure:")
    print(json.dumps(resume, indent=2, default=str))
else:
    print(f"\n❌ Resume not found")

print("\n" + "="*80)
