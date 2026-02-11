from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

# Connect to MongoDB
MONGODB_URI = os.getenv('MONGODB_URI')
client = MongoClient(MONGODB_URI)
db = client['Placement_Ai']

mobile = "+91 8864862270"

print("\n" + "="*80)
print("CHECKING RESUME SKILLS")
print("="*80 + "\n")

resume_col = db['Resume']
resume_doc = resume_col.find_one({'_id': mobile})

if resume_doc and 'skills' in resume_doc:
    skills = resume_doc['skills']
    print(f"Resume has {len(skills)} skills:\n")
    for skill in skills:
        print(f"  - {skill}")
else:
    print("No skills found in resume")

print("\n" + "="*80)
print("SKILL WEEK MAPPINGS")
print("="*80 + "\n")

mapping_col = db['skill_week_mapping']
mobile_id = ''.join(filter(str.isdigit, mobile))[-10:]
mapping_doc = mapping_col.find_one({'_id': mobile_id})

if mapping_doc and 'months' in mapping_doc:
    months = mapping_doc['months']
    print(f"Found mappings for {len(months)} months\n")
    
    all_skills_in_mappings = set()
    for month_key, month_skills in months.items():
        for skill_name in month_skills.keys():
            all_skills_in_mappings.add(skill_name)
    
    print(f"Total unique skills in mappings: {len(all_skills_in_mappings)}\n")
    
    # Check for matches
    print("MATCHING ANALYSIS:")
    print("-"*80)
    
    if resume_doc and 'skills' in resume_doc:
        resume_skills = resume_doc['skills']
        
        print("\n✅ EXACT MATCHES:")
        exact_matches = []
        for resume_skill in resume_skills:
            if resume_skill in all_skills_in_mappings:
                exact_matches.append(resume_skill)
                print(f"  - {resume_skill}")
        
        if not exact_matches:
            print("  None")
        
        print("\n🔍 RESUME SKILLS NOT IN MAPPINGS:")
        not_in_mappings = []
        for resume_skill in resume_skills:
            if resume_skill not in all_skills_in_mappings:
                not_in_mappings.append(resume_skill)
                print(f"  - {resume_skill}")
        
        if not not_in_mappings:
            print("  None")
        
        print("\n📝 CHECKING FOR PARTIAL MATCHES:")
        for resume_skill in not_in_mappings:
            partials = []
            for mapping_skill in all_skills_in_mappings:
                if resume_skill.lower() in mapping_skill.lower() or mapping_skill.lower() in resume_skill.lower():
                    partials.append(mapping_skill)
            if partials:
                print(f"  '{resume_skill}' might match:")
                for p in partials:
                    print(f"    - {p}")
else:
    print("No mappings found")

print("\n" + "="*80 + "\n")
