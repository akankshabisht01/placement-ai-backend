from pymongo import MongoClient
from dotenv import load_dotenv
import os
import json

load_dotenv()

client = MongoClient(os.getenv('MONGODB_URI'))
db = client['Placement_Ai']
week_test_col = db['week_test']

print("=" * 100)
print("Detailed check for tests with 0 questions")
print("=" * 100)

# Find documents with empty questions array
empty_tests = list(week_test_col.find({'$or': [
    {'questions': {'$exists': False}},
    {'questions': {'$size': 0}},
    {'questions': []}
]}))

print(f"\nFound {len(empty_tests)} test(s) with no questions\n")

for doc in empty_tests:
    print(f"{'='*100}")
    print(f"_id: {doc.get('_id')}")
    print(f"Mobile: {doc.get('mobile')}")
    print(f"Week: {doc.get('week')}, Month: {doc.get('month')}")
    print(f"Test Title: {doc.get('test_title', 'N/A')}")
    print(f"Created At: {doc.get('created_at', 'N/A')}")
    print(f"\nAll fields in document:")
    for key, value in doc.items():
        if key != '_id':
            print(f"  {key}: {value if not isinstance(value, list) else f'[{len(value)} items]'}")
    print()

print("=" * 100)
print("\n⚠️  ISSUE: These tests exist but have NO questions!")
print("📝 This usually happens when:")
print("   1. N8N webhook failed to populate questions")
print("   2. Test was created manually without questions")
print("   3. Network error during test generation")
print("\n💡 SOLUTION:")
print("   User needs to click 'Generate Weekly Test' button again to trigger N8N")
print("=" * 100)
