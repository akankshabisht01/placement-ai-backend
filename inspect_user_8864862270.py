from pymongo import MongoClient
from dotenv import load_dotenv
import os
import json

load_dotenv()

client = MongoClient(os.getenv('MONGODB_URI'))
db = client['Placement_Ai']
week_test_col = db['week_test']

print("=" * 100)
print("Detailed inspection of user +91 8864862270")
print("=" * 100)

doc = week_test_col.find_one({"_id": "+91 8864862270"})

if doc:
    print(f"\nUser: {doc.get('mobile')}")
    print(f"Week: {doc.get('week')}, Month: {doc.get('month')}")
    print(f"Test Title: {doc.get('test_title', 'N/A')}")
    
    if 'weekly_tests' in doc:
        weekly_tests = doc['weekly_tests']
        print(f"\nweekly_tests array has {len(weekly_tests)} elements:\n")
        
        for i, wt in enumerate(weekly_tests):
            print(f"{'='*80}")
            print(f"Element {i}:")
            print(f"  week_number: {wt.get('week_number', 'N/A')}")
            print(f"  month: {wt.get('month', 'N/A')}")
            print(f"  test_title: {wt.get('test_title', 'N/A')}")
            print(f"  questions count: {len(wt.get('questions', []))}")
            
            # Show first 3 questions from each element
            questions = wt.get('questions', [])
            if questions:
                print(f"\n  First few questions from this element:")
                for j, q in enumerate(questions[:3]):
                    print(f"\n    Question {j + 1}:")
                    print(f"      Skill: {q.get('skill', q.get('topic', 'N/A'))}")
                    print(f"      Text: {q.get('question', q.get('question_text', 'N/A'))[:100]}")
            
            # Check for array-related questions
            array_qs = [q for q in questions if 'array' in str(q.get('question', q.get('question_text', ''))).lower() or 'array' in str(q.get('skill', q.get('topic', ''))).lower()]
            if array_qs:
                print(f"\n  ⭐ ARRAY-related questions in this element: {len(array_qs)}")
                for aq in array_qs:
                    print(f"    - {aq.get('question', aq.get('question_text', ''))[:80]}")
        
        print(f"\n{'='*80}")
        print(f"\n🔥 PROBLEM IDENTIFIED:")
        print(f"  Current backend code only loads questions from weekly_tests[0]")
        print(f"  So only {len(weekly_tests[0].get('questions', []))} questions out of {sum(len(wt.get('questions', [])) for wt in weekly_tests)} total are shown!")
else:
    print("❌ User not found")
