"""Check Roadmap_Dashboard collection structure"""
import os
from pymongo import MongoClient
from dotenv import load_dotenv
import json

load_dotenv()

mongo_uri = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
db_name = os.getenv('MONGODB_DB', 'Placement_Ai')

client = MongoClient(mongo_uri)
db = client[db_name]
collection = db['Roadmap_Dashboard ']  # Note: trailing space in collection name!

print(f"\n{'='*80}")
print(f"ROADMAP_DASHBOARD COLLECTION STRUCTURE")
print(f"{'='*80}\n")

count = collection.count_documents({})
print(f"Total documents: {count}\n")

# Get all documents
docs = list(collection.find().limit(10))

for idx, doc in enumerate(docs, 1):
    print(f"\n{'='*80}")
    print(f"Document {idx}:")
    print(f"{'='*80}")
    
    # Show structure
    print(f"  _id: {doc.get('_id')}")
    print(f"  mobile: {doc.get('mobile')}")
    
    roadmap = doc.get('roadmap', {})
    print(f"\n  roadmap structure:")
    
    if isinstance(roadmap, dict):
        for month_key in sorted(roadmap.keys()):
            month_data = roadmap[month_key]
            print(f"\n    {month_key}:")
            
            if isinstance(month_data, dict):
                # Show keys
                print(f"      Keys: {list(month_data.keys())}")
                
                # Check for organized_weeks
                if 'organized_weeks' in month_data:
                    org_weeks = month_data['organized_weeks']
                    print(f"\n      organized_weeks:")
                    if isinstance(org_weeks, dict):
                        for week_key in sorted(org_weeks.keys()):
                            week_data = org_weeks[week_key]
                            if isinstance(week_data, dict):
                                print(f"        {week_key}:")
                                print(f"          learning_goal: {week_data.get('learning_goal', 'N/A')[:50]}...")
                                
                                topics = week_data.get('topics', [])
                                print(f"          topics count: {len(topics)}")
                                if topics:
                                    print(f"          First topic: {topics[0]}")
    else:
        print(f"    Roadmap is not a dict: {type(roadmap)}")

print(f"\n{'='*80}\n")
