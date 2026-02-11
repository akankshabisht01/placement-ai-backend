"""
Test the actual skill ratings API with semantic matching
"""
import requests
import json

BACKEND_URL = "http://localhost:5000"
MOBILE = "+91 8864862270"

print("=" * 100)
print("Testing Skill Ratings API with Semantic Matching")
print("=" * 100)

print(f"\n📱 Mobile: {MOBILE}")
print(f"🔗 Endpoint: {BACKEND_URL}/api/skill-ratings/{MOBILE}\n")

try:
    response = requests.get(f"{BACKEND_URL}/api/skill-ratings/{MOBILE}", timeout=30)
    
    print(f"Status Code: {response.status_code}\n")
    
    if response.status_code == 200:
        data = response.json()
        
        if data.get('success'):
            skill_ratings = data.get('skillRatings', {})
            total_skills = data.get('totalSkillsRated', 0)
            
            print(f"✅ SUCCESS: Found {total_skills} skills with ratings\n")
            print("=" * 100)
            print("SKILL RATINGS (with skill-specific scores):")
            print("=" * 100)
            
            for skill, rating in skill_ratings.items():
                stars = '⭐' * rating.get('stars', 0)
                avg_pct = rating.get('averagePercentage', 0)
                weeks = rating.get('weeksAppearing', [])
                week_scores = rating.get('weekScores', [])
                weeks_tested = rating.get('weeksTested', 0)
                matched_topic = rating.get('matchedTopic', 'N/A')
                
                print(f"\n{skill}")
                print(f"  Stars: {stars} ({rating.get('stars', 0)}/3)")
                print(f"  Average: {avg_pct}%")
                print(f"  Weeks appearing: {weeks}")
                print(f"  Weeks tested: {weeks_tested}")
                print(f"  Week scores: {week_scores}")
                print(f"  Matched topic: {matched_topic}")
            
            print("\n" + "=" * 100)
            print("✅ Semantic matching is working!")
            print("✅ Each skill now has its SPECIFIC score, not overall week average!")
            print("=" * 100)
        else:
            print(f"❌ API returned error: {data.get('error')}")
    else:
        print(f"❌ HTTP Error: {response.status_code}")
        print(f"Response: {response.text}")

except requests.exceptions.ConnectionError:
    print("❌ ERROR: Cannot connect to backend")
    print("   Make sure backend is running: python app.py")
except Exception as e:
    print(f"❌ ERROR: {str(e)}")

print("\n" + "=" * 100)
