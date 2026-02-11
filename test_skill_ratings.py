import requests
import json

backend_url = "http://localhost:5000"
mobile = "+91 8864862270"

print("\n" + "="*80)
print("TESTING SKILL RATINGS API")
print("="*80)

try:
    response = requests.get(f"{backend_url}/api/skill-ratings/{mobile}")
    
    print(f"\n📥 Response Status: {response.status_code}")
    
    result = response.json()
    print(f"\n📥 Response:")
    print(json.dumps(result, indent=2))
    
    if result.get('success'):
        skill_ratings = result.get('skillRatings', {})
        
        print("\n" + "="*80)
        print(f"STAR RATINGS ({len(skill_ratings)} skills)")
        print("="*80)
        
        for skill, rating in skill_ratings.items():
            stars = rating.get('stars', 0)
            avg = rating.get('averagePercentage', 0)
            weeks = rating.get('weeksAppearing', [])
            
            star_display = '⭐' * stars if stars > 0 else '⚪'
            
            print(f"\n{skill}:")
            print(f"   {star_display} {stars} stars")
            print(f"   Average: {avg}%")
            print(f"   Weeks: {weeks}")
            print(f"   Scores: {rating.get('weekScores', [])}")
    else:
        print(f"\n❌ Error: {result.get('message')}")
        
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*80 + "\n")
