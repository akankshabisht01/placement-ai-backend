from pymongo import MongoClient
from dotenv import load_dotenv
import os
import json

load_dotenv()

client = MongoClient(os.getenv('MONGODB_URI'))
db = client['Placement_Ai']
collection = db['week_test_result']

print("=" * 100)
print("Checking skill-wise breakdown in week_test_result")
print("=" * 100)

# Get a sample document
doc = collection.find_one({"_id": "+91 8864862270"})

if doc:
    print(f"\nUser: {doc.get('mobile')}")
    print(f"Week: {doc.get('week')}, Month: {doc.get('month')}")
    print(f"\n📊 OVERALL SCORE:")
    print(f"   scorePercentage: {doc.get('scorePercentage')}%")
    print(f"   totalScore: {doc.get('totalScore')}/{doc.get('maxPossibleScore')}")
    
    # Check if skill-wise performance exists
    if 'skillPerformance' in doc:
        print(f"\n✅ SKILL-WISE BREAKDOWN EXISTS:")
        skill_perf = doc['skillPerformance']
        for skill, data in skill_perf.items():
            print(f"\n   Skill: {skill}")
            print(f"      Percentage: {data.get('percentage')}%")
            print(f"      Score: {data.get('score')}/{data.get('maxScore')}")
            print(f"      Correct: {data.get('correct')}/{data.get('total')} questions")
    else:
        print(f"\n❌ NO skill-wise breakdown - only overall score exists")
    
    # Check detailed results
    if 'detailedResults' in doc:
        print(f"\n📋 DETAILED RESULTS:")
        detailed = doc['detailedResults']
        print(f"   Total questions: {len(detailed)}")
        
        # Show unique skills
        skills_in_questions = set()
        for q in detailed[:5]:  # Show first 5
            skill = q.get('skill', 'N/A')
            skills_in_questions.add(skill)
            print(f"   - Q: {q.get('question', 'N/A')[:60]}...")
            print(f"     Skill: {skill}, Correct: {q.get('isCorrect')}, Marks: {q.get('marksEarned')}/{q.get('marks')}")
        
        print(f"\n   Unique skills in questions: {skills_in_questions}")
    
    print("\n" + "=" * 100)
    print("KEY FINDINGS:")
    print("=" * 100)
    
    has_skill_breakdown = 'skillPerformance' in doc
    
    if has_skill_breakdown:
        print("✅ The system DOES track skill-wise scores separately!")
        print("   Each skill/topic has its own percentage based on questions tagged with that skill")
    else:
        print("❌ The system only stores OVERALL week score")
        print("   All skills in that week would get the same percentage")

else:
    print("❌ No document found")

print("\n" + "=" * 100)
