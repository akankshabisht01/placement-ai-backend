import requests
import json

# Test the skill completion API
backend_url = "http://localhost:5000"
mobile = "+91 8864862270"

print("\n" + "="*80)
print("TESTING SKILL COMPLETION API FOR MONTH 2, WEEK 8")
print("="*80)

# Test with Week 8 (cumulative week number for Month 2, Week 4)
test_data = {
    "mobile": mobile,
    "weekNumber": 8,
    "monthNumber": 2
}

print(f"\n📤 Request:")
print(json.dumps(test_data, indent=2))

try:
    response = requests.post(
        f"{backend_url}/api/check-skill-completion-with-ai",
        json=test_data,
        headers={"Content-Type": "application/json"}
    )
    
    print(f"\n📥 Response Status: {response.status_code}")
    print(f"\n📥 Response Body:")
    print(json.dumps(response.json(), indent=2))
    
    result = response.json()
    
    if result.get('success'):
        skills_moved = result.get('skillsMoved', [])
        skills_completed = result.get('skillsCompleted', [])
        
        print("\n" + "="*80)
        print("RESULT ANALYSIS")
        print("="*80)
        print(f"✅ Success: {result.get('success')}")
        print(f"📋 Skills Completed: {skills_completed}")
        print(f"➡️  Skills Moved: {skills_moved}")
        
        if skills_moved:
            print(f"\n🎉 SUCCESS! {len(skills_moved)} skill(s) were moved to Skills & Expertise")
        elif skills_completed:
            print(f"\nℹ️  Skills were completed but already in resume")
        else:
            print(f"\n⚠️  No skills were scheduled to complete this week")
    else:
        print(f"\n❌ API returned error: {result.get('error')}")
        
except Exception as e:
    print(f"\n❌ Error calling API: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*80 + "\n")
