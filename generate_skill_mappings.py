"""
Manually trigger skill-week mapping for existing roadmaps
Run this to analyze existing roadmaps and create skill mappings
"""
import os
import sys
from pymongo import MongoClient
from dotenv import load_dotenv

# Add parent directory to path to import from app.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the analysis function from app
from app import _analyze_roadmap_for_skill_completion, _save_skill_week_mapping

load_dotenv()

# Get MongoDB connection
mongo_uri = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
db_name = os.getenv('MONGODB_DB', 'Placement_Ai')

client = MongoClient(mongo_uri)
db = client[db_name]

# Get all weekly plans
weekly_plans_col = db['weekly_plans']
all_plans = list(weekly_plans_col.find())

print(f"\n{'='*80}")
print(f"GENERATING SKILL-WEEK MAPPINGS FOR EXISTING ROADMAPS")
print(f"{'='*80}")
print(f"Found {len(all_plans)} users with weekly plans\n")

success_count = 0
fail_count = 0

for plan_doc in all_plans:
    user_id = plan_doc.get('_id')
    months = plan_doc.get('months', {})
    
    print(f"\n📱 User: {user_id}")
    print(f"   Months available: {list(months.keys())}")
    
    for month_key, month_data in months.items():
        month_number = int(month_key.split('_')[1])
        
        print(f"\n   🗓️  Processing {month_key}...")
        
        try:
            # Analyze roadmap
            skill_mapping = _analyze_roadmap_for_skill_completion(month_data, month_number)
            
            if skill_mapping:
                # Save mapping
                _save_skill_week_mapping(user_id, month_number, skill_mapping)
                print(f"      ✅ Saved mapping: {skill_mapping}")
                success_count += 1
            else:
                print(f"      ⚠️ No mapping generated (empty result)")
                fail_count += 1
                
        except Exception as e:
            print(f"      ❌ Error: {str(e)}")
            fail_count += 1

print(f"\n{'='*80}")
print(f"SUMMARY")
print(f"{'='*80}")
print(f"✅ Successfully mapped: {success_count} month(s)")
print(f"❌ Failed: {fail_count} month(s)")
print(f"{'='*80}\n")
