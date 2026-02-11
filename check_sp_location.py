"""
Check if skillPerformance exists anywhere in Weekly_test_analysis
"""
import os
from pymongo import MongoClient
from dotenv import load_dotenv
import json

load_dotenv()

mongo_uri = os.getenv('MONGODB_URI')
db = MongoClient(mongo_uri)[os.getenv('MONGODB_DB', 'Placement_Ai')]

docs = list(db['Weekly_test_analysis'].find({'mobile': '+91 8864862270'}))

print(f"Found {len(docs)} documents in Weekly_test_analysis")

if docs:
    doc = docs[0]
    print(f"\nDocument keys (root level): {list(doc.keys())}")
    
    analysis = doc.get('analysis', {})
    print(f"Analysis keys: {list(analysis.keys())}")
    
    # Check if skillPerformance exists at root
    if 'skillPerformance' in doc:
        print(f"\nSkillPerformance at ROOT:")
        print(json.dumps(doc['skillPerformance'], indent=2))
    
    # Check if skillPerformance exists in analysis
    if 'skillPerformance' in analysis:
        print(f"\nSkillPerformance in ANALYSIS:")
        sp = analysis['skillPerformance']
        print(f"Type: {type(sp)}")
        if isinstance(sp, dict):
            print(f"Keys: {list(sp.keys())}")
            for k, v in list(sp.items())[:2]:
                print(f"\n{k}:")
                print(json.dumps(v, indent=2))
