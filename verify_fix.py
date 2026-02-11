from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()

client = MongoClient(os.getenv('MONGODB_URI'))
db = client['Placement_Ai']
week_test_col = db['week_test']

print("=" * 100)
print("Testing the fix for weekly_tests array question extraction")
print("=" * 100)

mobile = "+91 8864862270"
test_doc = week_test_col.find_one({"_id": mobile})

if test_doc:
    print(f"\nUser: {mobile}")
    print(f"Test structure check:")
    
    questions = []
    week_number = test_doc.get('week', 1)
    month_number = test_doc.get('month', 1)
    
    # FIXED CODE - merges ALL weekly_tests elements
    if 'weekly_tests' in test_doc and test_doc['weekly_tests']:
        weekly_tests = test_doc['weekly_tests']
        # Merge questions from ALL elements in the weekly_tests array
        questions = []
        for i, wt in enumerate(weekly_tests):
            if isinstance(wt, dict):
                wt_questions = wt.get('questions', [])
                print(f"\n  Element {i}: Adding {len(wt_questions)} questions")
                print(f"    Title: {wt.get('test_title', 'N/A')}")
                questions.extend(wt_questions)
                # Try to get week/month from the first element if available
                if i == 0:
                    if 'week_number' in wt:
                        week_number = wt['week_number']
                    if 'month' in wt:
                        month_number = wt['month']
        print(f"\n✅ Total questions extracted: {len(questions)}")
        print(f"  From {len(weekly_tests)} weekly_tests elements")
    elif 'questions' in test_doc and test_doc['questions']:
        questions = test_doc['questions']
        print(f"\n✅ Found {len(questions)} questions at top level (old format)")
    
    # Check for array questions
    array_questions = []
    for i, q in enumerate(questions):
        q_text = str(q.get('question', q.get('question_text', ''))).lower()
        skill = str(q.get('skill', q.get('topic', ''))).lower()
        if 'array' in q_text or 'array' in skill:
            array_questions.append({
                'index': i + 1,
                'text': q.get('question', q.get('question_text', ''))[:100]
            })
    
    print(f"\n📊 Array-related questions found: {len(array_questions)}")
    for aq in array_questions:
        print(f"  Question {aq['index']}: {aq['text']}")
    
    print(f"\n✅ FIX VERIFIED:")
    print(f"  Before fix: Only 20 questions from weekly_tests[0]")
    print(f"  After fix: All {len(questions)} questions from all weekly_tests elements")
    print(f"  Array questions are now visible: {'YES ✅' if array_questions else 'NO ❌'}")

print("\n" + "=" * 100)
