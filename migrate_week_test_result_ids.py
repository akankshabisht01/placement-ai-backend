"""
Migration Script: Update week_test_result _id format
FROM: +91 8864862270_week_2
TO:   +91 8864862270

This removes the _week_N suffix from document _ids.
For users with multiple week results, keeps the most recent one.
"""
from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()

client = MongoClient(os.getenv('MONGODB_URI'))
db = client['Placement_Ai']
collection = db['week_test_result']

print("=" * 100)
print("MIGRATION: Update week_test_result _id format")
print("FROM: mobile_week_N  →  TO: mobile")
print("=" * 100)

# Get all existing documents
docs = list(collection.find({}))
print(f"\nFound {len(docs)} documents to process\n")

# Group by mobile number
mobile_groups = {}
for doc in docs:
    _id = doc.get('_id')
    mobile = doc.get('mobile')
    
    # Extract base mobile (without _week_N)
    if '_week_' in str(_id):
        base_mobile = _id.split('_week_')[0]
    else:
        base_mobile = _id
    
    if base_mobile not in mobile_groups:
        mobile_groups[base_mobile] = []
    
    mobile_groups[base_mobile].append(doc)

print(f"Grouped into {len(mobile_groups)} unique mobile numbers:\n")

# Process each mobile group
for base_mobile, docs_list in mobile_groups.items():
    print(f"{'='*100}")
    print(f"Mobile: {base_mobile}")
    print(f"Documents found: {len(docs_list)}")
    
    if len(docs_list) == 1:
        # Single document - just update _id if needed
        doc = docs_list[0]
        old_id = doc.get('_id')
        
        if '_week_' in str(old_id):
            print(f"  Old _id: {old_id}")
            print(f"  New _id: {base_mobile}")
            
            # Create new document with updated _id
            new_doc = doc.copy()
            new_doc['_id'] = base_mobile
            
            # Insert new document
            try:
                collection.insert_one(new_doc)
                print(f"  ✅ Created new document with _id={base_mobile}")
                
                # Delete old document
                collection.delete_one({'_id': old_id})
                print(f"  ✅ Deleted old document with _id={old_id}")
            except Exception as e:
                print(f"  ❌ Error: {str(e)}")
        else:
            print(f"  ℹ️  Already in correct format: {old_id}")
    
    else:
        # Multiple documents - keep the most recent
        print(f"  Multiple documents found - keeping most recent")
        
        # Sort by savedAt (most recent first)
        sorted_docs = sorted(docs_list, key=lambda x: x.get('savedAt', ''), reverse=True)
        
        most_recent = sorted_docs[0]
        old_docs = sorted_docs[1:]
        
        print(f"  Most recent: {most_recent.get('_id')} (Week {most_recent.get('week')}, saved {most_recent.get('savedAt', 'N/A')})")
        
        # Create new document with base mobile as _id
        new_doc = most_recent.copy()
        new_doc['_id'] = base_mobile
        
        try:
            # Insert or update the new format document
            collection.replace_one(
                {'_id': base_mobile},
                new_doc,
                upsert=True
            )
            print(f"  ✅ Created/updated document with _id={base_mobile}")
            
            # Delete all old documents (including the one we just migrated)
            for old_doc in docs_list:
                old_id = old_doc.get('_id')
                if old_id != base_mobile:
                    collection.delete_one({'_id': old_id})
                    print(f"  ✅ Deleted old document: {old_id}")
        except Exception as e:
            print(f"  ❌ Error: {str(e)}")

print("\n" + "=" * 100)
print("MIGRATION COMPLETE")
print("=" * 100)

# Verify the results
final_docs = list(collection.find({}))
print(f"\nFinal document count: {len(final_docs)}")
print("\nFinal documents:")
for doc in final_docs:
    print(f"  _id: {doc.get('_id')} | Week: {doc.get('week')} | Month: {doc.get('month')} | Saved: {doc.get('savedAt', 'N/A')[:19]}")

print("\n" + "=" * 100)
