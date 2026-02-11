from pymongo import MongoClient
from dotenv import load_dotenv
import os
import json

load_dotenv()

client = MongoClient(os.getenv('MONGODB_URI'))
db = client['Placement_Ai']
week_test_col = db['week_test']

print("=" * 100)
print("Checking week_test collection for all users")
print("=" * 100)

# Get all documents
docs = list(week_test_col.find({}))

print(f"\nTotal documents: {len(docs)}\n")

for doc in docs:
    _id = doc.get('_id')
    mobile = doc.get('mobile')
    week = doc.get('week')
    month = doc.get('month')
    questions = doc.get('questions', [])
    test_title = doc.get('test_title', 'N/A')
    
    print(f"{'='*100}")
    print(f"_id: {_id}")
    print(f"Mobile: {mobile}")
    print(f"Week: {week}, Month: {month}")
    print(f"Test Title: {test_title}")
    print(f"Number of questions: {len(questions)}")
    
    if len(questions) == 0:
        print("⚠️  WARNING: This test has NO QUESTIONS!")
    elif len(questions) > 0:
        print(f"✅ First question preview: {questions[0].get('question_text', questions[0].get('question', 'N/A'))[:100]}")
    
    print()

print("=" * 100)
