"""
Test the updated skill ratings endpoint that now uses Weekly_test_analysis collection
"""
import requests
import json

# Test with the user mobile
mobile = "+91 8864862270"
backend_url = "http://localhost:5000"

print(f"Testing skill ratings endpoint for: {mobile}")
print("="*80)

try:
    response = requests.get(f"{backend_url}/api/skill-ratings/{mobile}")
    
    print(f"Status Code: {response.status_code}")
    print(f"\nResponse:")
    
    data = response.json()
    print(json.dumps(data, indent=2))
    
    if data.get('success'):
        skill_ratings = data.get('skillRatings', {})
        print(f"\n{'='*80}")
        print(f"Total Skills with Ratings: {len(skill_ratings)}")
        print(f"{'='*80}\n")
        
        for skill_name, rating in skill_ratings.items():
            stars = '⭐' * rating['stars']
            print(f"{skill_name}: {stars} ({rating['stars']} stars)")
            print(f"  Average: {rating['averagePercentage']}%")
            print(f"  Weeks Tested: {rating['weeksTested']}")
            print(f"  Week Scores: {rating.get('weekScores', [])}")
            if 'scoreDetails' in rating:
                print(f"  Details:")
                for detail in rating['scoreDetails']:
                    print(f"    - {detail}")
            print()
    
except Exception as e:
    print(f"Error: {str(e)}")
    import traceback
    traceback.print_exc()
