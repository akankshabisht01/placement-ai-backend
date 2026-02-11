import os
from pymongo import MongoClient
from dotenv import load_dotenv
import json

load_dotenv()

# Connect to MongoDB
mongo_uri = os.getenv('MONGO_URI')
client = MongoClient(mongo_uri)
db = client['Placement_Ai']

# Get a sample roadmap
roadmap_collection = db['Roadmap_Dashboard ']
sample_roadmap = roadmap_collection.find_one()

if sample_roadmap:
    print('='*80)
    print('SAMPLE ROADMAP USER:', sample_roadmap.get('_id'))
    print('='*80)
    
    # Check Month 1
    roadmap_data = sample_roadmap.get('roadmap', {})
    month_1 = roadmap_data.get('Month 1', {})
    
    if month_1:
        print('\n📅 MONTH 1 - MONTH VIEW STRUCTURE:')
        print('-'*80)
        print('Skill Focus:', month_1.get('Skill Focus', ''))
        print('\nDaily Plan:')
        daily_plan = month_1.get('Daily Plan (2 hours/day)', [])
        for i, week_plan in enumerate(daily_plan, 1):
            print(f'  Week {i}: {week_plan.strip()}')
    
    # Now check if there's a weekly plan cached
    mobile_id = str(sample_roadmap.get('_id', '')).replace('+', '').replace(' ', '')[-10:]
    
    weekly_collection = db['weekly_plans']
    weekly_plan_doc = weekly_collection.find_one({'mobile': mobile_id})
    
    if weekly_plan_doc:
        print('\n\n✅ FOUND CACHED WEEKLY PLAN')
        print('='*80)
        months_data = weekly_plan_doc.get('months', {})
        month_1_weekly = months_data.get('month_1', {})
        
        if month_1_weekly:
            print('\n📊 WEEK-BY-WEEK BREAKDOWN FROM WEEKLY VIEW:')
            print('-'*80)
            for week_num in range(1, 5):
                week_key = f'week_{week_num}'
                week_data = month_1_weekly.get(week_key, {})
                if week_data:
                    print(f'\n🗓️  WEEK {week_num}:')
                    goal = week_data.get('learning_goal', 'N/A')
                    print(f'   Goal: {goal}')
                    topics = week_data.get('topics', [])
                    print(f'   Topics: {topics}')
                    roadmap_text = week_data.get('roadmap', '')
                    print(f'   Roadmap: {roadmap_text[:200]}...')
        else:
            print('❌ No month_1 data in weekly plan')
            
        print('\n\n🔍 COMPARISON ANALYSIS:')
        print('='*80)
        print('Checking if Daily Plan flow matches Weekly View...')
        
        # Compare
        if month_1 and month_1_weekly:
            daily_plan = month_1.get('Daily Plan (2 hours/day)', [])
            if len(daily_plan) >= 1:
                week1_month = daily_plan[0].lower()
                week1_weekly_topics = month_1_weekly.get('week_1', {}).get('topics', [])
                week1_weekly_str = ' '.join(week1_weekly_topics).lower()
                
                print(f'\n📌 Week 1 Month View: {daily_plan[0][:100]}')
                print(f'📌 Week 1 Weekly View Topics: {week1_weekly_topics}')
                
                # Check if key skills mentioned in month view appear in weekly view
                if 'excel' in week1_month and any('excel' in t.lower() for t in week1_weekly_topics):
                    print('✅ Week 1: Excel mentioned in BOTH views - FLOW MATCHES')
                elif 'excel' in week1_month:
                    print('❌ Week 1: Excel in Month View but NOT in Weekly View topics - FLOW MISMATCH')
                else:
                    print('⚠️  Week 1: Cannot determine - need manual verification')
    else:
        print(f'\n\n❌ NO CACHED WEEKLY PLAN FOUND for mobile: {mobile_id}')
        print('   Weekly plans are generated on-demand when user switches to Weekly View')
        print('\n💡 To generate a weekly plan:')
        print('   1. Login to the app with this mobile number')
        print('   2. Go to Career Roadmap page')
        print('   3. Click "Weekly View" toggle')
        print('   4. Then run this script again')
else:
    print('❌ No roadmaps found in database')

client.close()
