"""Check current state of resume in database"""
import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

mongo_uri = os.getenv('MONGO_URI') or os.getenv('MONGODB_URI')
client = MongoClient(mongo_uri)
db = client[os.getenv("MONGODB_DB", "Placement_Ai")]

resume_col = db['Resume']

# Find the resume
mobile_formats = [
    "+91 8864862270",
    "+918864862270",
    "8864862270",
]

print("\n" + "="*80)
print("CHECKING CURRENT RESUME STATE IN DATABASE")
print("="*80 + "\n")

resume_doc = None
for variant in mobile_formats:
    resume_doc = resume_col.find_one({'_id': variant})
    if resume_doc:
        print(f"✅ Found resume with _id: '{variant}'")
        break

if resume_doc:
    print(f"\n📄 Full Resume Document:")
    print(f"   _id: {resume_doc.get('_id')}")
    print(f"   name: {resume_doc.get('name')}")
    
    skills = resume_doc.get('skills', [])
    print(f"\n📊 Skills array ({len(skills)} total):")
    for i, skill in enumerate(skills, 1):
        print(f"   {i}. '{skill}' (type: {type(skill).__name__}, length: {len(skill)})")
    
    print(f"\n📋 Raw skills array: {skills}")
    
    # Check other fields that might affect display
    if 'skillsToLearn' in resume_doc:
        print(f"\n🎯 Skills To Learn: {resume_doc.get('skillsToLearn')}")
    
    if 'skills_to_develop' in resume_doc:
        print(f"\n📚 Skills To Develop: {resume_doc.get('skills_to_develop')}")
        
else:
    print("❌ Resume not found!")
    print(f"   Tried formats: {mobile_formats}")
    
    # Try searching by any field containing the mobile
    print("\n🔍 Searching for any resume with this mobile...")
    all_resumes = resume_col.find({})
    for resume in all_resumes:
        resume_id = resume.get('_id', '')
        if '8864862270' in str(resume_id):
            print(f"   Found: {resume_id}")
            print(f"   Skills: {resume.get('skills', [])}")

print("\n" + "="*80 + "\n")
