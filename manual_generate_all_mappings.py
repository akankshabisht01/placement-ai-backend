"""
Manually generate skill mappings for users who have roadmaps but no mappings.
Run this script when the backend is running.
"""
import requests
import json

# Users who have roadmaps but no skill mappings
users_to_process = [
    "+91 7302249246",
    "+91 8126355099",
    "+91 9346333208",
    "+91 9084117332",
    "+91 8864862270"
]

url = "http://localhost:5000/api/generate-skill-mappings-from-roadmap"

print(f"\n{'='*80}")
print(f"MANUALLY GENERATING SKILL MAPPINGS FOR USERS")
print(f"{'='*80}\n")

for mobile in users_to_process:
    print(f"\n{'─'*80}")
    print(f"Processing: {mobile}")
    print(f"{'─'*80}")
    
    payload = {"mobile": mobile}
    
    try:
        response = requests.post(url, json=payload, timeout=60)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                print(f"✅ SUCCESS!")
                print(f"   Months processed: {result.get('months_processed')}")
                print(f"   Total skills: {result.get('totalSkills')}")
                
                mappings = result.get('mappings', {})
                for month_key in sorted(mappings.keys()):
                    month_num = month_key.split('_')[1]
                    skills = mappings[month_key]
                    print(f"   Month {month_num}: {len(skills)} skills")
            else:
                print(f"❌ FAILED: {result.get('message')}")
        else:
            print(f"❌ HTTP Error {response.status_code}: {response.text}")
    
    except requests.exceptions.Timeout:
        print(f"⏱️ TIMEOUT: Request took too long (>60s)")
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")

print(f"\n{'='*80}")
print(f"PROCESSING COMPLETE")
print(f"{'='*80}\n")
