from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

mongo_uri = os.getenv('MONGO_URI') or os.getenv('MONGODB_URI')
client = MongoClient(mongo_uri)
db = client[os.getenv("MONGODB_DB", "Placement_Ai")]

resume_col = db['Resume']

print("\n" + "="*80)
print("CHECKING IF ALL USERS HAVE JOB SELECTION")
print("="*80)

total_resumes = resume_col.count_documents({})
print(f"\nTotal resumes: {total_resumes}")

# Check how many have jobSelection
with_job_selection = resume_col.count_documents({'jobSelection': {'$exists': True}})
without_job_selection = total_resumes - with_job_selection

print(f"\n✅ With jobSelection: {with_job_selection}")
print(f"❌ Without jobSelection: {without_job_selection}")

# Check how many have skills in jobSelection
with_skills = resume_col.count_documents({
    '$or': [
        {'jobSelection.selectedSkills.0': {'$exists': True}},
        {'jobSelection.unselectedSkills.0': {'$exists': True}}
    ]
})

print(f"✅ With skills in jobSelection: {with_skills}")
print(f"⚠️  With empty skills arrays: {with_job_selection - with_skills}")

# Show sample users without jobSelection
print(f"\n{'='*80}")
print("USERS WITHOUT JOB SELECTION:")
print("="*80)

users_without = resume_col.find({'jobSelection': {'$exists': False}}).limit(5)
for user in users_without:
    print(f"\n_id: {user.get('_id')}")
    print(f"Name: {user.get('name', 'N/A')}")
    print(f"Available fields: {list(user.keys())}")

# Show sample users with empty skills
print(f"\n{'='*80}")
print("USERS WITH EMPTY SKILLS IN JOB SELECTION:")
print("="*80)

users_empty_skills = resume_col.find({
    'jobSelection': {'$exists': True},
    'jobSelection.selectedSkills': {'$size': 0},
    'jobSelection.unselectedSkills': {'$size': 0}
}).limit(5)

count = 0
for user in users_empty_skills:
    count += 1
    print(f"\n_id: {user.get('_id')}")
    print(f"Name: {user.get('name', 'N/A')}")
    print(f"jobSelection: {user.get('jobSelection')}")

if count == 0:
    print("\n✅ No users found with empty skill arrays")

print("\n" + "="*80)
print("CONCLUSION:")
print("="*80)

if without_job_selection > 0:
    print(f"⚠️  WARNING: {without_job_selection} users don't have jobSelection field!")
    print(f"   These users will get error: 'No job role found in your profile'")
else:
    print(f"✅ All {total_resumes} users have jobSelection field")

if (with_job_selection - with_skills) > 0:
    print(f"⚠️  WARNING: {with_job_selection - with_skills} users have empty skills arrays!")
    print(f"   These users will get error: 'No skills found in jobSelection'")
else:
    print(f"✅ All users with jobSelection have skills defined")

print("\n" + "="*80)
