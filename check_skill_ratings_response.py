import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

# MongoDB connection - Use correct database name
mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
db_name = os.getenv('MONGODB_DB', 'Placement_Ai')
client = MongoClient(mongo_uri)
db = client[db_name]

print(f"Using database: {db_name}")

# Use the correct mobile format that matches the resume _id
mobile = "+91 8864862270"

# Check Resume
resume = db['Resume'].find_one({'_id': mobile})
print("\n=== RESUME DATA ===")
if resume:
    print(f"Found Resume with _id: {mobile}")
    print(f"Job Selection: {resume.get('jobSelection', {})}")
    print(f"Job Role: {resume.get('jobSelection', {}).get('jobRole', 'N/A')}")
    print(f"Skills in Resume: {resume.get('skills', [])}")
    print(f"Selected Skills: {resume.get('jobSelection', {}).get('selectedSkills', [])}")
else:
    print(f"No resume found with _id: {mobile}")

# Simulate what the API does
print("\n=== SIMULATING /api/skill-ratings RESPONSE ===")
job_role = resume.get('jobSelection', {}).get('jobRole', '') if resume else ''
print(f"Job Role from Resume: '{job_role}'")

# Check if job_role_skills.py has this role
from data.job_role_skills import get_job_role_skills

print(f"\n=== CHECKING JOB_ROLE_SKILLS.PY ===")
found_skills = get_job_role_skills(job_role)

if found_skills:
    print(f"✓ Found {len(found_skills)} skills for '{job_role}':")
    for skill in found_skills:
        print(f"  - {skill}")
else:
    print(f"✗ '{job_role}' not found in JOB_ROLE_SKILLS")

print("\n=== EXPECTED API RESPONSE ===")
print(f"jobRoleSkills: {found_skills}")
print(f"Length: {len(found_skills) if found_skills else 0}")

