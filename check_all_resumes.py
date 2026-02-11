import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

# MongoDB connection
mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
client = MongoClient(mongo_uri)
db = client['placement_prediction']

# Find ALL resumes
print("\n=== ALL RESUMES IN DATABASE ===")
resumes = list(db['Resume'].find({}, {'mobile': 1, 'name': 1, 'jobSelection': 1, 'skills': 1}))

print(f"Total resumes found: {len(resumes)}")
for resume in resumes:
    print(f"\nMobile: '{resume.get('mobile', 'N/A')}'")
    print(f"Name: {resume.get('name', 'N/A')}")
    job_sel = resume.get('jobSelection', {})
    if job_sel:
        print(f"Job Domain: {job_sel.get('jobDomain', 'N/A')}")
        print(f"Job Role: {job_sel.get('jobRole', 'N/A')}")
        print(f"Selected Skills: {job_sel.get('selectedSkills', [])}")
    print(f"Resume Skills: {resume.get('skills', [])}")
