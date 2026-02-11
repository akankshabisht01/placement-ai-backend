"""Find the resume for user 8864862270 with different mobile formats"""
import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

mongo_uri = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
db_name = os.getenv('MONGODB_DB', 'Placement_Ai')

client = MongoClient(mongo_uri)
db = client[db_name]

mobile = "+91 8864862270"
clean_mobile = ''.join(filter(str.isdigit, mobile))

# Try different formats
formats_to_try = [
    mobile,                           # +91 8864862270
    clean_mobile,                     # 918864862270
    clean_mobile[-10:],               # 8864862270
    f"+91{clean_mobile[-10:]}",       # +918864862270
    f"+91 {clean_mobile[-10:]}",      # +91 8864862270
]

print(f"\n{'='*80}")
print(f"SEARCHING FOR RESUME WITH DIFFERENT MOBILE FORMATS")
print(f"{'='*80}\n")

resume_col = db['Resume']

for fmt in formats_to_try:
    print(f"Trying: '{fmt}'")
    resume = resume_col.find_one({'mobile': fmt})
    if resume:
        print(f"  ✅ FOUND!")
        print(f"     _id: {resume.get('_id')}")
        print(f"     mobile: {resume.get('mobile')}")
        print(f"     skills: {resume.get('skills', [])}")
        print()
        break
    else:
        print(f"  ❌ Not found")

# Also check Registration collection
print(f"\n{'='*80}")
print(f"CHECKING REGISTRATION COLLECTION")
print(f"{'='*80}\n")

reg_col = db['Registration']

for fmt in formats_to_try:
    print(f"Trying: '{fmt}'")
    reg = reg_col.find_one({'mobile': fmt})
    if reg:
        print(f"  ✅ FOUND!")
        print(f"     _id: {reg.get('_id')}")
        print(f"     mobile: {reg.get('mobile')}")
        print(f"     name: {reg.get('name')}")
        print()
        break
    else:
        print(f"  ❌ Not found")

print(f"\n{'='*80}")
print(f"LISTING ALL RESUMES (SAMPLE)")
print(f"{'='*80}\n")

all_resumes = list(resume_col.find().limit(5))
print(f"Total resumes: {resume_col.count_documents({})}\n")
print(f"Sample mobile formats in Resume collection:")
for resume in all_resumes:
    print(f"  - mobile: '{resume.get('mobile')}' | _id: {resume.get('_id')}")

print(f"\n{'='*80}\n")
