import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

# Get MongoDB connection
mongo_uri = os.getenv('MONGO_URI') or os.getenv('MONGODB_URI')
client = MongoClient(mongo_uri)
db = client[os.getenv("MONGODB_DB", "Placement_Ai")]

mobile = "+91 8864862270"

print("\n" + "="*80)
print(f"MANUAL FIX: Update localStorage for user {mobile}")
print("="*80)

# Get skills from Resume collection
resume_col = db['Resume']
resume_doc = resume_col.find_one({'_id': mobile})

if resume_doc:
    skills = resume_doc.get('skills', [])
    print(f"\n✅ Found {len(skills)} skills in database:")
    for i, skill in enumerate(skills, 1):
        print(f"   {i}. {skill}")
    
    print("\n" + "="*80)
    print("INSTRUCTIONS TO FIX FRONTEND:")
    print("="*80)
    print("\n1. Open the Dashboard page in your browser")
    print("2. Press F12 to open Developer Console")
    print("3. Copy and paste the following code:")
    print("\n" + "-"*80)
    print(f"""
const linkedData = JSON.parse(localStorage.getItem('linkedResumeData') || '{{}}');
linkedData.skills = {skills};
localStorage.setItem('linkedResumeData', JSON.stringify(linkedData));
window.dispatchEvent(new Event('skillsUpdated'));
console.log('✅ Skills updated! Dashboard should refresh automatically.');
""")
    print("-"*80)
    print("\n4. Press Enter")
    print("5. The Dashboard should automatically update showing all 5 skills!")
    print("\n" + "="*80 + "\n")
else:
    print("\n❌ Resume not found!")
