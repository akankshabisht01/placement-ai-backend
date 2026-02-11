"""Test the new skill mapping generation endpoint"""
import requests
import json

# User who just created roadmap
mobile = "+91 6396428243"

print(f"\n{'='*80}")
print(f"TESTING SKILL MAPPING GENERATION FROM ROADMAP_DASHBOARD")
print(f"{'='*80}\n")

print(f"📱 Mobile: {mobile}")
print(f"🎯 Generating skill-week mappings for all months...\n")

# Call the endpoint
url = "http://localhost:5000/api/generate-skill-mappings-from-roadmap"
payload = {
    "mobile": mobile
}

print(f"📤 POST {url}")
print(f"   Payload: {json.dumps(payload, indent=2)}\n")

response = requests.post(url, json=payload)

print(f"📥 Response Status: {response.status_code}")
print(f"\n{'='*80}")
print("RESPONSE:")
print(f"{'='*80}\n")

result = response.json()
print(json.dumps(result, indent=2))

if result.get('success'):
    print(f"\n{'='*80}")
    print(f"✅ SUCCESS!")
    print(f"{'='*80}\n")
    print(f"Months processed: {result.get('months_processed')}")
    print(f"Total skills mapped: {result.get('totalSkills')}")
    
    print(f"\n📋 SKILL MAPPINGS BY MONTH:")
    print(f"{'='*80}\n")
    
    mappings = result.get('mappings', {})
    for month_key in sorted(mappings.keys()):
        month_num = month_key.split('_')[1]
        skills = mappings[month_key]
        
        print(f"\n🗓️  MONTH {month_num} ({len(skills)} skills):")
        print(f"{'─'*60}")
        
        for skill, week in sorted(skills.items(), key=lambda x: x[1]):
            print(f"   Week {week}: {skill}")
else:
    print(f"\n{'='*80}")
    print(f"❌ FAILED!")
    print(f"{'='*80}\n")
    print(f"Error: {result.get('message')}")

print(f"\n{'='*80}\n")
