from pymongo import MongoClient
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Connect to MongoDB
mongo_uri = os.getenv('MONGODB_URI')
client = MongoClient(mongo_uri)
db = client['Placement_Ai']

print("="*100)
print("Checking weekly_tests array in week_test collection")
print("="*100)

week_test_collection = db['week_test']

# Get all documents
all_docs = list(week_test_collection.find({}))

print(f"\nTotal documents: {len(all_docs)}\n")

for doc in all_docs:
    print("="*100)
    print(f"_id: {doc.get('_id', 'N/A')}")
    print(f"Mobile: {doc.get('mobile', 'N/A')}")
    
    # Check if weekly_tests exists
    if 'weekly_tests' in doc:
        weekly_tests = doc['weekly_tests']
        print(f"✅ Has weekly_tests array: {len(weekly_tests)} weeks")
        
        # Iterate through each week
        for week_num, week_data in enumerate(weekly_tests, 1):
            print(f"\n  Week {week_num}:")
            
            # Check if questions exist in this week
            if isinstance(week_data, dict) and 'questions' in week_data:
                questions = week_data['questions']
                print(f"    ✅ Has questions array: {len(questions)} questions")
                
                if len(questions) > 0:
                    print(f"    📝 First question: {questions[0][:100] if isinstance(questions[0], str) else str(questions[0])[:100]}")
            else:
                print(f"    ❌ No questions field in this week")
                print(f"    Available fields: {list(week_data.keys()) if isinstance(week_data, dict) else 'Not a dict'}")
    else:
        print("❌ No weekly_tests array")
        
        # Check if regular questions array exists
        if 'questions' in doc:
            print(f"✅ Has regular questions array: {len(doc['questions'])} questions")
        else:
            print(f"Available top-level fields: {list(doc.keys())}")
    
    print()

print("="*100)
