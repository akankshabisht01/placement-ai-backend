"""
Debug: Check what data we're getting from Weekly_test_analysis
"""
import os
from pymongo import MongoClient
from dotenv import load_dotenv
import json

load_dotenv()

mongo_uri = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
db_name = os.getenv('MONGODB_DB', 'Placement_Ai')

client = MongoClient(mongo_uri)
db = client[db_name]

mobile = "+91 8864862270"

# Get one week's data
week_analysis_col = db['Weekly_test_analysis']
docs = list(week_analysis_col.find({'mobile': mobile}))

if docs:
    doc = docs[0]  # First week
    analysis = doc.get('analysis', {})
    
    print("Month:", analysis.get('month'))
    print("Week:", analysis.get('week'))
    print("\nScore Summary:")
    print(json.dumps(analysis.get('score_summary', {}), indent=2))
    
    print("\nTopic Analysis:")
    for topic in analysis.get('topic_analysis', []):
        print(f"  - Topic: {topic.get('topic')}")
        print(f"    Accuracy: {topic.get('accuracy_percentage')}%")
        print()

client.close()
