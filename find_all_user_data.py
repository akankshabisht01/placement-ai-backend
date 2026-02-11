"""Find all resume-related data for this user"""
import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

mongo_uri = os.getenv('MONGO_URI') or os.getenv('MONGODB_URI')
client = MongoClient(mongo_uri)
db = client[os.getenv("MONGODB_DB", "Placement_Ai")]

mobile = "8864862270"

print("\n" + "="*80)
print(f"FINDING ALL DATA FOR USER {mobile}")
print("="*80 + "\n")

# Collections to check
collections_to_check = [
    'Resume',
    'student_analysis',
    'Student_Analysis',
    'resume_analysis',
    'Resume_Analysis',
    'students',
    'Students'
]

mobile_formats = [
    mobile,
    f"+91 {mobile}",
    f"+91{mobile}",
    mobile[-10:],
    f"+91 {mobile[-10:]}"
]

print("🔍 Checking these collections:")
for col_name in collections_to_check:
    print(f"   - {col_name}")

print("\n" + "-"*80 + "\n")

for col_name in collections_to_check:
    try:
        col = db[col_name]
        
        # Try to find by _id
        for mobile_format in mobile_formats:
            doc = col.find_one({'_id': mobile_format})
            if doc:
                print(f"✅ Found in '{col_name}' with _id: '{mobile_format}'")
                
                # Show skills-related fields
                if 'skills' in doc:
                    print(f"   📊 skills: {doc['skills']}")
                if 'skillsToLearn' in doc:
                    print(f"   🎯 skillsToLearn: {doc['skillsToLearn']}")
                if 'skills_to_develop' in doc:
                    print(f"   📚 skills_to_develop: {doc['skills_to_develop']}")
                
                print()
                break
        
        # Try to find by phone/mobile field
        for mobile_format in mobile_formats:
            doc = col.find_one({'phone': mobile_format})
            if doc:
                print(f"✅ Found in '{col_name}' with phone: '{mobile_format}'")
                if 'skills' in doc:
                    print(f"   📊 skills: {doc['skills']}")
                print()
                break
            
            doc = col.find_one({'mobile': mobile_format})
            if doc:
                print(f"✅ Found in '{col_name}' with mobile: '{mobile_format}'")
                if 'skills' in doc:
                    print(f"   📊 skills: {doc['skills']}")
                print()
                break
                
    except Exception as e:
        pass

print("="*80 + "\n")
