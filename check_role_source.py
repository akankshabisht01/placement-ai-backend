from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

client = MongoClient(os.getenv('MONGO_URI'))
db = client['Placement_Ai']

roadmap_col = db['Roadmap_Dashboard ']

print('Checking roadmap roles...\n')

# Get all roadmaps
roadmaps = list(roadmap_col.find())

for doc in roadmaps:
    user_id = doc.get('_id', 'NO ID')
    
    # Check role field
    role = doc.get('role', 'NO ROLE FIELD')
    job_role = doc.get('job_role', 'NO job_role FIELD')
    domain = doc.get('domain', 'NO DOMAIN')
    
    print(f'User: {user_id}')
    print(f'  role field: {role}')
    print(f'  job_role field: {job_role}')
    print(f'  domain: {domain}')
    
    # Check if introduction has the data
    intro = doc.get('introduction', '')
    if intro and intro.strip().startswith('{'):
        print(f'  ⚠️ Introduction contains JSON data')
        try:
            import json
            parsed = json.loads(intro)
            if 'job_role' in parsed:
                print(f'     job_role in intro: {parsed.get("job_role")}')
        except:
            pass
    
    print()

client.close()
