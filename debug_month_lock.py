from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

# Connect to MongoDB
mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI")
client = MongoClient(mongo_uri)
db = client[os.getenv("MONGODB_DB", "Placement_Ai")]

# Check Weekly_test_analysis collection
analysis_collection = db["Weekly_test_analysis"]
monthly_result_collection = db["monthly_test_result"]
monthly_analysis_collection = db["monthly_test_analysis"]

print("="*80)
print("CHECKING USERS WITH COMPLETED WEEKLY TESTS")
print("="*80)

# Find all unique mobile numbers in Weekly_test_analysis
all_analyses = list(analysis_collection.find())
print(f"\nTotal documents in Weekly_test_analysis: {len(all_analyses)}")

# Group by mobile number
from collections import defaultdict
mobile_weeks = defaultdict(list)

for doc in all_analyses:
    mobile = doc.get('mobile', 'Unknown')
    if 'analysis' in doc and 'week' in doc['analysis']:
        week = doc['analysis']['week']
        mobile_weeks[mobile].append(week)

print(f"\nFound {len(mobile_weeks)} unique users with weekly test data:")

for mobile, weeks in mobile_weeks.items():
    weeks_sorted = sorted(weeks)
    completed_count = len(weeks_sorted)
    
    print(f"\n{'='*80}")
    print(f"Mobile: {mobile}")
    print(f"Completed weeks: {weeks_sorted} (Total: {completed_count})")
    
    # Check if they have 4 weeks (Month 1 eligible)
    if completed_count >= 4:
        print(f"✅ ELIGIBLE for Month 1 (completed 4+ weeks)")
        
        # Calculate which months should be unlocked
        months_eligible = []
        for month in [1, 2, 3]:
            month_weeks = list(range((month-1)*4 + 1, month*4 + 1))
            if all(w in weeks_sorted for w in month_weeks):
                months_eligible.append(month)
        
        print(f"Months eligible based on weeks: {months_eligible}")
        
        # Check monthly test results
        for month in months_eligible:
            result_id = f"{mobile}_month_{month}"
            result = monthly_result_collection.find_one({'_id': result_id})
            
            if result:
                score = result.get('totalScore', 0)
                total = result.get('totalMarks', 100)
                percentage = (score / total * 100) if total > 0 else 0
                passed = percentage >= 50
                print(f"  Month {month} test: {'✅ PASSED' if passed else '❌ FAILED'} ({percentage:.1f}%)")
            else:
                print(f"  Month {month} test: ⏳ NOT TAKEN YET")
            
            # Check monthly analysis
            analysis = monthly_analysis_collection.find_one({'mobile': mobile, 'month': month})
            if analysis:
                print(f"  Month {month} analysis: ✅ EXISTS")
            else:
                print(f"  Month {month} analysis: ❌ NOT FOUND")
    else:
        weeks_needed = 4 - completed_count
        print(f"❌ NOT ELIGIBLE (needs {weeks_needed} more weeks)")

print(f"\n{'='*80}\n")

# Now simulate the backend endpoint logic
print("SIMULATING /api/check-month-test-eligibility LOGIC:")
print("="*80)

for mobile in mobile_weeks.keys():
    print(f"\nChecking eligibility for: {mobile}")
    
    # Normalize mobile formats
    normalized_mobile = mobile.replace("+", "").replace(" ", "").replace("-", "")
    mobile_10 = normalized_mobile[-10:] if len(normalized_mobile) >= 10 else normalized_mobile
    
    search_ids = [mobile, normalized_mobile, mobile_10]
    if len(normalized_mobile) == 10:
        search_ids.extend([
            f"91{normalized_mobile}",
            f"+91{normalized_mobile}",
            f"+91 {mobile_10}"
        ])
    
    print(f"  Search patterns: {search_ids}")
    
    # Find all analyses
    completed_weeks = []
    for search_id in search_ids:
        analyses = list(analysis_collection.find({'mobile': search_id}))
        for analysis in analyses:
            if 'analysis' in analysis and 'week' in analysis['analysis']:
                week = analysis['analysis']['week']
                if week not in completed_weeks:
                    completed_weeks.append(week)
    
    completed_weeks.sort()
    print(f"  Found completed weeks: {completed_weeks}")
    
    # Calculate month unlock status
    unlocked_months = []
    for month in [1, 2, 3]:
        expected_weeks = list(range((month-1)*4 + 1, month*4 + 1))
        month_weeks_completed = [w for w in completed_weeks if w in expected_weeks]
        
        all_weeks_done = len(month_weeks_completed) == 4 and month_weeks_completed == expected_weeks
        
        if all_weeks_done:
            # Check if previous month passed (if not month 1)
            can_unlock = True
            if month > 1:
                prev_month = month - 1
                prev_result_id = f"{mobile}_month_{prev_month}"
                prev_result = monthly_result_collection.find_one({'_id': prev_result_id})
                
                if prev_result:
                    score = prev_result.get('totalScore', 0)
                    total = prev_result.get('totalMarks', 100)
                    percentage = (score / total * 100) if total > 0 else 0
                    can_unlock = percentage >= 50
                    print(f"  Month {prev_month} must pass: {'✅ Passed' if can_unlock else '❌ Failed'} ({percentage:.1f}%)")
                else:
                    can_unlock = False
                    print(f"  Month {prev_month} must pass: ❌ Not taken yet")
            
            if can_unlock:
                unlocked_months.append(month)
    
    print(f"  UNLOCKED MONTHS: {unlocked_months}")
    if not unlocked_months and len(completed_weeks) >= 4:
        print("  ⚠️ WARNING: User has 4+ weeks but no unlocked months!")

client.close()
