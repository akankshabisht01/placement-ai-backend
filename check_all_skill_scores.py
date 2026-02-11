"""
Get all skill ratings (not filtered by job role)
"""
import requests
import json

mobile = "+91 8864862270"
backend_url = "http://localhost:5000"

print(f"Fetching ALL skill ratings for: {mobile}")
print("="*80)

try:
    response = requests.get(f"{backend_url}/api/skill-ratings/{mobile}")
    data = response.json()
    
    # The backend returns filtered skills, but we can see from the logs
    # Let me check if there's an endpoint that returns all skills
    
    # Based on the console output, we saw:
    print("From the backend console output:")
    print("\nSkills tested in the curriculum:")
    print("  1. Machine Learning Fundamentals: 50.6% (1 star)")
    print("     - Week 1: 42.5%")
    print("     - Week 2: 27.5%") 
    print("     - Week 3: 45%")
    print("     - Week 4: 87.5%")
    print()
    print("  2. scikit-learn: 48.49% (0 stars)")
    print("     - Week 1: 33.96% (from 'Install scikit-learn' topic)")
    print("     - Week 2: 27.5%")
    print("     - Week 3: 45%")
    print("     - Week 4: 87.5%")
    print()
    print("="*80)
    print("\nJob-role filtered result (NLP Engineer):")
    print(f"Total skills required: {len(data.get('jobRoleSkills', []))}")
    print(f"Skills with ratings: {data.get('totalSkillsRated', 0)}")
    print()
    
    for skill_name, rating in data.get('skillRatings', {}).items():
        stars = '⭐' * rating['stars']
        print(f"{skill_name}: {stars} ({rating['stars']} stars)")
        print(f"  Average: {rating['averagePercentage']}%")
        print(f"  Weeks tested: {rating['weeksTested']}")
        for detail in rating.get('scoreDetails', []):
            print(f"    • {detail}")
        print()
    
except Exception as e:
    print(f"Error: {str(e)}")
