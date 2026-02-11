import os
from pymongo import MongoClient
from dotenv import load_dotenv
import json

load_dotenv()

# Get MongoDB connection
mongo_uri = os.getenv('MONGO_URI') or os.getenv('MONGODB_URI')
client = MongoClient(mongo_uri)
db = client[os.getenv("MONGODB_DB", "Placement_Ai")]

mobile = "8864862270"

print("\n" + "="*80)
print("DEBUGGING: WHY STARS NOT SHOWING")
print("="*80)

# 1. Check skill mappings
print("\n1. SKILL MAPPINGS IN DATABASE:")
print("-" * 80)
mapping_col = db['skill_week_mapping']
mapping_doc = mapping_col.find_one({'_id': mobile})

if mapping_doc:
    months = mapping_doc.get('months', {})
    all_mapped_skills = set()
    for month_key, skill_map in months.items():
        print(f"\n   {month_key.upper()}:")
        for skill, weeks in skill_map.items():
            print(f"      {skill}: {weeks}")
            all_mapped_skills.add(skill)
    
    print(f"\n   Total unique skills in mapping: {len(all_mapped_skills)}")
    print(f"   Skills: {sorted(all_mapped_skills)}")
else:
    print("   ❌ No mapping found!")

# 2. Check skills in Resume
print("\n2. SKILLS IN RESUME:")
print("-" * 80)
resume_col = db['Resume']
resume_doc = resume_col.find_one({'_id': f'+91 {mobile}'})

if resume_doc:
    resume_skills = resume_doc.get('skills', [])
    print(f"   Skills in resume ({len(resume_skills)} total):")
    for skill in resume_skills:
        print(f"      - {skill}")
else:
    print("   ❌ Resume not found!")

# 3. Check if user has taken any weekly tests
print("\n3. WEEKLY TEST RESULTS:")
print("-" * 80)
week_test_col = db['week_test_result']

mobile_variants = [
    f'+91 {mobile}',
    f'+91{mobile}',
    mobile
]

all_results = list(week_test_col.find({'mobile': {'$in': mobile_variants}}))

if all_results:
    print(f"   Found {len(all_results)} test results:")
    for result in all_results:
        print(f"      Month {result.get('month')}, Week {result.get('week')}: {result.get('scorePercentage')}%")
else:
    print("   ❌ NO WEEKLY TEST RESULTS FOUND!")
    print("   ⚠️  This is why stars are not showing!")
    print("   → User needs to complete weekly tests first")

# 4. Check name matching
print("\n4. SKILL NAME MATCHING:")
print("-" * 80)

if mapping_doc and resume_doc:
    resume_skills_set = set(resume_skills)
    
    print("   Checking which resume skills have mappings:")
    for skill in resume_skills:
        if skill in all_mapped_skills:
            print(f"      ✅ {skill} - HAS MAPPING")
        else:
            print(f"      ❌ {skill} - NO MAPPING (won't show stars)")
    
    print("\n   Checking which mapped skills are in resume:")
    for skill in all_mapped_skills:
        if skill in resume_skills_set:
            print(f"      ✅ {skill} - IN RESUME")
        else:
            # Check if it's a combined skill that was split
            parts = [s.strip() for s in skill.split(' & ')]
            if all(part in resume_skills_set for part in parts):
                print(f"      ⚠️  {skill} - WAS SPLIT INTO: {parts}")
            else:
                print(f"      ❌ {skill} - NOT IN RESUME (mapping won't be used)")

print("\n" + "="*80)
print("DIAGNOSIS:")
print("="*80)

if not all_results:
    print("\n❌ PRIMARY ISSUE: NO WEEKLY TEST RESULTS")
    print("   → User needs to complete weekly tests to get star ratings")
    print("   → Stars are calculated from test performance")
elif mapping_doc and resume_doc:
    # Check if any resume skills have mappings
    matched = any(skill in all_mapped_skills for skill in resume_skills)
    if not matched:
        print("\n❌ ISSUE: SKILL NAME MISMATCH")
        print("   → Skills in resume don't match skills in mapping")
        print("   → Need to regenerate mappings or check skill names")
    else:
        print("\n✅ Skills have mappings and tests exist")
        print("   → Issue might be in frontend display logic")
else:
    print("\n❌ Missing data - check mapping or resume")

print("="*80 + "\n")
