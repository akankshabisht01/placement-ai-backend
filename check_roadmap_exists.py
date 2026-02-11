from pymongo import MongoClient
import os
from dotenv import load_dotenv
import json

load_dotenv()

# Connect to MongoDB
MONGODB_URI = os.getenv('MONGODB_URI')
client = MongoClient(MONGODB_URI)
db = client['Placement_Ai']

mobile = "+91 8864862270"
clean_mobile = ''.join(filter(str.isdigit, mobile))

print(f"\n{'='*80}")
print(f"CHECKING ROADMAP_DASHBOARD FOR {mobile}")
print(f"{'='*80}\n")

# Check Roadmap_Dashboard collection (note trailing space)
roadmap_collection = db['Roadmap_Dashboard ']

# Try different mobile formats
mobile_formats = [
    mobile,
    clean_mobile,
    clean_mobile[-10:],
    f"+91 {clean_mobile[-10:]}",
    f"+91{clean_mobile[-10:]}"
]

print(f"Searching with formats: {mobile_formats}\n")

roadmap_doc = roadmap_collection.find_one({'_id': {'$in': mobile_formats}})

if roadmap_doc:
    print(f"✅ FOUND roadmap document!")
    print(f"   _id: {roadmap_doc.get('_id')}")
    
    roadmap_data = roadmap_doc.get('roadmap', {})
    print(f"   Has 'roadmap' key: {bool(roadmap_data)}")
    
    if roadmap_data:
        print(f"   Months in roadmap: {list(roadmap_data.keys())}")
        
        # Check Month 2 structure
        month_2 = roadmap_data.get('Month 2', {})
        if month_2:
            print(f"\n   Month 2 structure:")
            print(f"   - Skill Focus: {month_2.get('Skill Focus', 'MISSING')}")
            print(f"   - Learning Goals: {len(month_2.get('Learning Goals', []))} goals")
            print(f"   - Daily Plan: {len(month_2.get('Daily Plan (2 hours/day)', []))} weeks")
            print(f"   - Mini Project: {'YES' if month_2.get('Mini Project') else 'NO'}")
    else:
        print(f"   ❌ 'roadmap' key is empty!")
else:
    print(f"❌ NO roadmap found!")
    print(f"\nAll documents in Roadmap_Dashboard collection:")
    all_docs = list(roadmap_collection.find({}, {'_id': 1}))
    if all_docs:
        for doc in all_docs:
            print(f"   - {doc['_id']}")
    else:
        print(f"   Collection is empty!")

print(f"\n{'='*80}\n")
