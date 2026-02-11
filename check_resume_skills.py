"""
Check what skills are in the user's resume
"""
import os
from pymongo import MongoClient
from dotenv import load_dotenv
import json

load_dotenv()

mongo_uri = os.getenv('MONGODB_URI')
db = MongoClient(mongo_uri)[os.getenv('MONGODB_DB', 'Placement_Ai')]

mobile = "+91 8864862270"

# Try different mobile formats
mobile_formats = [
    mobile,
    mobile.replace(' ', ''),
    mobile.replace('+', ''),
    '8864862270',
    '+918864862270'
]

print("Checking Resume collection for skills...")
print("="*80)

resume_col = db['Resume']

for variant in mobile_formats:
    doc = resume_col.find_one({'_id': variant})
    if doc:
        print(f"\n✅ Found resume with _id: {variant}")
        print(f"\nSkills in resume:")
        skills = doc.get('skills', [])
        if skills:
            for i, skill in enumerate(skills, 1):
                print(f"  {i}. {skill}")
        else:
            print("  ❌ No skills found (empty array)")
        
        print(f"\nOther resume fields:")
        print(f"  - Name: {doc.get('name')}")
        print(f"  - Email: {doc.get('email')}")
        print(f"  - Job Role: {doc.get('jobRole')}")
        print(f"  - Job Domain: {doc.get('jobDomain')}")
        
        print(f"\nAll fields in resume: {list(doc.keys())}")
        break
else:
    print("❌ No resume found with any mobile format")
    print(f"Tried: {mobile_formats}")
