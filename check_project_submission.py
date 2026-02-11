"""Check the actual project submission in MongoDB"""
import os
from pymongo import MongoClient
from dotenv import load_dotenv
import json

load_dotenv()

mongo_uri = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
db_name = os.getenv('MONGODB_DB', 'Placement_Ai')

client = MongoClient(mongo_uri)
db = client[db_name]
collection = db['project_submissions']

# Get the user's submission
submission = collection.find_one({'_id': '9346333208_month_1'})

if submission:
    print("\n" + "="*80)
    print("PROJECT SUBMISSION FOUND")
    print("="*80)
    
    print(f"\n📱 Mobile: {submission.get('mobile')}")
    print(f"📅 Month: {submission.get('month')}")
    print(f"📝 Title: {submission.get('projectTitle')}")
    print(f"📄 Description: {submission.get('projectDescription')[:200]}...")
    print(f"📁 Total Files: {submission.get('totalFiles')}")
    
    print(f"\n📊 EVALUATION:")
    evaluation = submission.get('evaluation', {})
    print(f"   Score: {evaluation.get('score')}/100")
    print(f"   Grade: {evaluation.get('grade')}")
    print(f"   Title Score: {evaluation.get('title_score')}/5")
    print(f"   Description Score: {evaluation.get('description_score')}/30")
    print(f"   Files Score: {evaluation.get('files_score')}/65")
    
    print(f"\n📝 FEEDBACK:")
    feedback = evaluation.get('feedback', '')
    if feedback:
        print(f"   Length: {len(feedback)} characters")
        print(f"   Preview: {feedback[:300]}...")
    else:
        print("   ❌ NO FEEDBACK FOUND!")
    
    print(f"\n📋 FILES INFO:")
    for idx, file_info in enumerate(submission.get('filesInfo', []), 1):
        print(f"   {idx}. {file_info.get('filename')} ({file_info.get('size')} bytes)")
    
    print(f"\n✅ Evaluated By: {submission.get('evaluatedBy')}")
    
else:
    print("❌ Submission not found!")
