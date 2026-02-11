from pymongo import MongoClient
import json

c = MongoClient('mongodb://localhost:27017/')
db = c['Placement_Ai']

# Check skill_week_mapping for this user
mobile_variants = ['8864862270', '+918864862270', '+91 8864862270']

print('='*80)
print('CHECKING SKILL_WEEK_MAPPING')
print('='*80)

mapping = None
for variant in mobile_variants:
    mapping = db.skill_week_mapping.find_one({'_id': variant})
    if mapping:
        print(f'\n✅ Found mapping with _id: {variant}')
        break

if mapping:
    print('\n' + '='*80)
    print('ACTUAL SKILLS FOR USER +91 8864862270:')
    print('='*80)
    
    for month in mapping.get('months', []):
        month_num = month.get('month')
        print(f'\n📅 Month {month_num}:')
        
        for skill_obj in month.get('skills', []):
            skill_name = skill_obj.get('skill')
            weeks = skill_obj.get('weeks', [])
            print(f'  ✓ {skill_name}')
            print(f'    Weeks: {weeks}')
else:
    print(f'\n❌ No skill_week_mapping found for any variant')
    print(f'Tried: {mobile_variants}')
    print(f'\nTotal documents in skill_week_mapping: {db.skill_week_mapping.count_documents({})}')
    
    # Show sample if any exist
    sample = db.skill_week_mapping.find_one()
    if sample:
        print(f'\nSample _id format: {sample["_id"]}')
