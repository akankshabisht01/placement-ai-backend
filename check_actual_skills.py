from pymongo import MongoClient
import json

c = MongoClient('mongodb://localhost:27017/')
db_placement = c['Placement_Ai']
db_other = c['placement_db']

print('Placement_Ai collections:', db_placement.list_collection_names())
print('placement_db collections:', db_other.list_collection_names())

# Check for resume
mobile_variants = ['+918864862270', '8864862270', '+91 8864862270']
resume = None
for variant in mobile_variants:
    resume = db_other['resumes'].find_one({'mobile': variant})
    if resume:
        print(f'\n✅ Resume found with mobile: {variant}')
        break

if not resume:
    # Try finding any resume
    all_resumes = list(db_other['resumes'].find().limit(5))
    print(f'\n❌ No resume found for {mobile_variants[0]}')
    print(f'Total resumes in collection: {db_other["resumes"].count_documents({})}')
    if all_resumes:
        print('\nSample resume IDs:')
        for r in all_resumes:
            print(f'  - {r.get("_id")} / {r.get("mobile")}')
else:
    print('\n' + '='*80)
    print('YOUR ACTUAL SKILLS FROM RESUME:')
    print('='*80)
    
    # Check different possible skill field names
    skill_fields = ['skills', 'Skills', 'skillsAndExpertise', 'skills_expertise']
    
    for field in skill_fields:
        if field in resume:
            skills = resume[field]
            print(f'\nField: {field}')
            if isinstance(skills, list):
                for skill in skills:
                    print(f'  - {skill}')
            elif isinstance(skills, dict):
                print(f'  {json.dumps(skills, indent=2)}')
            else:
                print(f'  {skills}')
    
    # Print all resume fields to see structure
    print('\n' + '='*80)
    print('RESUME STRUCTURE (all fields):')
    print('='*80)
    for key in resume.keys():
        if key not in ['_id']:
            print(f'  - {key}')
