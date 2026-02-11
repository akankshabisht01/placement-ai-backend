from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

client = MongoClient(os.getenv('MONGODB_URI'))
db = client['Placement_Ai']

# Mobile to search
mobile = '9084117332'
mobile_with_code = '+91 9084117332'

print(f"=== Searching all collections for mobile: {mobile} or {mobile_with_code} ===\n")

collection_names = db.list_collection_names()

for collection_name in sorted(collection_names):
    collection = db[collection_name]
    
    # Try different mobile formats
    query_results = list(collection.find({
        '$or': [
            {'mobile': mobile},
            {'mobile': mobile_with_code},
            {'mobile': f'+91{mobile}'},
            {'mobile': f'91 {mobile}'},
            {'user_mobile': mobile},
            {'user_mobile': mobile_with_code}
        ]
    }))
    
    if query_results:
        print(f"✓ {collection_name}: Found {len(query_results)} documents")
        for doc in query_results:
            # Show relevant fields
            mobile_field = doc.get('mobile') or doc.get('user_mobile')
            week = doc.get('week') or doc.get('analysis', {}).get('week')
            doc_id = doc.get('_id')
            print(f"   - _id: {doc_id}, mobile: {mobile_field}, week: {week}")
