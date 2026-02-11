"""
Generate skill-week mappings WITHOUT Perplexity API.
Uses simple text parsing to extract week numbers from Daily Plan.
"""
import os
import re
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

mongo_uri = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
db_name = os.getenv('MONGODB_DB', 'Placement_Ai')

client = MongoClient(mongo_uri)
db = client[db_name]

roadmap_col = db['Roadmap_Dashboard ']  # Note: trailing space
mapping_col = db['skill_week_mapping']

def normalize_mobile_id(mobile):
    """Normalize mobile to last 10 digits"""
    clean = ''.join(filter(str.isdigit, str(mobile)))
    return clean[-10:]

def extract_skills_from_month(month_data):
    """
    Extract skills from month data using simple text parsing.
    Maps each skill from 'Skill Focus' to the last week it's mentioned.
    """
    skill_focus = month_data.get('Skill Focus', '')
    daily_plan = month_data.get('Daily Plan (2 hours/day)', [])
    
    # Extract skills from Skill Focus (split by commas)
    skills = [s.strip() for s in skill_focus.split(',')]
    skills = [s for s in skills if s]  # Remove empty
    
    # Map each skill to week 4 by default (end of month)
    skill_mapping = {}
    
    for skill in skills:
        # Default to week 4
        week_num = 4
        
        # Check if skill is mentioned in specific weeks
        for i, plan_text in enumerate(daily_plan, 1):
            if isinstance(plan_text, str) and skill.lower() in plan_text.lower():
                # If skill mentioned in a week, set that as completion week
                # Extract week number from "Week X:" pattern
                week_match = re.search(r'Week\s+(\d+)', plan_text)
                if week_match:
                    week_num = int(week_match.group(1))
        
        skill_mapping[skill] = week_num
    
    return skill_mapping

print(f"\n{'='*80}")
print(f"SIMPLE SKILL MAPPING GENERATION (No Perplexity)")
print(f"{'='*80}\n")

# Process all users
all_roadmaps = list(roadmap_col.find())

for roadmap_doc in all_roadmaps:
    mobile = roadmap_doc.get('mobile')
    user_id = roadmap_doc.get('_id')
    
    print(f"\n{'─'*80}")
    print(f"User: {mobile}")
    print(f"{'─'*80}")
    
    # Check if mapping already exists
    mobile_id = normalize_mobile_id(mobile)
    existing = mapping_col.find_one({'_id': mobile_id})
    
    if existing:
        print(f"✅ Mapping already exists, skipping")
        continue
    
    roadmap_data = roadmap_doc.get('roadmap', {})
    
    if not roadmap_data:
        print(f"❌ No roadmap data")
        continue
    
    # Process each month
    all_months = {}
    
    for month_key, month_data in roadmap_data.items():
        if not month_key.startswith('Month '):
            continue
        
        try:
            month_num = int(month_key.split(' ')[1])
            print(f"\n   📅 {month_key}...")
            
            skill_mapping = extract_skills_from_month(month_data)
            
            if skill_mapping:
                all_months[f"month_{month_num}"] = skill_mapping
                print(f"      ✅ {len(skill_mapping)} skills:")
                for skill, week in sorted(skill_mapping.items(), key=lambda x: x[1]):
                    print(f"         Week {week}: {skill}")
            else:
                print(f"      ⚠️ No skills extracted")
        
        except Exception as e:
            print(f"      ❌ Error: {str(e)}")
            continue
    
    # Save to database
    if all_months:
        mapping_col.insert_one({
            '_id': mobile_id,
            'months': all_months,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        })
        print(f"\n   💾 Saved {len(all_months)} months to database")
    else:
        print(f"\n   ⚠️ No months to save")

print(f"\n{'='*80}")
print(f"GENERATION COMPLETE")
print(f"{'='*80}\n")

# Verify
print(f"FINAL VERIFICATION:")
print(f"{'='*80}\n")

count = mapping_col.count_documents({})
print(f"Total users with skill mappings: {count}\n")

for doc in mapping_col.find():
    user_id = doc.get('_id')
    months = doc.get('months', {})
    total_skills = sum(len(m) for m in months.values())
    print(f"✅ User {user_id}: {len(months)} months, {total_skills} skills")

print(f"\n{'='*80}\n")
