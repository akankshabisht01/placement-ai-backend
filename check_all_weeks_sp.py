"""
Check all weeks in Weekly_test_analysis collection
"""
import os
from pymongo import MongoClient
from dotenv import load_dotenv
import json

load_dotenv()

mongo_uri = os.getenv('MONGODB_URI')
db = MongoClient(mongo_uri)[os.getenv('MONGODB_DB', 'Placement_Ai')]

docs = list(db['Weekly_test_analysis'].find({'mobile': '+91 8864862270'}).sort('_id', 1))

print(f"Found {len(docs)} documents in Weekly_test_analysis")
print("="*80)

for doc in docs:
    analysis = doc.get('analysis', {})
    print(f"\nWeek {analysis.get('week')}, Month {analysis.get('month')}")
    print(f"Overall Score (score_summary): {analysis.get('score_summary', {}).get('percentage')}%")
    
    sp = doc.get('skillPerformance', {})
    print(f"\nSkillPerformance (root level) - {len(sp)} topics:")
    for topic, data in sp.items():
        print(f"  • {topic}")
        print(f"    Score: {data.get('score')}/{data.get('maxScore')} = {data.get('percentage')}%")
        print(f"    Correct: {data.get('correct')}/{data.get('total')}")
    
    print("="*80)
