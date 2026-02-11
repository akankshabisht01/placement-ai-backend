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
print("Full structure of users with weekly_tests array")
print("="*100)

week_test_collection = db['week_test']

# Get documents with weekly_tests array
docs_with_weekly_tests = week_test_collection.find({'weekly_tests': {'$exists': True}})

for doc in docs_with_weekly_tests:
    print(f"\n{'='*100}")
    print(f"User: {doc.get('_id')}")
    print(f"{'='*100}")
    
    weekly_tests = doc.get('weekly_tests', [])
    print(f"\nTotal weeks in weekly_tests array: {len(weekly_tests)}")
    
    for idx, week_data in enumerate(weekly_tests, 1):
        print(f"\n--- Week {idx} ---")
        print(f"Week number: {week_data.get('week_number', 'N/A')}")
        print(f"Month: {week_data.get('month', 'N/A')}")
        
        questions = week_data.get('questions', [])
        print(f"Number of questions: {len(questions)}")
        
        if len(questions) > 0:
            print(f"\nFirst question details:")
            first_q = questions[0]
            print(json.dumps(first_q, indent=2))
            
            print(f"\nLast question details:")
            last_q = questions[-1]
            print(json.dumps(last_q, indent=2))
    
    print("\n" + "="*100)

print("\n" + "="*100)
