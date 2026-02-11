"""Test skill completion check after weekly test"""
import requests
import json

# User who just generated skill mappings
mobile = "+91 6396428243"

print(f"\n{'='*80}")
print(f"TESTING SKILL COMPLETION CHECK")
print(f"{'='*80}\n")

# Test different weeks to see which skills complete
test_cases = [
    {"mobile": mobile, "monthNumber": 1, "weekNumber": 4, "expected": ["Data Cleaning", "Microsoft Excel", "Basic Data Analysis"]},
    {"mobile": mobile, "monthNumber": 2, "weekNumber": 3, "expected": ["Data Visualization"]},
    {"mobile": mobile, "monthNumber": 2, "weekNumber": 4, "expected": ["Reporting", "Tableau"]},
    {"mobile": mobile, "monthNumber": 3, "weekNumber": 3, "expected": ["Statistical Analysis"]},
    {"mobile": mobile, "monthNumber": 3, "weekNumber": 4, "expected": ["Data Analysis", "Reporting"]},
]

url = "http://localhost:5000/api/check-skill-completion-with-ai"

for i, test in enumerate(test_cases, 1):
    print(f"\n{'─'*80}")
    print(f"TEST CASE {i}: Month {test['monthNumber']}, Week {test['weekNumber']}")
    print(f"{'─'*80}")
    print(f"📱 Mobile: {test['mobile']}")
    print(f"📅 Month: {test['monthNumber']}, Week: {test['weekNumber']}")
    print(f"🎯 Expected skills to complete: {test['expected']}")
    
    payload = {
        "mobile": test['mobile'],
        "monthNumber": test['monthNumber'],
        "weekNumber": test['weekNumber']
    }
    
    response = requests.post(url, json=payload)
    result = response.json()
    
    if result.get('success'):
        completed = result.get('skillsCompleted', [])
        moved = result.get('skillsMoved', [])
        
        print(f"\n✅ SUCCESS!")
        print(f"   Skills completed this week: {completed}")
        print(f"   Skills moved to resume: {moved}")
        print(f"   Total skills in resume: {result.get('totalSkillsInResume')}")
        
        # Check if expected skills match
        if set(completed) == set(test['expected']):
            print(f"   ✅ CORRECT: Skills match expected!")
        else:
            print(f"   ⚠️  MISMATCH:")
            print(f"      Expected: {test['expected']}")
            print(f"      Got: {completed}")
    else:
        print(f"\n❌ FAILED: {result.get('message')}")

print(f"\n{'='*80}\n")
