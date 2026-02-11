from pymongo import MongoClient
import os
from dotenv import load_dotenv
import json

load_dotenv()

client = MongoClient(os.getenv('MONGO_URI'))
db = client['Placement_Ai']

# Find a weekly plan with actual month data
weekly_col = db['weekly_plans']
weekly_plans = list(weekly_col.find().limit(10))

found_match = None
for plan in weekly_plans:
    months = plan.get('months', {})
    if 'month_1' in months:
        month_1 = months['month_1']
        if 'week_1' in month_1 and month_1['week_1'].get('topics'):
            found_match = plan
            break

if found_match:
    print('='*80)
    print('FOUND WEEKLY PLAN WITH DATA')
    print('='*80)
    
    # Try to find matching roadmap
    mobile = found_match.get('mobile', '')
    roadmap_doc = None
    roadmap_col = db['Roadmap_Dashboard ']
    
    if mobile:
        roadmap_doc = roadmap_col.find_one({'_id': f'+91 {mobile}'})
        if roadmap_doc:
            print(f'\n✅ Found roadmap for mobile: +91 {mobile}')
    
    if not mobile or not roadmap_doc:
        # Try to find a user with both
        for doc in roadmap_col.find().limit(30):
            doc_id = doc.get('_id', '')
            doc_mobile = str(doc_id).replace('+', '').replace(' ', '').replace('91', '')[-10:]
            
            # Check if this roadmap user has weekly plan
            test_plan = weekly_col.find_one({'mobile': doc_mobile})
            if test_plan and test_plan.get('months', {}).get('month_1', {}).get('week_1'):
                mobile = doc_mobile
                roadmap_doc = doc
                print(f'\n✅ Found matching pair for mobile: {doc_id}')
                break
    
    if mobile and roadmap_doc:
        # Show Month View
        roadmap_data = roadmap_doc.get('roadmap', {})
        month_1 = roadmap_data.get('Month 1', {})
        
        print('\n📅 MONTH 1 - MONTH VIEW:')
        print('-'*80)
        print(f'Skill Focus: {month_1.get("Skill Focus", "N/A")}')
        print('\nDaily Plan:')
        daily_plan = month_1.get('Daily Plan (2 hours/day)', [])
        for i, week_plan in enumerate(daily_plan, 1):
            print(f'  Week {i}: {week_plan.strip()[:150]}')
        
        # Show Weekly View
        weekly_plan = weekly_col.find_one({'mobile': mobile})
        month_1_weekly = weekly_plan.get('months', {}).get('month_1', {})
        
        print('\n\n📊 MONTH 1 - WEEKLY VIEW:')
        print('-'*80)
        for week_num in range(1, 5):
            week_key = f'week_{week_num}'
            week_data = month_1_weekly.get(week_key, {})
            if week_data and week_data.get('topics'):
                print(f'\n🗓️  WEEK {week_num}:')
                print(f'   Topics: {week_data.get("topics", [])}')
                print(f'   Goal: {week_data.get("learning_goal", "N/A")[:120]}')
        
        # Comparison
        print('\n\n🔍 FLOW COMPARISON:')
        print('='*80)
        if len(daily_plan) >= 1 and month_1_weekly.get('week_1'):
            week1_month = daily_plan[0].lower()
            week1_topics = month_1_weekly['week_1'].get('topics', [])
            
            print(f'\n📌 Week 1 from Month View: {daily_plan[0][:100]}')
            print(f'📌 Week 1 from Weekly View: {week1_topics}')
            
            # Check for key terms
            if 'excel' in week1_month:
                has_excel = any('excel' in str(t).lower() for t in week1_topics)
                if has_excel:
                    print('✅ MATCH: Excel appears in both Week 1')
                else:
                    print('❌ MISMATCH: Excel in Month View but not in Weekly View Week 1')
    
else:
    print('No weekly plans with data found')

client.close()
