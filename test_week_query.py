from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

mongo_uri = os.getenv('MONGODB_URI')
client = MongoClient(mongo_uri)
db = client['Placement_Ai']
result_collection = db['week_test_result']

print("All documents in week_test_result:")
print("="*80)
for doc in result_collection.find():
    print(f"_id: {doc['_id']}")
    print(f"mobile: '{doc['mobile']}'")
    print(f"week: {doc.get('week')}, month: {doc.get('month')}, testType: {doc.get('testType')}")
    print("-"*80)

