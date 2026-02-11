from pymongo import MongoClient
import json

c = MongoClient('mongodb://localhost:27017/')

# Check both databases
for db_name in ['Placement_Ai', 'placement_db']:
    db = c[db_name]
    print(f'\n{"="*80}')
    print(f'DATABASE: {db_name}')
    print(f'{"="*80}')
    
    collections = db.list_collection_names()
    
    # Look for job role or course related collections
    for col_name in collections:
        if any(keyword in col_name.lower() for keyword in ['job', 'role', 'course', 'skill', 'domain']):
            print(f'\n📁 Collection: {col_name}')
            count = db[col_name].count_documents({})
            print(f'   Documents: {count}')
            
            # Check if it has NLP Engineer
            nlp_doc = db[col_name].find_one({'$or': [
                {'role': {'$regex': 'NLP', '$options': 'i'}},
                {'jobRole': {'$regex': 'NLP', '$options': 'i'}},
                {'title': {'$regex': 'NLP', '$options': 'i'}},
                {'name': {'$regex': 'NLP', '$options': 'i'}},
                {'_id': {'$regex': 'NLP', '$options': 'i'}}
            ]})
            
            if nlp_doc:
                print(f'\n   ✅ Found NLP Engineer!')
                print(json.dumps(nlp_doc, indent=2, default=str))
            else:
                # Show sample document structure
                sample = db[col_name].find_one()
                if sample:
                    print(f'   Sample fields: {list(sample.keys())}')

print(f'\n{"="*80}')
print('SEARCHING FOR ALL JOB ROLES')
print(f'{"="*80}')

# Try to find all job roles in any collection
for db_name in ['Placement_Ai', 'placement_db']:
    db = c[db_name]
    for col_name in db.list_collection_names():
        # Get a sample doc to check structure
        sample = db[col_name].find_one()
        if sample:
            for key in ['role', 'jobRole', 'job_role', 'title', 'name']:
                if key in sample:
                    all_docs = list(db[col_name].find())
                    if all_docs:
                        print(f'\n📋 {db_name}.{col_name} - Field: {key}')
                        unique_values = set()
                        for doc in all_docs:
                            val = doc.get(key)
                            if val:
                                unique_values.add(val if isinstance(val, str) else str(val))
                        for val in sorted(unique_values):
                            print(f'   - {val}')
                    break
