import requests
import json

backend_url = "http://localhost:5000"
mobile = "+91 8864862270"

print("\n" + "="*80)
print("TESTING: Refresh Stars Flow")
print("="*80)

# Step 1: Call generate-skill-mappings-from-roadmap
print("\n1. CALLING: /api/generate-skill-mappings-from-roadmap")
print("-" * 80)

try:
    response = requests.post(
        f"{backend_url}/api/generate-skill-mappings-from-roadmap",
        json={"mobile": mobile},
        headers={"Content-Type": "application/json"}
    )
    
    print(f"Status: {response.status_code}")
    result = response.json()
    print(f"Response:")
    print(json.dumps(result, indent=2))
    
    if result.get('success'):
        print(f"\n✅ Mappings generated successfully!")
    else:
        print(f"\n❌ Failed: {result.get('message')}")
        
except Exception as e:
    print(f"❌ Error: {e}")

# Step 2: Call skill-ratings API
print("\n2. CALLING: /api/skill-ratings/{mobile}")
print("-" * 80)

try:
    response = requests.get(f"{backend_url}/api/skill-ratings/{mobile}")
    
    print(f"Status: {response.status_code}")
    result = response.json()
    print(f"Response:")
    print(json.dumps(result, indent=2))
    
    if result.get('success'):
        skill_ratings = result.get('skillRatings', {})
        print(f"\n✅ Found {len(skill_ratings)} skills with ratings:")
        
        for skill, rating in skill_ratings.items():
            stars = rating.get('stars', 0)
            avg = rating.get('averagePercentage', 0)
            star_display = '⭐' * stars if stars > 0 else '⚪'
            print(f"   {star_display} {skill}: {avg}%")
    else:
        print(f"\n❌ No ratings: {result.get('message')}")
        
except Exception as e:
    print(f"❌ Error: {e}")

print("\n" + "="*80 + "\n")
