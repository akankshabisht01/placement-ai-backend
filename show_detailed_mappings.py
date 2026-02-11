"""Show detailed skill-week mappings for all users"""
import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

mongo_uri = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
db_name = os.getenv('MONGODB_DB', 'Placement_Ai')

client = MongoClient(mongo_uri)
db = client[db_name]
collection = db['skill_week_mapping']

print(f"\n{'='*80}")
print(f"COMPLETE SKILL-WEEK MAPPING FOR ALL USERS")
print(f"{'='*80}\n")

all_mappings = list(collection.find())

for doc in all_mappings:
    user_id = doc.get('_id')
    months = doc.get('months', {})
    
    print(f"\n{'─'*80}")
    print(f"📱 USER: {user_id}")
    print(f"{'─'*80}")
    
    for month_key in sorted(months.keys()):
        month_num = month_key.split('_')[1]
        skills = months[month_key]
        
        print(f"\n  📅 MONTH {month_num}:")
        
        # Group skills by week
        by_week = {}
        for skill, week in skills.items():
            if week not in by_week:
                by_week[week] = []
            by_week[week].append(skill)
        
        # Show by week
        for week in sorted(by_week.keys()):
            skill_list = by_week[week]
            print(f"\n    ✅ WEEK {week} ({len(skill_list)} skill{'s' if len(skill_list) > 1 else ''} complete here):")
            for skill in sorted(skill_list):
                print(f"       • {skill}")

print(f"\n{'='*80}")
print(f"\nHOW IT WORKS:")
print(f"{'='*80}")
print(f"""
When a student completes a weekly test:

1. Student finishes Week 3 test in Month 2
2. Backend calls /api/check-skill-completion-with-ai
3. System checks skill_week_mapping collection:
   - Finds skills where completion_week = 3 in month_2
4. Those skills automatically move to "Skills & Expertise" in resume
5. Student sees their profile updated instantly!

Example:
- Student completes Month 1, Week 2 test
- System finds: "CSS3" completes at Week 2
- "CSS3" moves from "Skills You Can Develop" → "Skills & Expertise"
""")
print(f"{'='*80}\n")
