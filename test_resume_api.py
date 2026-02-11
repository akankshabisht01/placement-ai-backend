"""Test what the resume API endpoint returns"""
import requests
import json

mobile = "+91 8864862270"

print("\n" + "="*80)
print("TESTING RESUME API ENDPOINT")
print("="*80 + "\n")

# Test the resume analysis endpoint
url = "http://localhost:5000/api/resume-analysis/8864862270"

try:
    print(f"📡 Calling: GET {url}")
    response = requests.get(url, timeout=5)
    
    print(f"📊 Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"\n✅ Response received!")
        
        # Check skills in response
        if 'skills' in data:
            skills = data['skills']
            print(f"\n📊 Skills in API response ({len(skills)} total):")
            for i, skill in enumerate(skills, 1):
                print(f"   {i}. {skill}")
        
        if 'skillsToLearn' in data:
            skills_to_learn = data['skillsToLearn']
            print(f"\n🎯 Skills To Learn ({len(skills_to_learn)} total):")
            for i, skill in enumerate(skills_to_learn, 1):
                print(f"   {i}. {skill}")
        
        # Print full response for debugging
        print(f"\n📋 Full Response:")
        print(json.dumps(data, indent=2))
    else:
        print(f"❌ Error: {response.status_code}")
        print(f"Response: {response.text}")
        
except requests.exceptions.ConnectionError:
    print("❌ ERROR: Could not connect to backend")
    print("   Make sure backend is running on port 5000")
except Exception as e:
    print(f"❌ ERROR: {str(e)}")

print("\n" + "="*80 + "\n")
