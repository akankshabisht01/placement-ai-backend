"""Check all users in Roadmap_Dashboard and their skill mappings"""
import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

mongo_uri = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
db_name = os.getenv('MONGODB_DB', 'Placement_Ai')

client = MongoClient(mongo_uri)
db = client[db_name]

roadmap_col = db['Roadmap_Dashboard ']  # Note: trailing space
mapping_col = db['skill_week_mapping']

print(f"\n{'='*80}")
print(f"USERS IN ROADMAP_DASHBOARD vs SKILL_WEEK_MAPPING")
print(f"{'='*80}\n")

roadmaps = list(roadmap_col.find())

for roadmap in roadmaps:
    user_id = roadmap.get('_id')
    mobile = roadmap.get('mobile')
    
    # Normalize mobile to check mapping
    clean_mobile = ''.join(filter(str.isdigit, str(mobile)))
    mobile_id = clean_mobile[-10:]
    
    # Check if mapping exists
    mapping = mapping_col.find_one({'_id': mobile_id})
    
    print(f"User: {mobile} (ID: {user_id})")
    print(f"  Normalized ID: {mobile_id}")
    print(f"  Has mapping: {'✅ YES' if mapping else '❌ NO'}")
    
    if mapping:
        months = mapping.get('months', {})
        print(f"  Months with mappings: {list(months.keys())}")
    
    print()

print(f"{'='*80}\n")
