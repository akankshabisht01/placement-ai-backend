"""
Script to check the structure of Weekly_test_analysis collection
"""
import os
from pymongo import MongoClient
from dotenv import load_dotenv
import json

# Load environment variables
load_dotenv()

# Connect to MongoDB
mongo_uri = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
db_name = os.getenv('MONGODB_DB', 'Placement_Ai')

client = MongoClient(mongo_uri)
db = client[db_name]

# User mobile
mobile = "+91 8864862270"

# Query Weekly_test_analysis collection
collection = db['Weekly_test_analysis']

# Find all documents for this user
docs = list(collection.find({'_id': mobile}))

if not docs:
    # Try with mobile field
    docs = list(collection.find({'mobile': mobile}))

print(f"Found {len(docs)} documents in Weekly_test_analysis for {mobile}")
print("="*80)

for doc in docs:
    print(f"\nDocument ID: {doc.get('_id')}")
    print(f"Mobile: {doc.get('mobile')}")
    
    analysis = doc.get('analysis', {})
    print(f"Month: {analysis.get('month')}")
    print(f"Week: {analysis.get('week')}")
    
    # Check for skillPerformance
    skill_performance = analysis.get('skillPerformance', [])
    print(f"\nSkillPerformance (type: {type(skill_performance)}):")
    if isinstance(skill_performance, list):
        print(f"  Length: {len(skill_performance)}")
        for skill in skill_performance[:5]:  # Show first 5
            print(f"  - {json.dumps(skill, indent=4)}")
    elif isinstance(skill_performance, dict):
        print(f"  Keys: {list(skill_performance.keys())}")
        for key, value in list(skill_performance.items())[:5]:
            print(f"  {key}: {json.dumps(value, indent=4)}")
    else:
        print(f"  {json.dumps(skill_performance, indent=2)}")
    
    # Check score_summary
    score_summary = analysis.get('score_summary', {})
    print(f"\nScore Summary:")
    print(f"  Percentage: {score_summary.get('percentage')}")
    print(f"  Correct: {score_summary.get('correct')}")
    print(f"  Total: {score_summary.get('total')}")
    
    # Print all available keys in analysis
    print(f"\nAll keys in analysis: {list(analysis.keys())}")
    
    # Check for skill_analysis or other skill-related fields
    if 'skill_analysis' in analysis:
        print(f"\nSkill Analysis found:")
        print(json.dumps(analysis['skill_analysis'], indent=2))
    
    # Check topic_analysis
    if 'topic_analysis' in analysis:
        print(f"\nTopic Analysis found:")
        topic_analysis = analysis['topic_analysis']
        if isinstance(topic_analysis, list):
            print(f"  Length: {len(topic_analysis)}")
            for topic in topic_analysis[:3]:  # Show first 3
                print(f"  - {json.dumps(topic, indent=4)}")
        else:
            print(json.dumps(topic_analysis, indent=2))
    
    print("="*80)

client.close()
