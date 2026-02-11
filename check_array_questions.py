from pymongo import MongoClient
from dotenv import load_dotenv
import os
import json

load_dotenv()

client = MongoClient(os.getenv('MONGODB_URI'))
db = client['Placement_Ai']
week_test_col = db['week_test']

print("=" * 100)
print("Checking for Array-related questions in weekly tests")
print("=" * 100)

# Get all documents
docs = list(week_test_col.find({}))

for doc in docs:
    _id = doc.get('_id')
    mobile = doc.get('mobile')
    questions = doc.get('questions', [])
    
    if not questions:
        # Check weekly_tests array
        if 'weekly_tests' in doc:
            for wt in doc['weekly_tests']:
                questions.extend(wt.get('questions', []))
    
    # Look for array-related questions
    array_questions = []
    for i, q in enumerate(questions):
        q_text = q.get('question', q.get('question_text', q.get('questionText', ''))).lower()
        skill = q.get('skill', q.get('topic', '')).lower()
        
        if 'array' in q_text or 'array' in skill:
            array_questions.append({
                'index': i,
                'question': q.get('question', q.get('question_text', q.get('questionText', '')))[:100],
                'skill': q.get('skill', q.get('topic', 'N/A'))
            })
    
    if array_questions:
        print(f"\n{'='*100}")
        print(f"User: {mobile}")
        print(f"Total questions: {len(questions)}")
        print(f"Array-related questions found: {len(array_questions)}")
        for aq in array_questions:
            print(f"\n  Question {aq['index'] + 1}:")
            print(f"    Skill: {aq['skill']}")
            print(f"    Text: {aq['question']}")

print("\n" + "=" * 100)
