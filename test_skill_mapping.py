"""Test script to verify skill-week mapping functionality"""
import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

# Get MongoDB connection
mongo_uri = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
db_name = os.getenv('MONGODB_DB', 'Placement_Ai')

client = MongoClient(mongo_uri)
db = client[db_name]

# Check if skill_week_mapping collection exists and has data
mapping_col = db['skill_week_mapping']
count = mapping_col.count_documents({})

print(f"\n{'='*60}")
print(f"SKILL-WEEK MAPPING COLLECTION STATUS")
print(f"{'='*60}")
print(f"Collection: skill_week_mapping")
print(f"Document count: {count}")
print(f"{'='*60}\n")

if count > 0:
    print("Sample documents:")
    for doc in mapping_col.find().limit(3):
        print(f"\nUser: {doc.get('_id')}")
        months = doc.get('months', {})
        for month_key, mapping in months.items():
            print(f"  {month_key}: {mapping}")
else:
    print("⚠️ No documents found in skill_week_mapping collection")
    print("\nChecking weekly_plans collection for comparison...")
    
    weekly_plans_col = db['weekly_plans']
    plans_count = weekly_plans_col.count_documents({})
    print(f"weekly_plans collection has {plans_count} documents")
    
    if plans_count > 0:
        sample_plan = weekly_plans_col.find_one()
        print(f"\nSample user with weekly plan: {sample_plan.get('_id')}")
        print(f"Months in plan: {list(sample_plan.get('months', {}).keys())}")

print("\n" + "="*60)
