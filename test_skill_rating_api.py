"""
Test the skill rating API to verify skill-specific scoring works correctly
"""

import requests
import json

# Test with the user we know has skillPerformance data
mobile = '+91 8864862270'

print(f"Testing skill rating API for {mobile}")
print("=" * 80)

# Make API call
try:
    response = requests.get(f'http://localhost:5000/api/skill-ratings/{mobile}')
    
    if response.status_code == 200:
        data = response.json()
        
        if data.get('success'):
            skill_ratings = data.get('skillRatings', {})
            total_skills = data.get('totalSkillsRated', 0)
            
            print(f"\n✅ Success! Total skills rated: {total_skills}\n")
            
            # Print each skill's rating
            for skill_name, rating in skill_ratings.items():
                print(f"📊 {skill_name}")
                print(f"   Stars: {'⭐' * rating['stars']} ({rating['stars']}/3)")
                print(f"   Average: {rating['averagePercentage']}%")
                print(f"   Weeks Tested: {rating['weeksTested']}")
                print(f"   Week Scores: {rating['weekScores']}")
                
                # Show score details to see if using skill-specific or overall
                if 'scoreDetails' in rating:
                    print(f"   Score Breakdown:")
                    for detail in rating['scoreDetails']:
                        print(f"      {detail}")
                
                print()
            
            # Check if we're getting different scores for different skills
            print("\n" + "=" * 80)
            print("VERIFICATION:")
            print("=" * 80)
            
            averages = [r['averagePercentage'] for r in skill_ratings.values()]
            unique_averages = set(averages)
            
            if len(unique_averages) > 1:
                print(f"✅ GOOD: Found {len(unique_averages)} different average scores")
                print(f"   This means skills are getting skill-specific ratings!")
                print(f"   Unique scores: {sorted(unique_averages)}")
            else:
                print(f"⚠️  WARNING: All skills have the same average score: {averages[0]}%")
                print(f"   This might mean we're still using overall scores")
            
            # Check if any scores mention skill-specific topics
            has_specific = False
            has_overall = False
            for rating in skill_ratings.values():
                for detail in rating.get('scoreDetails', []):
                    if 'from ' in detail:
                        has_specific = True
                    if 'overall' in detail:
                        has_overall = True
            
            print(f"\n✅ Using skill-specific scores: {has_specific}")
            print(f"⚠️  Falling back to overall: {has_overall}")
            
        else:
            print(f"❌ API returned error: {data.get('error')}")
    else:
        print(f"❌ HTTP Error {response.status_code}")
        print(response.text)
        
except requests.exceptions.ConnectionError:
    print("❌ Could not connect to backend. Make sure the server is running on port 5000")
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
