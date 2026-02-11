from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

client = MongoClient(os.getenv('MONGO_URI'))
db = client['Placement_Ai']
weekly_col = db['weekly_plans']

count = weekly_col.count_documents({})
print(f'Total weekly plans in database: {count}')

if count > 0:
    sample = weekly_col.find_one()
    print(f'Sample mobile: {sample.get("mobile")}')
    print(f'Months available: {list(sample.get("months", {}).keys())}')
else:
    print('\nNo weekly plans have been generated yet.')
    print('Weekly plans are created when users switch to Weekly View for the first time.')

client.close()
