"""Check weekly test data for user +91 8864862270"""
import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

# Connect to MongoDB
mongo_uri = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
db_name = os.getenv('MONGODB_DB', 'Placement_Ai')
client = MongoClient(mongo_uri)
db = client[db_name]

# User mobile
mobile = "+91 8864862270"
mobile_variants = [
    mobile,
    "8864862270",
    "+918864862270",
    "91 8864862270",
]

print(f"\n{'='*80}")
print(f"📊 CHECKING WEEKLY TEST DATA FOR USER: {mobile}")
print(f"{'='*80}\n")

# 1. Check week_test_result collection
week_test_col = db['week_test_result']
print("🔍 Searching week_test_result collection...")

for variant in mobile_variants:
    results = list(week_test_col.find({'mobile': variant}))
    if results:
        print(f"\n✅ Found {len(results)} document(s) with mobile: {variant}")
        
        for i, result in enumerate(results, 1):
            print(f"\n📄 Document {i}:")
            print(f"   _id: {result.get('_id')}")
            print(f"   Month: {result.get('month')}")
            print(f"   Week: {result.get('week')}")
            print(f"   Overall Score: {result.get('scorePercentage')}%")
            
            skill_perf = result.get('skillPerformance', {})
            if skill_perf:
                print(f"   Skill Performance ({len(skill_perf)} topics):")
                for topic, perf in skill_perf.items():
                    percentage = perf.get('percentage', 0) if isinstance(perf, dict) else perf
                    print(f"      - {topic}: {percentage}%")
            else:
                print(f"   Skill Performance: None")
        break

if not results:
    print("❌ No weekly test results found")

# 2. Check skill_week_mapping
print(f"\n{'='*80}")
print("🗺️  CHECKING SKILL-WEEK MAPPINGS")
print(f"{'='*80}\n")

mapping_col = db['skill_week_mapping']
mobile_id = "8864862270"  # Last 10 digits

mapping_doc = mapping_col.find_one({'_id': mobile_id})

if mapping_doc:
    print(f"✅ Found skill-week mapping for {mobile_id}")
    
    months_data = mapping_doc.get('months', {})
    if months_data:
        print(f"\n📅 Months with mappings: {list(months_data.keys())}")
        
        for month_key, skill_map in months_data.items():
            print(f"\n{month_key.upper()}:")
            if isinstance(skill_map, dict):
                for skill, weeks in skill_map.items():
                    if isinstance(weeks, list):
                        print(f"   {skill}: Weeks {weeks}")
                    else:
                        print(f"   {skill}: Week {weeks}")
    else:
        print("⚠️  No months data in mapping")
else:
    print(f"❌ No skill-week mapping found for {mobile_id}")

# 3. Summary calculation
print(f"\n{'='*80}")
print("📊 SUMMARY: HOW MANY WEEKS USED FOR PERCENTAGE CALCULATION")
print(f"{'='*80}\n")

if results and mapping_doc:
    # Build week data lookup
    week_data = {}
    for result in results:
        month = result.get('month')
        week = result.get('week')
        if month and week:
            week_data[(month, week)] = {
                'overall': result.get('scorePercentage', 0),
                'skillPerformance': result.get('skillPerformance', {})
            }
    
    print(f"Available test data: {list(week_data.keys())}")
    print(f"Total weeks tested: {len(week_data)}")
    
    # For each skill in mapping, show which weeks contribute to its percentage
    months_data = mapping_doc.get('months', {})
    
    print("\n🎯 SKILL RATING CALCULATION:\n")
    
    all_skills = set()
    for month_key, skill_map in months_data.items():
        if isinstance(skill_map, dict):
            all_skills.update(skill_map.keys())
    
    for skill in sorted(all_skills):
        print(f"📌 {skill}:")
        
        # Find which weeks this skill appears in
        skill_weeks = []
        for month_key, skill_map in months_data.items():
            if skill in skill_map:
                weeks = skill_map[skill]
                if isinstance(weeks, list):
                    month_num = int(month_key.split('_')[1])
                    skill_weeks.extend([(month_num, w) for w in weeks])
                elif isinstance(weeks, int):
                    month_num = int(month_key.split('_')[1])
                    skill_weeks.append((month_num, weeks))
        
        print(f"   Mapped to weeks: {skill_weeks}")
        
        # Check which weeks have actual test data
        tested_weeks = [w for w in skill_weeks if w in week_data]
        print(f"   Weeks with test data: {tested_weeks} ({len(tested_weeks)} weeks)")
        
        if tested_weeks:
            percentages = []
            for week_key in tested_weeks:
                week_info = week_data[week_key]
                skill_perf = week_info.get('skillPerformance', {})
                
                # Try to find skill-specific score
                if skill in skill_perf:
                    perf_data = skill_perf[skill]
                    score = perf_data.get('percentage', 0) if isinstance(perf_data, dict) else perf_data
                    percentages.append(score)
                    print(f"      Week {week_key[1]}: {score}% (skill-specific)")
                else:
                    # Use overall score
                    overall = week_info.get('overall', 0)
                    percentages.append(overall)
                    print(f"      Week {week_key[1]}: {overall}% (overall)")
            
            if percentages:
                avg = sum(percentages) / len(percentages)
                stars = 3 if avg >= 90 else 2 if avg >= 70 else 1 if avg >= 50 else 0
                print(f"   ⭐ Average: {avg:.2f}% → {stars} stars")
        else:
            print(f"   ⭕ Not yet tested")
        
        print()

else:
    if not results:
        print("❌ No weekly test results found")
    if not mapping_doc:
        print("❌ No skill-week mappings found")

print(f"{'='*80}\n")

client.close()
