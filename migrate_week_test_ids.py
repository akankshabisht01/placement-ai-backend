"""
Migration script to update _id format in week_test_answers and week_test_result collections
Old format: +91 9084117332
New format: +91 9084117332_week_1
"""

from pymongo import MongoClient
from dotenv import load_dotenv
import os
from datetime import datetime

load_dotenv()

# Connect to MongoDB
mongo_uri = os.getenv('MONGODB_URI')
if not mongo_uri:
    print("❌ MONGODB_URI not found in .env file")
    exit(1)

client = MongoClient(mongo_uri)
db = client['Placement_Ai']

print("=" * 100)
print("MIGRATION: Update _id format for week_test_answers and week_test_result collections")
print("=" * 100)
print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 100)

def migrate_collection(collection_name, get_week_func):
    """
    Migrate a collection to new _id format
    
    Args:
        collection_name: Name of the collection to migrate
        get_week_func: Function to extract week number from document
    """
    print(f"\n{'='*100}")
    print(f"Migrating Collection: {collection_name}")
    print(f"{'='*100}")
    
    collection = db[collection_name]
    
    # Find all documents
    documents = list(collection.find({}))
    print(f"📊 Found {len(documents)} document(s) to migrate")
    
    if len(documents) == 0:
        print("✅ No documents to migrate")
        return
    
    migrated_count = 0
    skipped_count = 0
    error_count = 0
    
    for doc in documents:
        old_id = doc['_id']
        
        # Check if already in new format (contains _week_)
        if '_week_' in str(old_id):
            print(f"⏭️  Skipping {old_id} - already in new format")
            skipped_count += 1
            continue
        
        # Extract week number
        week_number = get_week_func(doc)
        
        if week_number is None:
            print(f"⚠️  Warning: Could not determine week number for {old_id} - skipping")
            error_count += 1
            continue
        
        # Create new _id
        new_id = f"{old_id}_week_{week_number}"
        
        print(f"\n🔄 Migrating document:")
        print(f"   Old _id: {old_id}")
        print(f"   New _id: {new_id}")
        print(f"   Week: {week_number}")
        
        try:
            # Check if new document already exists
            existing = collection.find_one({'_id': new_id})
            if existing:
                print(f"   ⚠️  Document with new _id already exists - will delete old one only")
                # Delete old document
                collection.delete_one({'_id': old_id})
                print(f"   ✅ Deleted old document")
                migrated_count += 1
            else:
                # Create new document with new _id
                new_doc = doc.copy()
                new_doc['_id'] = new_id
                new_doc['migrated_at'] = datetime.now().isoformat()
                new_doc['old_id'] = old_id
                
                # Insert new document
                collection.insert_one(new_doc)
                print(f"   ✅ Created new document with new _id")
                
                # Delete old document
                collection.delete_one({'_id': old_id})
                print(f"   ✅ Deleted old document")
                
                migrated_count += 1
        
        except Exception as e:
            print(f"   ❌ Error migrating {old_id}: {str(e)}")
            error_count += 1
    
    print(f"\n{'='*100}")
    print(f"Migration Summary for {collection_name}:")
    print(f"  ✅ Migrated: {migrated_count}")
    print(f"  ⏭️  Skipped (already in new format): {skipped_count}")
    print(f"  ❌ Errors: {error_count}")
    print(f"  📊 Total processed: {len(documents)}")
    print(f"{'='*100}")


# Migration function for week_test_answers
def get_week_from_answers(doc):
    """Extract week number from week_test_answers document"""
    # Check if week field exists
    if 'week' in doc:
        return doc['week']
    
    # Try to get from userAnswers if available
    user_answers = doc.get('userAnswers', [])
    if user_answers and len(user_answers) > 0:
        # Week might be in the test data
        pass
    
    # Check if testType indicates it's a weekly test
    test_type = doc.get('testType', '')
    if test_type != 'weekly':
        return None
    
    # As fallback, we need to look up the week from week_test collection
    mobile = doc.get('_id')
    if mobile:
        week_test_col = db['week_test']
        week_test_doc = week_test_col.find_one({'_id': mobile})
        if week_test_doc and 'week' in week_test_doc:
            return week_test_doc['week']
    
    # Default to week 1 if we can't determine
    print(f"   ⚠️  Could not determine week, checking week_test collection...")
    return None


# Migration function for week_test_result
def get_week_from_result(doc):
    """Extract week number from week_test_result document"""
    # Check if week field exists (it should based on the sample data)
    if 'week' in doc:
        return doc['week']
    
    # Fallback: try to get from week_test collection
    mobile = doc.get('_id') or doc.get('mobile')
    if mobile:
        week_test_col = db['week_test']
        week_test_doc = week_test_col.find_one({'_id': mobile})
        if week_test_doc and 'week' in week_test_doc:
            return week_test_doc['week']
    
    return None


# Perform migrations
print("\n🚀 Starting migration process...")

# Migrate week_test_answers
migrate_collection('week_test_answers', get_week_from_answers)

# Migrate week_test_result  
migrate_collection('week_test_result', get_week_from_result)

print("\n" + "=" * 100)
print("✅ MIGRATION COMPLETE")
print("=" * 100)

# Verify the migration
print("\n📊 Verification:")
print("=" * 100)

for collection_name in ['week_test_answers', 'week_test_result']:
    collection = db[collection_name]
    all_docs = list(collection.find({}))
    new_format_count = sum(1 for doc in all_docs if '_week_' in str(doc['_id']))
    old_format_count = sum(1 for doc in all_docs if '_week_' not in str(doc['_id']))
    
    print(f"\n{collection_name}:")
    print(f"  Total documents: {len(all_docs)}")
    print(f"  New format (_id contains _week_): {new_format_count}")
    print(f"  Old format (no _week_): {old_format_count}")
    
    if len(all_docs) > 0:
        print(f"  Sample _id values:")
        for doc in all_docs[:3]:
            print(f"    - {doc['_id']}")

print("\n" + "=" * 100)
