from pymongo import MongoClient

c = MongoClient('mongodb://localhost:27017/')

for db_name in ['Placement_Ai', 'placement_db']:
    db = c[db_name]
    collections = db.list_collection_names()
    print(f'\n{db_name}:')
    print(f'  Collections ({len(collections)}): {collections}')
    
    if 'week_test_result' in collections:
        count = db.week_test_result.count_documents({})
        print(f'  week_test_result documents: {count}')
        if count > 0:
            doc = db.week_test_result.find_one()
            print(f'  Sample _id: {doc["_id"]}')
