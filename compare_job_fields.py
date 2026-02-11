from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

mongo_uri = os.getenv('MONGO_URI') or os.getenv('MONGODB_URI')
client = MongoClient(mongo_uri)
db = client[os.getenv("MONGODB_DB", "Placement_Ai")]

resume_col = db['Resume']

print("\n" + "="*80)
print("COMPARING jobRoleSkills vs jobSelection")
print("="*80)

total_resumes = resume_col.count_documents({})
print(f"\nTotal resumes: {total_resumes}")

# Check jobRoleSkills
with_job_role_skills = resume_col.count_documents({'jobRoleSkills': {'$exists': True}})
print(f"\n✅ With jobRoleSkills: {with_job_role_skills}")

with_job_role_skills_and_data = resume_col.count_documents({
    'jobRoleSkills': {'$exists': True},
    '$or': [
        {'jobRoleSkills.current.0': {'$exists': True}},
        {'jobRoleSkills.skillsToLearn.0': {'$exists': True}}
    ]
})
print(f"   → With skills data: {with_job_role_skills_and_data}")

# Check jobSelection
with_job_selection = resume_col.count_documents({'jobSelection': {'$exists': True}})
print(f"\n✅ With jobSelection: {with_job_selection}")

with_job_selection_and_data = resume_col.count_documents({
    'jobSelection': {'$exists': True},
    '$or': [
        {'jobSelection.selectedSkills.0': {'$exists': True}},
        {'jobSelection.unselectedSkills.0': {'$exists': True}}
    ]
})
print(f"   → With skills data: {with_job_selection_and_data}")

# Check users with BOTH fields
with_both = resume_col.count_documents({
    'jobRoleSkills': {'$exists': True},
    'jobSelection': {'$exists': True}
})
print(f"\n🔄 With BOTH fields: {with_both}")

# Check users with ONLY jobRoleSkills
only_job_role_skills = resume_col.count_documents({
    'jobRoleSkills': {'$exists': True},
    'jobSelection': {'$exists': False}
})
print(f"   → ONLY jobRoleSkills: {only_job_role_skills}")

# Check users with ONLY jobSelection
only_job_selection = resume_col.count_documents({
    'jobSelection': {'$exists': True},
    'jobRoleSkills': {'$exists': False}
})
print(f"   → ONLY jobSelection: {only_job_selection}")

# Check users with NEITHER
with_neither = resume_col.count_documents({
    'jobRoleSkills': {'$exists': False},
    'jobSelection': {'$exists': False}
})
print(f"   → NEITHER field: {with_neither}")

print(f"\n{'='*80}")
print("SAMPLE COMPARISON:")
print("="*80)

# Show one user with both fields
user = resume_col.find_one({
    'jobRoleSkills': {'$exists': True},
    'jobSelection': {'$exists': True}
})

if user:
    import json
    print(f"\nUser: {user.get('_id')}")
    print(f"\njobRoleSkills:")
    print(json.dumps(user.get('jobRoleSkills'), indent=2))
    print(f"\njobSelection:")
    print(json.dumps(user.get('jobSelection'), indent=2, default=str))

print(f"\n{'='*80}")
print("RECOMMENDATION:")
print("="*80)

if with_job_role_skills >= with_job_selection:
    print(f"✅ USE jobRoleSkills - covers {with_job_role_skills}/{total_resumes} users")
    print(f"   jobSelection only covers {with_job_selection}/{total_resumes} users")
elif with_job_selection > with_job_role_skills:
    print(f"✅ USE jobSelection - covers {with_job_selection}/{total_resumes} users")
    print(f"   jobRoleSkills only covers {with_job_role_skills}/{total_resumes} users")

if with_both == total_resumes:
    print(f"✅✅ BEST: Use BOTH with fallback - all users covered!")

print("\n" + "="*80)
