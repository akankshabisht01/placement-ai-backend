from pymongo import MongoClient
import os
from dotenv import load_dotenv
import json

load_dotenv()

client = MongoClient(os.getenv('MONGO_URI'))
db = client['Placement_Ai']

resume_col = db['Resume']

print('Checking Resume collection for job role fields...\n')

# Get all resumes
resumes = list(resume_col.find())

for doc in resumes:
    user_id = doc.get('_id', 'NO ID')
    
    print(f'User: {user_id}')
    
    # Check all possible job role field names
    job_selection = doc.get('jobSelection')
    job_role_skills = doc.get('jobRoleSkills')
    job_role = doc.get('job_role')
    role = doc.get('role')
    target_role = doc.get('target_role')
    desired_role = doc.get('desired_role')
    
    print(f'  jobSelection: {job_selection}')
    print(f'  jobRoleSkills: {job_role_skills}')
    print(f'  job_role: {job_role}')
    print(f'  role: {role}')
    print(f'  target_role: {target_role}')
    print(f'  desired_role: {desired_role}')
    
    # Check domain fields
    domain = doc.get('domain')
    job_domain = doc.get('job_domain')
    target_domain = doc.get('target_domain')
    
    print(f'  domain: {domain}')
    print(f'  job_domain: {job_domain}')
    print(f'  target_domain: {target_domain}')
    
    print()

client.close()
