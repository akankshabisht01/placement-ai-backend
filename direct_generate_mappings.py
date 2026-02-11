"""
Direct skill mapping generation without using the API endpoint.
This connects directly to MongoDB and generates mappings.
"""
import os
import sys
import json
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime

# Add parent directory to path to import from app.py
sys.path.insert(0, os.path.dirname(__file__))

load_dotenv()

# Import the functions from app.py
mongo_uri = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
db_name = os.getenv('MONGODB_DB', 'Placement_Ai')

client = MongoClient(mongo_uri)
db = client[db_name]

# Import the AI analysis function
from app import _analyze_roadmap_dashboard_for_skills, _normalize_mobile_id

def save_skill_week_mapping(mobile, month_number, skill_mapping):
    """Save skill-to-week completion mapping in MongoDB"""
    try:
        collection = db['skill_week_mapping']
        mobile_id = _normalize_mobile_id(mobile)
        month_key = f"month_{month_number}"
        
        collection.update_one(
            {'_id': mobile_id},
            {
                '$set': {
                    f'months.{month_key}': skill_mapping,
                    'updated_at': datetime.utcnow()
                },
                '$setOnInsert': {
                    'created_at': datetime.utcnow()
                }
            },
            upsert=True
        )
        
        print(f"   💾 Saved mapping for {mobile_id}, {month_key}")
        return True
    except Exception as e:
        print(f"   ❌ Error saving: {str(e)}")
        return False


# Users to process
users_to_process = [
    "+91 7302249246",
    "+91 8126355099",
    "+91 9346333208",
    "+91 9084117332",
    "+91 8864862270"
]

print(f"\n{'='*80}")
print(f"DIRECT SKILL MAPPING GENERATION")
print(f"{'='*80}\n")

roadmap_col = db['Roadmap_Dashboard ']  # Note: trailing space

for mobile in users_to_process:
    print(f"\n{'─'*80}")
    print(f"Processing: {mobile}")
    print(f"{'─'*80}")
    
    # Find roadmap
    roadmap_doc = roadmap_col.find_one({'mobile': mobile})
    
    if not roadmap_doc:
        # Try with _id
        roadmap_doc = roadmap_col.find_one({'_id': mobile})
    
    if not roadmap_doc:
        print(f"❌ No roadmap found for {mobile}")
        continue
    
    print(f"✅ Found roadmap")
    
    roadmap_data = roadmap_doc.get('roadmap', {})
    
    if not roadmap_data:
        print(f"❌ Empty roadmap data")
        continue
    
    # Process each month
    months_processed = 0
    total_skills = 0
    
    for month_key, month_data in roadmap_data.items():
        if not month_key.startswith('Month '):
            continue
        
        try:
            month_num = int(month_key.split(' ')[1])
            print(f"\n   📅 {month_key}...")
            
            # Analyze this month
            skill_mapping = _analyze_roadmap_dashboard_for_skills(month_data)
            
            if skill_mapping:
                save_skill_week_mapping(mobile, month_num, skill_mapping)
                months_processed += 1
                total_skills += len(skill_mapping)
                print(f"      ✅ {len(skill_mapping)} skills mapped")
                
                # Show skills
                for skill, week in sorted(skill_mapping.items(), key=lambda x: x[1]):
                    print(f"         Week {week}: {skill}")
            else:
                print(f"      ⚠️ No skills extracted")
        
        except Exception as e:
            print(f"      ❌ Error: {str(e)}")
            continue
    
    print(f"\n   Summary: {months_processed} months, {total_skills} total skills")

print(f"\n{'='*80}")
print(f"GENERATION COMPLETE")
print(f"{'='*80}\n")

# Verify results
print(f"VERIFICATION:")
print(f"{'='*80}\n")

mapping_col = db['skill_week_mapping']

for mobile in users_to_process:
    clean_mobile = ''.join(filter(str.isdigit, mobile))
    mobile_id = clean_mobile[-10:]
    
    mapping = mapping_col.find_one({'_id': mobile_id})
    
    if mapping:
        months = mapping.get('months', {})
        print(f"✅ {mobile}: {len(months)} months mapped")
    else:
        print(f"❌ {mobile}: No mapping")

print(f"\n{'='*80}\n")
