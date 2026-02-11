from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

client = MongoClient(os.getenv('MONGODB_URI'))
db = client['Placement_Ai']

# Try different mobile formats
formats = [
    '+91 9084117332',
    '+919084117332',
    '9084117332',
    '91 9084117332'
]

print("=== Searching Weekly_test_analysis ===")
for mobile_format in formats:
    docs = list(db['Weekly_test_analysis'].find({'mobile': mobile_format}))
    print(f"\nFormat: '{mobile_format}' -> Found {len(docs)} documents")
    for doc in docs:
        week = doc.get('analysis', {}).get('week')
        print(f"  - Mobile: {doc.get('mobile')}, Week: {week}")

print("\n=== All documents in Weekly_test_analysis ===")
all_docs = list(db['Weekly_test_analysis'].find())
print(f"Total documents: {len(all_docs)}")
for doc in all_docs:
    mobile = doc.get('mobile')
    week = doc.get('analysis', {}).get('week')
    print(f"  - Mobile: '{mobile}', Week: {week}")
