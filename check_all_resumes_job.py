from pymongo import MongoClient
import json

client = MongoClient('mongodb://localhost:27017/')
db = client['Placement_Ai']
resume_col = db['Resume']

print("\n" + "="*80)
print("CHECKING ALL RESUMES FOR JOB SELECTION FIELD")
print("="*80)

total = resume_col.count_documents({})
print(f"\nTotal resumes: {total}")

print(f"\n📋 Sample _ids and jobSelection status:")
resumes = list(resume_col.find().limit(5))
for r in resumes:
    has_job = 'jobSelection' in r
    job_role = r.get('jobSelection', {}).get('jobRole') if has_job else None
    print(f"   _id: {r['_id']:20s} | jobSelection: {has_job:5} | jobRole: {job_role}")

# Check specifically for 8864862270
print(f"\n🔍 Searching for user 8864862270:")
mobile_formats = ['+91 8864862270', '+918864862270', '8864862270', '918864862270', '91 8864862270']

for fmt in mobile_formats:
    resume = resume_col.find_one({'_id': fmt})
    if resume:
        print(f"\n✅ Found with _id: {fmt}")
        print(f"   Has jobSelection: {'jobSelection' in resume}")
        if 'jobSelection' in resume:
            print(f"   jobSelection: {json.dumps(resume['jobSelection'], indent=6)}")
        else:
            print(f"   Fields in document: {list(resume.keys())}")
        break
else:
    print(f"   ❌ Not found with any format")

print("\n" + "="*80)
