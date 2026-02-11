"""Check skill-week mapping for specific user 8864862270"""
import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

mongo_uri = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
db_name = os.getenv('MONGODB_DB', 'Placement_Ai')

client = MongoClient(mongo_uri)
db = client[db_name]

# User to check
mobile = "+91 8864862270"
clean_mobile = ''.join(filter(str.isdigit, mobile))
mobile_id = clean_mobile[-10:]  # 8864862270

print(f"\n{'='*80}")
print(f"SKILL-WEEK MAPPING FOR USER: {mobile}")
print(f"Normalized ID: {mobile_id}")
print(f"{'='*80}\n")

# Check skill_week_mapping collection
mapping_col = db['skill_week_mapping']
mapping_doc = mapping_col.find_one({'_id': mobile_id})

if not mapping_doc:
    print(f"❌ No skill mapping found for this user!")
else:
    months = mapping_doc.get('months', {})
    
    print(f"✅ Skill mapping found!")
    print(f"Total months: {len(months)}\n")
    
    for month_key in sorted(months.keys()):
        month_num = month_key.split('_')[1]
        skills = months[month_key]
        
        print(f"{'─'*80}")
        print(f"📅 MONTH {month_num} - {len(skills)} skill(s)")
        print(f"{'─'*80}\n")
        
        # Group by week
        by_week = {}
        for skill, week in skills.items():
            if week not in by_week:
                by_week[week] = []
            by_week[week].append(skill)
        
        for week in sorted(by_week.keys()):
            skill_list = by_week[week]
            print(f"  ✅ WEEK {week}:")
            for skill in sorted(skill_list):
                print(f"     • {skill}")
            print()

# Also check Roadmap_Dashboard to see the actual roadmap
print(f"\n{'='*80}")
print(f"ROADMAP FROM ROADMAP_DASHBOARD")
print(f"{'='*80}\n")

roadmap_col = db['Roadmap_Dashboard ']  # Note: trailing space
roadmap_doc = roadmap_col.find_one({'mobile': mobile})

if not roadmap_doc:
    roadmap_doc = roadmap_col.find_one({'_id': mobile})

if roadmap_doc:
    roadmap_data = roadmap_doc.get('roadmap', {})
    
    for month_key in sorted(roadmap_data.keys()):
        if not month_key.startswith('Month '):
            continue
        
        month_num = month_key.split(' ')[1]
        month_data = roadmap_data[month_key]
        
        print(f"{'─'*80}")
        print(f"📅 {month_key}")
        print(f"{'─'*80}\n")
        
        print(f"🎯 Skill Focus: {month_data.get('Skill Focus', 'N/A')}\n")
        
        print(f"📝 Learning Goals:")
        goals = month_data.get('Learning Goals', [])
        for goal in goals:
            print(f"   • {goal}")
        
        print(f"\n📅 Daily Plan (2 hours/day):")
        daily_plan = month_data.get('Daily Plan (2 hours/day)', [])
        for plan in daily_plan:
            print(f"   {plan}")
        
        print(f"\n🚀 Mini Project:")
        print(f"   {month_data.get('Mini Project', 'N/A')}")
        
        print(f"\n✅ Expected Outcome:")
        print(f"   {month_data.get('Expected Outcome', 'N/A')}")
        print()
else:
    print(f"❌ No roadmap found in Roadmap_Dashboard")

print(f"{'='*80}\n")

# Test what happens when they complete a week
print(f"\n{'='*80}")
print(f"SIMULATION: What happens when tests are completed?")
print(f"{'='*80}\n")

if mapping_doc:
    months = mapping_doc.get('months', {})
    
    print(f"When student completes weekly tests:\n")
    
    for month_key in sorted(months.keys()):
        month_num = month_key.split('_')[1]
        skills = months[month_key]
        
        by_week = {}
        for skill, week in skills.items():
            if week not in by_week:
                by_week[week] = []
            by_week[week].append(skill)
        
        for week in sorted(by_week.keys()):
            skill_list = by_week[week]
            print(f"  ✅ Month {month_num}, Week {week} test completed →")
            print(f"     Skills moved to resume: {', '.join(skill_list)}\n")

print(f"{'='*80}\n")
