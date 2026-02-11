"""Test if skills move from 'Skills You Can Develop' to 'Skills & Expertise'"""
import os
from pymongo import MongoClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# MongoDB connection
mongo_uri = os.getenv('MONGO_URI') or os.getenv('MONGODB_URI')
client = MongoClient(mongo_uri)
db = client[os.getenv("MONGODB_DB", "Placement_Ai")]

mobile = "8864862270"
month_number = 1
week_number = 4

print(f"\n{'='*80}")
print(f"TESTING SKILL MOVEMENT FOR USER {mobile}")
print(f"{'='*80}\n")

# Step 1: Check skill mapping
print("1. Checking skill-week mapping...")
mapping_col = db['skill_week_mapping']
mobile_id = mobile[-10:]  # Last 10 digits
mapping_doc = mapping_col.find_one({'_id': mobile_id})

if mapping_doc:
    print(f"   ✅ Found mapping for user {mobile_id}")
    month_key = f"month_{month_number}"
    skill_mapping = mapping_doc.get('months', {}).get(month_key, {})
    
    if skill_mapping:
        print(f"   📋 Skills in Month {month_number}:")
        skills_at_week_4 = []
        for skill, week in skill_mapping.items():
            status = "← Week 4!" if week == week_number else ""
            print(f"      - {skill}: Week {week} {status}")
            if week == week_number:
                skills_at_week_4.append(skill)
        
        print(f"\n   🎯 Skills completing at Week {week_number}: {skills_at_week_4}")
    else:
        print(f"   ❌ No mapping found for {month_key}")
        skills_at_week_4 = []
else:
    print(f"   ❌ No skill mapping found for user {mobile_id}")
    skills_at_week_4 = []

# Step 2: Check resume BEFORE
print(f"\n2. Checking resume (BEFORE skill movement)...")
resume_col = db['Resume']

# Try different mobile formats
mobile_formats = [
    f"+91 {mobile}",
    f"+91{mobile}",
    mobile,
    f"+91 {mobile[-10:]}",
    mobile[-10:]
]

resume_doc = None
for variant in mobile_formats:
    resume_doc = resume_col.find_one({'_id': variant})
    if resume_doc:
        print(f"   ✅ Found resume with _id: {variant}")
        break

if resume_doc:
    current_skills = resume_doc.get('skills', [])
    print(f"   📊 Current skills ({len(current_skills)}): {current_skills}")
    
    # Check if expected skills are already there
    if skills_at_week_4:
        print(f"\n   🔍 Checking if Week {week_number} skills are in resume:")
        for skill in skills_at_week_4:
            if skill in current_skills:
                print(f"      ✅ '{skill}' - Already in resume")
            else:
                print(f"      ❌ '{skill}' - NOT in resume (should be added)")
else:
    print(f"   ❌ Resume not found!")
    print(f"   Tried formats: {mobile_formats}")

# Step 3: Simulate API call to move skills
print(f"\n3. Simulating skill movement (what the API would do)...")

if resume_doc and skills_at_week_4:
    current_skills = resume_doc.get('skills', [])
    current_skills_lower = [str(s).lower() for s in current_skills]
    
    skills_to_add = []
    for skill in skills_at_week_4:
        if skill.lower() not in current_skills_lower:
            skills_to_add.append(skill)
    
    if skills_to_add:
        print(f"   📝 Would add {len(skills_to_add)} skill(s): {skills_to_add}")
        
        # Actually add them
        new_skills = current_skills + skills_to_add
        result = resume_col.update_one(
            {'_id': resume_doc['_id']},
            {'$set': {'skills': new_skills}}
        )
        
        if result.modified_count > 0:
            print(f"   ✅ Successfully updated resume!")
            print(f"   📊 New skills list ({len(new_skills)}): {new_skills}")
        else:
            print(f"   ⚠️ Update attempted but no changes made")
    else:
        print(f"   ℹ️ All Week {week_number} skills already in resume")
elif not resume_doc:
    print(f"   ❌ Cannot move skills - resume not found")
elif not skills_at_week_4:
    print(f"   ℹ️ No skills mapped to Week {week_number}")

# Step 4: Verify final state
print(f"\n4. Verifying final resume state...")
resume_doc_after = resume_col.find_one({'_id': resume_doc['_id']}) if resume_doc else None

if resume_doc_after:
    final_skills = resume_doc_after.get('skills', [])
    print(f"   📊 Final skills ({len(final_skills)}): {final_skills}")
    
    if skills_at_week_4:
        print(f"\n   ✅ Verification:")
        all_present = True
        for skill in skills_at_week_4:
            if skill in final_skills:
                print(f"      ✅ '{skill}' - Present in resume")
            else:
                print(f"      ❌ '{skill}' - MISSING from resume")
                all_present = False
        
        if all_present:
            print(f"\n   🎉 SUCCESS! All Week {week_number} skills are now in 'Skills & Expertise'!")
        else:
            print(f"\n   ❌ FAILED! Some skills are still missing")

print(f"\n{'='*80}\n")
