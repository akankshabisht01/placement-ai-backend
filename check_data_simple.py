from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

client = MongoClient(os.getenv('MONGO_URI'))
db = client['Placement_Ai']

# Check weekly plans
weekly_col = db['weekly_plans']
print('WEEKLY PLANS:')
for doc in weekly_col.find().limit(5):
    mobile = doc.get('mobile', 'NO MOBILE')
    months = doc.get('months', {})
    has_month1 = 'month_1' in months
    print(f'  Mobile: {mobile}, Has Month 1: {has_month1}')
    if has_month1:
        month1 = months['month_1']
        weeks = [k for k in month1.keys() if k.startswith('week_')]
        print(f'    Weeks: {weeks}')

print('\n' + '='*80)
print('ROADMAPS:')
roadmap_col = db['Roadmap_Dashboard ']
for doc in roadmap_col.find().limit(5):
    doc_id = doc.get('_id', 'NO ID')
    roadmap = doc.get('roadmap', {})
    has_month1 = 'Month 1' in roadmap
    print(f'  ID: {doc_id}, Has Month 1: {has_month1}')

print('\n' + '='*80)
print('FINDING MATCH...')
for doc in roadmap_col.find().limit(10):
    doc_id = str(doc.get('_id', ''))
    # Extract mobile number
    mobile = doc_id.replace('+91 ', '').replace('+', '').strip()
    
    # Check if weekly plan exists
    weekly = weekly_col.find_one({'mobile': mobile})
    if weekly:
        print(f'\n✅ MATCH FOUND!')
        print(f'   Roadmap ID: {doc_id}')
        print(f'   Mobile: {mobile}')
        
        # Show Month 1 Daily Plan
        roadmap = doc.get('roadmap', {})
        month1 = roadmap.get('Month 1', {})
        daily_plan = month1.get('Daily Plan (2 hours/day)', [])
        
        print(f'\n   📅 MONTH VIEW - Daily Plan:')
        for i, plan in enumerate(daily_plan[:4], 1):
            print(f'      Week {i}: {plan[:80]}')
        
        # Show Weekly View
        weeks = weekly.get('months', {}).get('month_1', {})
        print(f'\n   📊 WEEKLY VIEW:')
        for i in range(1, 5):
            week = weeks.get(f'week_{i}', {})
            topics = week.get('topics', [])
            if topics:
                print(f'      Week {i}: {topics[:3]}')
        
        break

client.close()
