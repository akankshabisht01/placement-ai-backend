"""
Test automatic skill mapping generation when fetching roadmaps.
This simulates what happens when a user views their roadmap page.
"""
import requests
import json

# Test with a user who has roadmap but no skill mappings
mobile = "+91 8864862270"  # Different user to test

print(f"\n{'='*80}")
print(f"TESTING AUTOMATIC SKILL MAPPING GENERATION")
print(f"{'='*80}\n")

print(f"📱 Mobile: {mobile}")
print(f"🎯 Fetching roadmaps (this should auto-generate skill mappings)...\n")

# Call the get-all-roadmaps endpoint
url = "http://localhost:5000/api/get-all-roadmaps"
payload = {"mobile": mobile}

print(f"📤 POST {url}")
response = requests.post(url, json=payload)

print(f"📥 Response Status: {response.status_code}\n")

if response.status_code == 200:
    result = response.json()
    print(f"✅ Roadmaps fetched successfully!")
    print(f"   Domains: {list(result['data']['roadmapsByDomain'].keys())}")
    print(f"   Total roadmaps: {result['data']['totalRoadmaps']}")
    
    # Now check if skill mappings were created
    print(f"\n{'='*80}")
    print(f"CHECKING SKILL_WEEK_MAPPING COLLECTION")
    print(f"{'='*80}\n")
    
    import os
    from pymongo import MongoClient
    from dotenv import load_dotenv
    
    load_dotenv()
    mongo_uri = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
    db_name = os.getenv('MONGODB_DB', 'Placement_Ai')
    
    client = MongoClient(mongo_uri)
    db = client[db_name]
    collection = db['skill_week_mapping']
    
    # Normalize mobile to find in DB
    clean_mobile = ''.join(filter(str.isdigit, mobile))
    mobile_id = clean_mobile[-10:]
    
    mapping_doc = collection.find_one({'_id': mobile_id})
    
    if mapping_doc:
        print(f"✅ Skill mappings found for user {mobile_id}!")
        months = mapping_doc.get('months', {})
        
        for month_key in sorted(months.keys()):
            month_num = month_key.split('_')[1]
            skills = months[month_key]
            
            print(f"\n📅 MONTH {month_num} ({len(skills)} skills):")
            print(f"{'─'*60}")
            
            for skill, week in sorted(skills.items(), key=lambda x: x[1]):
                print(f"   Week {week}: {skill}")
    else:
        print(f"❌ No skill mappings found for user {mobile_id}")
        print(f"   This means auto-generation didn't work or was skipped")
else:
    print(f"❌ Failed to fetch roadmaps: {response.text}")

print(f"\n{'='*80}\n")
