from pymongo import MongoClient
from dotenv import load_dotenv
import os
import json

load_dotenv()

client = MongoClient(os.getenv('MONGODB_URI'))
db = client['Placement_Ai']
week_test_col = db['week_test']

print("=" * 100)
print("Inspecting week_test collection structure")
print("=" * 100)

# Get a sample document
doc = week_test_col.find_one({"_id": "+91 9346333208"})  # User with 40 questions

if doc:
    print(f"\n_id: {doc.get('_id')}")
    print(f"Mobile: {doc.get('mobile')}")
    print(f"Week: {doc.get('week')}, Month: {doc.get('month')}")
    print(f"Test Title: {doc.get('test_title', 'N/A')}")
    
    # Check if weekly_tests array exists
    if 'weekly_tests' in doc:
        print(f"\n✅ WEEKLY_TESTS ARRAY EXISTS!")
        print(f"Number of elements in weekly_tests array: {len(doc['weekly_tests'])}")
        
        for i, wt in enumerate(doc['weekly_tests']):
            print(f"\n  Element {i}:")
            print(f"    week_number: {wt.get('week_number', 'N/A')}")
            print(f"    month: {wt.get('month', 'N/A')}")
            print(f"    test_title: {wt.get('test_title', 'N/A')}")
            print(f"    questions count: {len(wt.get('questions', []))}")
            if wt.get('questions'):
                first_q = wt['questions'][0]
                print(f"    First question: {first_q.get('question', first_q.get('question_text', 'N/A'))[:80]}")
    else:
        print(f"\n⚠️  NO weekly_tests array found")
    
    # Check if top-level questions exist
    if 'questions' in doc:
        print(f"\n✅ TOP-LEVEL QUESTIONS EXIST!")
        print(f"Number of top-level questions: {len(doc['questions'])}")
        if doc['questions']:
            first_q = doc['questions'][0]
            print(f"First question: {first_q.get('question', first_q.get('question_text', 'N/A'))[:80]}")
    else:
        print(f"\n⚠️  NO top-level questions found")
        
    print("\n" + "=" * 100)
    print("FULL DOCUMENT STRUCTURE (keys only):")
    print(json.dumps(list(doc.keys()), indent=2))
else:
    print("❌ No document found")
