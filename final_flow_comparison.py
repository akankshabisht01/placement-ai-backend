from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

client = MongoClient(os.getenv('MONGO_URI'))
db = client['Placement_Ai']

# Get weekly plan
weekly_col = db['weekly_plans']
weekly_doc = weekly_col.find_one({'_id': '6396428243'})

# Get corresponding roadmap
roadmap_col = db['Roadmap_Dashboard ']
roadmap_doc = roadmap_col.find_one({'_id': '+91 6396428243'})

if not weekly_doc:
    print('No weekly plan found for 6396428243')
elif not roadmap_doc:
    print('No roadmap found for +91 6396428243')
else:
    print('='*80)
    print('FLOW COMPARISON FOR USER: +91 6396428243')
    print('='*80)
    
    # Extract Month 1 Daily Plan from Roadmap
    roadmap = roadmap_doc.get('roadmap', {})
    month1_roadmap = roadmap.get('Month 1', {})
    daily_plan = month1_roadmap.get('Daily Plan (2 hours/day)', [])
    
    print('\n📅 MONTH VIEW (from Roadmap_Dashboard):')
    print('-'*80)
    for i, plan in enumerate(daily_plan[:4], 1):
        print(f'\nWeek {i}:')
        print(f'  {plan}')
    
    # Extract Month 1 Weekly View
    months = weekly_doc.get('months', {})
    month1_weekly = months.get('month_1', {})
    
    print('\n\n📊 WEEKLY VIEW (from weekly_plans):')
    print('-'*80)
    for i in range(1, 5):
        week_key = f'week_{i}'
        week = month1_weekly.get(week_key, {})
        topics = week.get('topics', [])
        learning_goal = week.get('learning_goal', '')
        roadmap_items = week.get('roadmap', [])
        
        print(f'\nWeek {i}:')
        print(f'  Learning Goal: {learning_goal}')
        if topics:
            print(f'  Topics: {topics}')
        if roadmap_items:
            print(f'  Roadmap: {roadmap_items[:3]}')
    
    # Analysis
    print('\n\n🔍 FLOW ANALYSIS:')
    print('='*80)
    
    # Week 1
    week1_month = daily_plan[0].lower() if len(daily_plan) > 0 else ''
    week1_weekly = month1_weekly.get('week_1', {}).get('learning_goal', '').lower()
    week1_topics = month1_weekly.get('week_1', {}).get('topics', [])
    
    print('\n📌 Week 1:')
    print(f'   Month View mentions: {"Excel" if "excel" in week1_month else "N/A"}')
    print(f'   Weekly View mentions: {"Excel" if "excel" in week1_weekly else "N/A"}')
    
    if 'excel' in week1_month and 'excel' in week1_weekly:
        print('   ✅ MATCH: Both mention Excel in Week 1')
    else:
        print('   ❌ MISMATCH detected')
    
    # Week 2
    if len(daily_plan) > 1:
        week2_month = daily_plan[1].lower()
        week2_weekly = month1_weekly.get('week_2', {}).get('learning_goal', '').lower()
        
        print('\n📌 Week 2:')
        print(f'   Month View key terms: {"Data Cleaning" if "data cleaning" in week2_month or "clean" in week2_month else "N/A"}')
        print(f'   Weekly View key terms: {"Data Cleaning" if "data cleaning" in week2_weekly or "clean" in week2_weekly else "N/A"}')
        
        if ('clean' in week2_month and 'clean' in week2_weekly):
            print('   ✅ MATCH: Both mention Data Cleaning in Week 2')
        else:
            print('   ❌ MISMATCH detected')
    
    # Week 3
    if len(daily_plan) > 2:
        week3_month = daily_plan[2].lower()
        week3_weekly = month1_weekly.get('week_3', {}).get('learning_goal', '').lower()
        
        print('\n📌 Week 3:')
        print(f'   Month View mentions: {"Pivot Tables" if "pivot" in week3_month else "N/A"}')
        print(f'   Weekly View mentions: {"Pivot Tables" if "pivot" in week3_weekly else "N/A"}')
        
        if ('pivot' in week3_month and 'pivot' in week3_weekly):
            print('   ✅ MATCH: Both mention Pivot Tables in Week 3')
        else:
            print('   ❌ MISMATCH detected')

client.close()
