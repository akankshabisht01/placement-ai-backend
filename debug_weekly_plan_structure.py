"""Debug script to inspect weekly_plans structure"""
import os
import json
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

# Get MongoDB connection
mongo_uri = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
db_name = os.getenv('MONGODB_DB', 'Placement_Ai')

client = MongoClient(mongo_uri)
db = client[db_name]

# Get a sample weekly plan
weekly_plans_col = db['weekly_plans']
sample_plan = weekly_plans_col.find_one()

if sample_plan:
    print("\n" + "="*80)
    print("SAMPLE WEEKLY PLAN STRUCTURE")
    print("="*80)
    print(f"\nUser ID: {sample_plan.get('_id')}")
    
    months = sample_plan.get('months', {})
    print(f"\nMonths available: {list(months.keys())}")
    
    # Get first month
    if months:
        first_month_key = list(months.keys())[0]
        first_month_data = months[first_month_key]
        
        print(f"\n{first_month_key.upper()} STRUCTURE:")
        print("-" * 80)
        
        for week_key in ['week_1', 'week_2', 'week_3', 'week_4']:
            week_data = first_month_data.get(week_key, {})
            if week_data:
                print(f"\n{week_key}:")
                print(f"  learning_goal: {week_data.get('learning_goal', 'N/A')[:100]}...")
                print(f"  roadmap: {week_data.get('roadmap', 'N/A')[:100]}...")
                
                topics = week_data.get('topics', [])
                print(f"  topics type: {type(topics)}")
                print(f"  topics count: {len(topics) if isinstance(topics, list) else 'N/A'}")
                
                if isinstance(topics, list) and len(topics) > 0:
                    first_topic = topics[0]
                    print(f"  first topic type: {type(first_topic)}")
                    if isinstance(first_topic, dict):
                        print(f"  first topic keys: {list(first_topic.keys())}")
                        print(f"  first topic: {json.dumps(first_topic, indent=4)[:200]}...")
                    else:
                        print(f"  first topic: {first_topic}")
else:
    print("\n⚠️ No weekly plans found in database")

print("\n" + "="*80)
