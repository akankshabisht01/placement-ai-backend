"""
Fix script to remove invalid roadmap data from week_test collection
The week_test collection should ONLY contain test questions, not roadmap data
"""

from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()

client = MongoClient(os.getenv('MONGODB_URI'))
db = client['Placement_Ai']
week_test_col = db['week_test']

print("=" * 100)
print("FIXING week_test collection - Removing roadmap data")
print("=" * 100)

# Find documents that look like roadmap data (have weekly_tests, learning_goals but no questions)
roadmap_docs = list(week_test_col.find({
    '$or': [
        {'weekly_tests': {'$exists': True}},
        {'learning_goals': {'$exists': True}},
        {'mini_project': {'$exists': True}}
    ],
    '$or': [
        {'questions': {'$exists': False}},
        {'questions': {'$size': 0}},
        {'questions': []}
    ]
}))

print(f"\nFound {len(roadmap_docs)} roadmap document(s) in week_test collection")
print("These should NOT be in week_test - they belong in a roadmap collection\n")

if len(roadmap_docs) == 0:
    print("✅ No roadmap documents found in week_test collection")
    print("=" * 100)
    exit(0)

for doc in roadmap_docs:
    mobile = doc.get('_id')
    print(f"{'='*100}")
    print(f"Removing roadmap data for: {mobile}")
    print(f"  Week: {doc.get('week')}, Month: {doc.get('month')}")
    print(f"  Fields: {', '.join([k for k in doc.keys() if k != '_id'])}")
    
    # Delete this document
    result = week_test_col.delete_one({'_id': mobile})
    
    if result.deleted_count > 0:
        print(f"  ✅ Deleted successfully")
    else:
        print(f"  ❌ Failed to delete")
    print()

print("=" * 100)
print(f"✅ Cleanup complete! Removed {len(roadmap_docs)} roadmap document(s)")
print("\n📝 Next steps for users:")
print("   1. Users should click 'Generate Weekly Test' button in dashboard")
print("   2. This will trigger N8N to create a proper test with questions")
print("   3. The test will then show the correct number of questions")
print("=" * 100)
