import os
from pymongo import MongoClient
from dotenv import load_dotenv
import json

load_dotenv()

# Get MongoDB connection
mongo_uri = os.getenv('MONGO_URI') or os.getenv('MONGODB_URI')
client = MongoClient(mongo_uri)
db = client[os.getenv("MONGODB_DB", "Placement_Ai")]

print("\n" + "="*80)
print("CHECKING SKILLS FORMAT FOR USER 8864862270")
print("="*80)

# Check Resume collection
resume_col = db['Resume']
mobile_formats = [
    "+91 8864862270",
    "+918864862270",
    "8864862270"
]

print("\n1. RESUME COLLECTION - Current Skills:")
print("-" * 80)
for fmt in mobile_formats:
    doc = resume_col.find_one({'_id': fmt})
    if doc:
        print(f"   Found with _id: {fmt}")
        skills = doc.get('skills', [])
        print(f"   Skills ({type(skills).__name__}): {json.dumps(skills, indent=6)}")
        print(f"   Number of skills: {len(skills)}")
        
        # Check if any skills contain ' & '
        combined = [s for s in skills if isinstance(s, str) and ' & ' in s]
        if combined:
            print(f"   ⚠️  Found {len(combined)} COMBINED skills: {combined}")
        else:
            print(f"   ✅ All skills are individual (no ' & ' found)")
        break

# Check skill_week_mapping collection
mapping_col = db['skill_week_mapping']
mobile_id = "8864862270"

print("\n2. SKILL_WEEK_MAPPING COLLECTION:")
print("-" * 80)
mapping_doc = mapping_col.find_one({'_id': mobile_id})
if mapping_doc:
    print(f"   Found mapping for: {mobile_id}")
    months = mapping_doc.get('months', {})
    
    for month_key, skill_map in months.items():
        print(f"\n   {month_key.upper()}:")
        for skill, week in skill_map.items():
            if ' & ' in skill:
                print(f"      Week {week}: ⚠️  COMBINED: {skill}")
            else:
                print(f"      Week {week}: ✅ Individual: {skill}")

print("\n" + "="*80)
print("ANALYSIS COMPLETE")
print("="*80 + "\n")
