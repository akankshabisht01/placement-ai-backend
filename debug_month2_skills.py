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
print(f"DEBUGGING MONTH 2 SKILL COMPLETION FOR USER {mobile}")
print("="*80)

# 1. Check skill mappings for Month 2
print("\n1. SKILL-WEEK MAPPINGS FOR MONTH 2:")
print("-" * 80)
mapping_col = db['skill_week_mapping']
mapping_doc = mapping_col.find_one({'_id': mobile})

if mapping_doc:
    month_2 = mapping_doc.get('months', {}).get('month_2', {})
    if month_2:
        print(f"   Month 2 Skill Mappings:")
        for skill, week in month_2.items():
            print(f"      Week {week}: {skill}")
    else:
        print("   ⚠️  No Month 2 mapping found!")
else:
    print("   ⚠️  No mapping document found for this user!")

# 2. Check week_test submissions for Month 2
print("\n2. WEEK TEST SUBMISSIONS FOR MONTH 2:")
print("-" * 80)
week_test_col = db['week_test']

# Try different mobile formats
mobile_formats = [
    f"+91 {mobile}",
    f"+91{mobile}",
    mobile
]

for fmt in mobile_formats:
    submissions = list(week_test_col.find({'mobile': fmt, 'month': 2}).sort('week', 1))
    if submissions:
        print(f"   Found submissions with mobile format: {fmt}")
        for sub in submissions:
            print(f"      Week {sub.get('week')}: Submitted on {sub.get('submitted_at', 'N/A')}")
        break
else:
    print("   ⚠️  No Month 2 test submissions found!")
    print(f"   Tried formats: {mobile_formats}")

# 3. Check current skills in Resume
print("\n3. CURRENT SKILLS IN RESUME:")
print("-" * 80)
resume_col = db['Resume']

resume_formats = [
    f"+91 {mobile}",
    f"+91{mobile}",
    mobile
]

resume_doc = None
for fmt in resume_formats:
    resume_doc = resume_col.find_one({'_id': fmt})
    if resume_doc:
        print(f"   Found resume with _id: {fmt}")
        skills = resume_doc.get('skills', [])
        print(f"   Current skills ({len(skills)} total):")
        for i, skill in enumerate(skills, 1):
            print(f"      {i}. {skill}")
        break

if not resume_doc:
    print("   ⚠️  Resume not found!")

# 4. What SHOULD have happened for Month 2
print("\n4. EXPECTED BEHAVIOR:")
print("-" * 80)
if mapping_doc and month_2:
    print("   When user completes Month 2 tests, these skills should move:")
    for skill, week in month_2.items():
        if ' & ' in skill:
            individual = [s.strip() for s in skill.split(' & ')]
            print(f"      Week {week}: {skill}")
            print(f"         → Splits into: {individual}")
        else:
            print(f"      Week {week}: {skill}")

print("\n" + "="*80)
print("DIAGNOSIS")
print("="*80)

# Check if Month 2 Week 4 was completed
if mapping_doc and month_2:
    submissions = list(week_test_col.find({'month': 2}).sort('week', 1))
    if submissions:
        weeks_completed = [s.get('week') for s in submissions]
        print(f"✅ Month 2 weeks completed: {weeks_completed}")
        
        # Check if Week 4 (or Week 8 cumulative) was completed
        if 4 in weeks_completed or 8 in weeks_completed:
            print("✅ Month 2 Week 4 completed")
            
            # Check what skills should have been added
            expected_skills = []
            for skill, week in month_2.items():
                if ' & ' in skill:
                    expected_skills.extend([s.strip() for s in skill.split(' & ')])
                else:
                    expected_skills.append(skill)
            
            print(f"\n📋 Expected skills to be added: {expected_skills}")
            
            if resume_doc:
                current_skills = resume_doc.get('skills', [])
                missing_skills = [s for s in expected_skills if s not in current_skills]
                
                if missing_skills:
                    print(f"\n❌ PROBLEM: These skills are MISSING from resume:")
                    for skill in missing_skills:
                        print(f"      - {skill}")
                    print("\n🔧 LIKELY CAUSE: Frontend didn't call /api/check-skill-completion-with-ai")
                else:
                    print(f"\n✅ All Month 2 skills are already in resume!")
        else:
            print(f"⚠️  Month 2 Week 4 NOT completed (only weeks {weeks_completed})")
    else:
        print("❌ No Month 2 test submissions found - user hasn't taken tests yet")
else:
    print("❌ No skill mapping exists for Month 2")

print("="*80 + "\n")
