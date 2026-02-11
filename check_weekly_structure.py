from pymongo import MongoClient
import os
from dotenv import load_dotenv
import json

load_dotenv()

client = MongoClient(os.getenv('MONGO_URI'))
db = client['Placement_Ai']

weekly_col = db['weekly_plans']
doc = weekly_col.find_one()

print('WEEKLY PLAN STRUCTURE:')
print(json.dumps({k: type(v).__name__ for k, v in doc.items()}, indent=2))

print('\n\nFull document keys:', list(doc.keys()))
print(f'\n_id type: {type(doc.get("_id"))}')
print(f'_id value: {doc.get("_id")}')

# Check if _id might be the mobile
_id = str(doc.get('_id'))
print(f'\n_id as string: {_id}')

# Show sample month data
months = doc.get('months', {})
if 'month_1' in months:
    week_1 = months['month_1'].get('week_1', {})
    print(f'\n\nMonth 1, Week 1 sample:')
    print(f'  Topics: {week_1.get("topics", [])[:3]}')
    print(f'  Learning goal: {week_1.get("learning_goal", "")[:100]}')

client.close()
