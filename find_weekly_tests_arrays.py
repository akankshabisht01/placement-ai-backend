from pymongo import MongoClient
from dotenv import load_dotenv
import os
import json

load_dotenv()

client = MongoClient(os.getenv('MONGODB_URI'))
db = client['Placement_Ai']
week_test_col = db['week_test']

print("=" * 100)
print("Checking for weekly_tests array structure")
print("=" * 100)

# Get all documents
docs = list(week_test_col.find({}))

for doc in docs:
    _id = doc.get('_id')
    mobile = doc.get('mobile')
    
    print(f"\n{'='*100}")
    print(f"User: {mobile}")
    print(f"_id: {_id}")
    
    # Check structure
    has_weekly_tests = 'weekly_tests' in doc
    has_top_level_questions = 'questions' in doc
    
    print(f"Has weekly_tests array: {has_weekly_tests}")
    print(f"Has top-level questions: {has_top_level_questions}")
    
    if has_weekly_tests:
        weekly_tests = doc['weekly_tests']
        print(f"  weekly_tests array length: {len(weekly_tests)}")
        
        total_questions = 0
        for i, wt in enumerate(weekly_tests):
            q_count = len(wt.get('questions', []))
            total_questions += q_count
            print(f"    Element {i}: {q_count} questions (Week {wt.get('week_number', '?')}, Month {wt.get('month', '?')})")
        
        print(f"  Total questions across all weekly_tests elements: {total_questions}")
        
        # Check if only showing first element
        if len(weekly_tests) > 1:
            print(f"\n  ⚠️  WARNING: Multiple weekly_tests elements found!")
            print(f"  Current backend code only shows questions from weekly_tests[0]")
            print(f"  This means {total_questions - len(weekly_tests[0].get('questions', []))} questions are being hidden!")
    
    if has_top_level_questions:
        print(f"  Top-level questions count: {len(doc['questions'])}")

print("\n" + "=" * 100)
