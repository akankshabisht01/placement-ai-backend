import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

# MongoDB connection
mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
db_name = os.getenv('MONGODB_DB', 'Placement_Ai')
client = MongoClient(mongo_uri)
db = client[db_name]

mobile = "+91 8864862270"

print(f"\n{'='*80}")
print(f"CHECKING COMPLETED WEEKLY TESTS FOR: {mobile}")
print(f"{'='*80}\n")

# Check Weekly_test_analysis collection
weekly_col = db['Weekly_test_analysis']
weekly_tests = list(weekly_col.find({'mobile': mobile}).sort('_id', 1))

print(f"📊 Total Weekly Test Records Found: {len(weekly_tests)}\n")

if weekly_tests:
    print("Completed Tests:")
    print("-" * 80)
    for test in weekly_tests:
        month = test.get('analysis', {}).get('month', 'N/A')
        week = test.get('analysis', {}).get('week', 'N/A')
        score_summary = test.get('analysis', {}).get('score_summary', {})
        percentage = score_summary.get('percentage', 0)
        
        # Get skillPerformance topics
        skill_perf = test.get('skillPerformance', {})
        topics = list(skill_perf.keys()) if skill_perf else []
        
        print(f"\n📝 {test.get('_id', 'N/A')}")
        print(f"   Month: {month}, Week: {week}")
        print(f"   Overall Score: {percentage}%")
        print(f"   Topics Tested: {len(topics)}")
        if topics:
            for topic in topics[:3]:  # Show first 3 topics
                topic_data = skill_perf[topic]
                print(f"      - {topic}: {topic_data.get('percentage', 0)}% ({topic_data.get('correct', 0)}/{topic_data.get('total', 0)} correct)")
            if len(topics) > 3:
                print(f"      ... and {len(topics) - 3} more topics")
else:
    print("❌ No weekly test records found!")

print("\n" + "="*80)
print(f"SUMMARY: {len(weekly_tests)} weeks completed")
print("="*80)
