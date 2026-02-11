"""
Fix combined skills in Resume collection by splitting them into individual skills
Example: "Machine Learning Models & scikit-learn" -> ["Machine Learning Models", "scikit-learn"]
"""

from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

def split_combined_skills(skills_list):
    """Split any combined skills (containing ' & ') into individual skills"""
    if not isinstance(skills_list, list):
        return skills_list
    
    new_skills = []
    for skill in skills_list:
        if isinstance(skill, str) and ' & ' in skill:
            # Split and add individual skills
            individual_skills = [s.strip() for s in skill.split(' & ')]
            new_skills.extend(individual_skills)
        else:
            new_skills.append(skill)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_skills = []
    for skill in new_skills:
        skill_lower = skill.lower()
        if skill_lower not in seen:
            seen.add(skill_lower)
            unique_skills.append(skill)
    
    return unique_skills

def main():
    mongo_uri = os.getenv('MONGO_URI') or os.getenv('MONGODB_URI')
    if not mongo_uri:
        print("❌ MongoDB URI not found in environment variables")
        return
    
    client = MongoClient(mongo_uri)
    db = client[os.getenv("MONGODB_DB", "Placement_Ai")]
    resume_col = db['Resume']
    
    print("🔍 Searching for resumes with combined skills...")
    print("="*60)
    
    # Find all resumes with skills
    resumes = resume_col.find({'skills': {'$exists': True}})
    
    updated_count = 0
    for resume in resumes:
        skills = resume.get('skills', [])
        
        # Check if any skill contains ' & '
        has_combined = any(isinstance(s, str) and ' & ' in s for s in skills)
        
        if has_combined:
            original_skills = skills.copy()
            new_skills = split_combined_skills(skills)
            
            print(f"\n📱 User: {resume['_id']}")
            print(f"   Before: {original_skills}")
            print(f"   After:  {new_skills}")
            
            # Update the resume
            result = resume_col.update_one(
                {'_id': resume['_id']},
                {'$set': {'skills': new_skills}}
            )
            
            if result.modified_count > 0:
                updated_count += 1
                print(f"   ✅ Updated!")
            else:
                print(f"   ⚠️ No changes made")
    
    print("\n" + "="*60)
    print(f"✅ Updated {updated_count} resume(s)")
    
    # Show updated data for test user
    print("\n" + "="*60)
    print("Verifying test user (8864862270):")
    test_resume = resume_col.find_one({'_id': '+91 8864862270'})
    if test_resume:
        print(f"Skills: {test_resume.get('skills', [])}")
    else:
        print("Not found")

if __name__ == '__main__':
    main()
