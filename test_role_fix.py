from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

client = MongoClient(os.getenv('MONGO_URI'))
db = client['Placement_Ai']

# Test with a specific user
mobile = '+91 6396428243'

# Clean mobile number
clean_mobile = ''.join(filter(str.isdigit, mobile))
mobile_formats = [
    mobile,
    clean_mobile,
    clean_mobile[-10:],
    f"+91 {clean_mobile[-10:]}",
    f"+91{clean_mobile[-10:]}"
]
mobile_formats = list(dict.fromkeys(mobile_formats))

print(f'Testing with mobile: {mobile}')
print(f'Mobile formats: {mobile_formats}\n')

# Get Resume
resume_collection = db['Resume']
user_resume = resume_collection.find_one({'_id': {'$in': mobile_formats}})

if user_resume:
    print('✅ Found Resume!')
    
    job_selection = user_resume.get('jobSelection', {})
    job_role_skills = user_resume.get('jobRoleSkills', {})
    
    print(f'\njobSelection type: {type(job_selection)}')
    print(f'jobSelection: {job_selection}')
    
    if isinstance(job_selection, dict):
        user_job_role = job_selection.get('jobRole')
        user_job_domain = job_selection.get('jobDomain')
        print(f'\n✅ Extracted from jobSelection:')
        print(f'   Role: {user_job_role}')
        print(f'   Domain: {user_job_domain}')
        
        if user_job_role:
            formatted_role = user_job_role.replace('_', ' ').title()
            formatted_domain = user_job_domain.replace('_', ' ').title() if user_job_domain else None
            print(f'\n📋 Final formatted:')
            print(f'   Role: {formatted_role}')
            print(f'   Domain: {formatted_domain}')
else:
    print('❌ Resume not found!')

client.close()
