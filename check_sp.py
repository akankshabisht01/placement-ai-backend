"""
Check week_test_result skillPerformance structure
"""
import os
from pymongo import MongoClient
from dotenv import load_dotenv
import json

load_dotenv()

mongo_uri = os.getenv('MONGODB_URI')
db = MongoClient(mongo_uri)[os.getenv('MONGODB_DB', 'Placement_Ai')]

docs = list(db['week_test_result'].find({'mobile': '+91 8864862270'}))

print(f"Found {len(docs)} documents in week_test_result")

if docs:
    doc = docs[0]
    print(f"\nWeek {doc.get('week')}, Month {doc.get('month')}")
    print(f"Score Percentage: {doc.get('scorePercentage')}")
    
    sp = doc.get('skillPerformance', {})
    print(f"\nSkillPerformance keys: {list(sp.keys())}")
    
    for skill, data in sp.items():
        print(f"\n{skill}:")
        print(json.dumps(data, indent=2))
