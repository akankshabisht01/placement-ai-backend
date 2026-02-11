"""Check a specific user's roadmap weekly topics"""
import os
from pymongo import MongoClient
from dotenv import load_dotenv
import json

load_dotenv()

mongo_uri = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
db_name = os.getenv('MONGODB_DB', 'Placement_Ai')

client = MongoClient(mongo_uri)
db = client[db_name]
collection = db['Roadmap_Dashboard ']

# Get a sample user
mobile = "+91 8864862270"
doc = collection.find_one({'mobile': mobile})

if doc:
    print(f"\n{'='*80}")
    print(f"USER ROADMAP WEEKLY TOPICS")
    print(f"Mobile: {mobile}")
    print(f"{'='*80}\n")
    
    roadmap = doc.get('roadmap', {})
    
    # Check Month 1
    month1 = roadmap.get('Month 1', {})
    
    print("\n📚 MONTH 1 LEARNING PLAN:")
    print(f"\n🎯 Skill Focus: {month1.get('Skill Focus', 'N/A')}")
    
    print(f"\n📝 Learning Goals:")
    goals = month1.get('Learning Goals', [])
    if isinstance(goals, list):
        for goal in goals:
            print(f"   • {goal}")
    else:
        print(f"   {goals}")
    
    print(f"\n📅 Weekly Plan (Daily Plan 2 hours/day):")
    daily_plan = month1.get('Daily Plan (2 hours/day)', [])
    if isinstance(daily_plan, list):
        for i, week in enumerate(daily_plan, 1):
            print(f"\n   Week {i}:")
            print(f"   {week}")
    else:
        print(f"   {daily_plan}")
    
    print(f"\n🚀 Mini Project:")
    print(f"   {month1.get('Mini Project', 'N/A')}")
    
    print(f"\n✅ Expected Outcome:")
    print(f"   {month1.get('Expected Outcome', 'N/A')}")
    
else:
    print(f"User {mobile} not found")
