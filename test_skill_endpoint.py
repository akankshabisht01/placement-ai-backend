"""Test the skill completion endpoint directly"""
import requests
import json

mobile = "+91 8864862270"

print(f"\n{'='*80}")
print(f"TESTING SKILL COMPLETION ENDPOINT")
print(f"{'='*80}\n")

# Simulate completing Month 1, Week 4 test
payload = {
    "mobile": mobile,
    "monthNumber": 1,
    "weekNumber": 4
}

url = "http://localhost:5000/api/check-skill-completion-with-ai"

print(f"Request:")
print(f"  URL: {url}")
print(f"  Payload: {json.dumps(payload, indent=2)}\n")

try:
    response = requests.post(url, json=payload, timeout=10)
    
    print(f"Response:")
    print(f"  Status: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"  Body: {json.dumps(result, indent=2)}")
        
        if result.get('success'):
            print(f"\n✅ SUCCESS!")
            print(f"   Skills completed: {result.get('skillsCompleted', [])}")
            print(f"   Skills moved: {result.get('skillsMoved', [])}")
        else:
            print(f"\n❌ FAILED: {result.get('error') or result.get('message')}")
    else:
        print(f"  Error: {response.text}")

except requests.exceptions.ConnectionError:
    print(f"❌ ERROR: Could not connect to backend")
    print(f"   Make sure backend is running on port 5000")
except Exception as e:
    print(f"❌ ERROR: {str(e)}")

print(f"\n{'='*80}\n")
