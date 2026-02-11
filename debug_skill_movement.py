"""Check resume and debug skill movement for user 8864862270"""
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
mobile_id = clean_mobile[-10:]

print(f"\n{'='*80}")
print(f"DEBUGGING SKILL MOVEMENT FOR USER: {mobile}")
print(f"{'='*80}\n")

# Check Resume
resume_col = db['Resume']
resume_doc = resume_col.find_one({'mobile': mobile})

if not resume_doc:
    print(f"❌ No resume found!")
else:
    print(f"✅ Resume found\n")
    print(f"Current Skills in Resume:")
    skills = resume_doc.get('skills', [])
    if skills:
        for i, skill in enumerate(skills, 1):
            print(f"  {i}. {skill}")
    else:
        print(f"  (empty)")
    print()

# Check skill_week_mapping
mapping_col = db['skill_week_mapping']
mapping_doc = mapping_col.find_one({'_id': mobile_id})

if not mapping_doc:
    print(f"❌ No skill mapping found!")
else:
    print(f"✅ Skill-week mapping found\n")
    months = mapping_doc.get('months', {})
    
    print(f"Skills that should complete at Week 4 in each month:")
    for month_key in sorted(months.keys()):
        month_num = month_key.split('_')[1]
        skills_map = months[month_key]
        
        week_4_skills = [skill for skill, week in skills_map.items() if week == 4]
        if week_4_skills:
            print(f"  Month {month_num}, Week 4: {week_4_skills}")

print(f"\n{'='*80}")
print(f"WHAT SHOULD HAPPEN:")
print(f"{'='*80}\n")

if mapping_doc and resume_doc:
    print(f"When user completes Month 1, Week 4 test:")
    print(f"  - Expected skill to add: 'Machine Learning Models & scikit-learn'")
    print(f"  - Current resume skills: {resume_doc.get('skills', [])}")
    
    # Check if skill is already in resume
    target_skill = "Machine Learning Models & scikit-learn"
    if target_skill in resume_doc.get('skills', []):
        print(f"\n  ✅ ALREADY IN RESUME!")
    else:
        print(f"\n  ❌ NOT YET IN RESUME - Should be added when test completes")

print(f"\n{'='*80}")
print(f"CHECKING WEEK_TEST COLLECTION:")
print(f"{'='*80}\n")

# Check if test was actually submitted
week_test_col = db['week_test']
tests = list(week_test_col.find({'mobile': mobile}).sort('createdAt', -1).limit(5))

if tests:
    print(f"Recent tests for this user:\n")
    for test in tests:
        month = test.get('month')
        week = test.get('week')
        created = test.get('createdAt')
        print(f"  - Month {month}, Week {week} (Created: {created})")
else:
    print(f"❌ No tests found in week_test collection")

print(f"\n{'='*80}\n")
