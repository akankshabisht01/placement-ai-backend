from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

client = MongoClient(os.getenv('MONGODB_URI'))
db = client['Placement_Ai']
analysis_collection = db['Weekly_test_analysis']

# Test mobile number
mobile = '+91 9084117332'

# Add 4 completed weeks for Month 1
test_data = [
    {
        '_id': f'{mobile}_week_1',
        'mobile': mobile,
        'analysis': {
            'week': 1,
            'month': 1,
            'score': 80,
            'total': 100
        }
    },
    {
        '_id': f'{mobile}_week_2',
        'mobile': mobile,
        'analysis': {
            'week': 2,
            'month': 1,
            'score': 75,
            'total': 100
        }
    },
    {
        '_id': f'{mobile}_week_3',
        'mobile': mobile,
        'analysis': {
            'week': 3,
            'month': 1,
            'score': 85,
            'total': 100
        }
    },
    {
        '_id': f'{mobile}_week_4',
        'mobile': mobile,
        'analysis': {
            'week': 4,
            'month': 1,
            'score': 90,
            'total': 100
        }
    }
]

# Insert or update test data
for data in test_data:
    analysis_collection.update_one(
        {'_id': data['_id']},
        {'$set': data},
        upsert=True
    )
    print(f"✓ Added/Updated: {data['_id']}")

print(f"\n✅ Added 4 weeks of analysis for {mobile}")
print("Month 1 should now be unlocked!")
print("\nTo verify, call: /api/check-month-test-eligibility/9084117332")
