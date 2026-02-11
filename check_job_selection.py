from pymongo import MongoClient
import json

client = MongoClient('mongodb://localhost:27017/')
db = client['Placement_Ai']
resume_col = db['Resume']

mobile_formats = ['8864862270', '+91 8864862270', '918864862270', '+918864862270']

print("\n" + "="*80)
print("CHECKING RESUME FOR JOB SELECTION")
print("="*80)

resume = resume_col.find_one({'mobile': {'$in': mobile_formats}})

if resume:
    print(f"\n✅ Found resume with _id: {resume.get('_id')}")
    
    # Check all top-level fields
    print(f"\n📋 All fields in resume:")
    for key in resume.keys():
        print(f"   - {key}")
    
    # Check jobSelection specifically
    job_selection = resume.get('jobSelection')
    print(f"\n🎯 jobSelection field:")
    if job_selection:
        print(f"   ✅ EXISTS")
        print(f"   Value: {json.dumps(job_selection, indent=6)}")
        
        job_role = job_selection.get('jobRole')
        print(f"\n   jobRole: {job_role}")
    else:
        print(f"   ❌ NOT FOUND - This is why Perplexity can't get job role!")
        print(f"\n   The Resume document needs a 'jobSelection' field with 'jobRole'")
else:
    print(f"\n❌ No resume found with mobile formats: {mobile_formats}")

print("\n" + "="*80)
