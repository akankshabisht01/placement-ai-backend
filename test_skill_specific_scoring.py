"""
Test script to verify skill-specific scoring is working correctly
"""
from pymongo import MongoClient
from dotenv import load_dotenv
import os
import json

load_dotenv()

client = MongoClient(os.getenv('MONGODB_URI'))
db = client['Placement_Ai']

print("=" * 100)
print("TESTING SKILL-SPECIFIC SCORING FIX")
print("=" * 100)

# Test user
mobile = "+91 8864862270"

# 1. Check week_test_result
print(f"\n1. WEEK TEST RESULT DATA:")
print("-" * 100)
week_result = db['week_test_result'].find_one({"_id": mobile})

if week_result:
    print(f"Week: {week_result.get('week')}, Month: {week_result.get('month')}")
    print(f"Overall Score: {week_result.get('scorePercentage')}%")
    
    if 'skillPerformance' in week_result:
        print(f"\nSkill-Wise Breakdown:")
        for skill, data in week_result['skillPerformance'].items():
            print(f"  • {skill}: {data.get('percentage')}% ({data.get('correct')}/{data.get('total')} correct)")
    else:
        print("❌ No skillPerformance data found!")

# 2. Check skill_week_mapping
print(f"\n2. SKILL-WEEK MAPPING:")
print("-" * 100)

# Normalize mobile
clean = ''.join([c for c in mobile if c.isdigit()])
mobile_id = clean[-10:] if len(clean) >= 10 else clean

mapping = db['skill_week_mapping'].find_one({"_id": mobile_id})

if mapping and 'months' in mapping:
    for month_key, skills in mapping['months'].items():
        print(f"\n{month_key}:")
        for skill_name, weeks in skills.items():
            print(f"  • {skill_name}: weeks {weeks}")

# 3. Expected Behavior
print(f"\n3. EXPECTED BEHAVIOR AFTER FIX:")
print("-" * 100)
print("✅ If Week 4 teaches 2 topics:")
print("   - Topic A: User scored 43.4%")
print("   - Topic B: User scored 49.06%")
print("   - Overall: 46.23%")
print()
print("✅ When calculating skill ratings:")
print("   - Skills mapped to Topic A should get ~43.4% (not 46.23%)")
print("   - Skills mapped to Topic B should get ~49.06% (not 46.23%)")
print("   - Each skill gets its SPECIFIC score, not the overall week average")

# 4. What the API should return
print(f"\n4. WHAT /api/skill-ratings SHOULD NOW RETURN:")
print("-" * 100)
print("Before fix: All skills in Week 4 = 46.23% (overall week score)")
print("After fix:  Each skill gets its own topic-specific score")
print()
print("Example for skills in the resume:")
if week_result and 'skillPerformance' in week_result:
    print("\nBased on actual data:")
    for skill, data in week_result['skillPerformance'].items():
        pct = data.get('percentage', 0)
        if pct >= 90:
            stars = "⭐⭐⭐"
        elif pct >= 70:
            stars = "⭐⭐"
        elif pct >= 50:
            stars = "⭐"
        else:
            stars = "(no stars)"
        print(f"  • Skill related to '{skill}': {pct}% {stars}")

print("\n" + "=" * 100)
print("TEST THE FIX:")
print("=" * 100)
print("Run this command to test:")
print(f"  curl http://localhost:5000/api/skill-ratings/{mobile}")
print()
print("Or in Python:")
print(f"  import requests")
print(f"  r = requests.get('http://localhost:5000/api/skill-ratings/{mobile}')")
print(f"  print(r.json())")
print("\n" + "=" * 100)
