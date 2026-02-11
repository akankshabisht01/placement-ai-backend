from pymongo import MongoClient
import os
from dotenv import load_dotenv
import json

load_dotenv()

mongo_uri = os.getenv('MONGODB_URI')
client = MongoClient(mongo_uri)
db = client['Placement_Ai']
collection = db['Weekly_test_analysis']

print("="*100)
print("WEEKLY_TEST_ANALYSIS COLLECTION - DETAILED VIEW")
print("="*100)

count = collection.count_documents({})
print(f"\nTotal documents: {count}\n")

# Get all documents
docs = list(collection.find())

for i, doc in enumerate(docs, 1):
    print(f"\n{'='*100}")
    print(f"DOCUMENT {i}/{count}")
    print(f"{'='*100}")
    
    print(f"\n_id: {doc.get('_id')}")
    print(f"mobile: {doc.get('mobile')}")
    
    if 'analysis' in doc:
        analysis = doc['analysis']
        print(f"\n📊 ANALYSIS STRUCTURE:")
        print(f"  analysis_title: {analysis.get('analysis_title', 'N/A')}")
        print(f"  mobile: {analysis.get('mobile', 'N/A')}")
        print(f"  week: {analysis.get('week', 'N/A')}")
        print(f"  month: {analysis.get('month', 'N/A')}")
        
        if 'score_summary' in analysis:
            score = analysis['score_summary']
            print(f"\n  📈 SCORE SUMMARY:")
            print(f"    • Total Questions: {score.get('total_questions', 0)}")
            print(f"    • Correct: {score.get('correct', 0)}")
            print(f"    • Incorrect: {score.get('incorrect', 0)}")
            print(f"    • Percentage: {score.get('percentage', 0)}%")
            print(f"    • Passed: {score.get('passed', 'N/A')}")
        
        if 'topic_analysis' in analysis:
            topics = analysis['topic_analysis']
            print(f"\n  📚 TOPIC ANALYSIS ({len(topics)} topics):")
            for topic in topics:
                print(f"    • {topic.get('topic', 'Unknown')}: {topic.get('correct', 0)}/{topic.get('total', 0)} correct ({topic.get('percentage', 0)}%)")
        
        if 'overall_feedback' in analysis:
            feedback = analysis['overall_feedback'][:150]
            print(f"\n  💬 OVERALL FEEDBACK:")
            print(f"    {feedback}...")
        
        if 'recommendations' in analysis:
            recs = analysis['recommendations']
            print(f"\n  💡 RECOMMENDATIONS ({len(recs)} items):")
            for idx, rec in enumerate(recs[:3], 1):
                rec_text = rec[:100] if isinstance(rec, str) else str(rec)[:100]
                print(f"    {idx}. {rec_text}...")
        
        if 'mistake_patterns' in analysis:
            mistakes = analysis['mistake_patterns']
            print(f"\n  ❌ MISTAKE PATTERNS ({len(mistakes)} mistakes):")
            for idx, mistake in enumerate(mistakes[:5], 1):
                if isinstance(mistake, dict):
                    q = mistake.get('question', '')[:80]
                    print(f"    {idx}. Q: {q}...")
                    print(f"       Your answer: {mistake.get('user_answer', 'N/A')}")
                    print(f"       Correct: {mistake.get('correct_answer', 'N/A')}")
                else:
                    print(f"    {idx}. {str(mistake)[:100]}")
            if len(mistakes) > 5:
                print(f"    ... and {len(mistakes) - 5} more mistakes")
    
    # Check if there are other top-level fields
    other_fields = [k for k in doc.keys() if k not in ['_id', 'mobile', 'analysis']]
    if other_fields:
        print(f"\n  🔧 OTHER FIELDS: {', '.join(other_fields)}")

print("\n" + "="*100)
print("SUMMARY")
print("="*100)
print(f"\n📊 Total analyses: {count}")

# Check which users have analyses
users = {}
for doc in docs:
    mobile = doc.get('mobile', 'Unknown')
    if 'analysis' in doc:
        week = doc['analysis'].get('week', 'N/A')
        if mobile not in users:
            users[mobile] = []
        users[mobile].append(week)

print(f"\n👥 Users with analyses:")
for mobile, weeks in sorted(users.items()):
    print(f"  • {mobile}: Weeks {sorted(weeks)}")

print("\n" + "="*100)
