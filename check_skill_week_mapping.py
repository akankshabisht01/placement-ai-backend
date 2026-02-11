import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from pymongo import MongoClient
from dotenv import load_dotenv
import json

load_dotenv()

# MongoDB connection
mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
db_name = os.getenv('MONGODB_DB', 'Placement_Ai')
client = MongoClient(mongo_uri)
db = client[db_name]

mobile = "8864862270"  # normalized ID format

print(f"\n{'='*80}")
print(f"CHECKING skill_week_mapping COLLECTION FOR: {mobile}")
print(f"{'='*80}\n")

# Check skill_week_mapping collection
mapping_col = db['skill_week_mapping']
mapping_doc = mapping_col.find_one({'_id': mobile})

if mapping_doc:
    print("✅ Mapping document found!\n")
    print(f"Document ID: {mapping_doc.get('_id')}")
    print(f"Created/Updated: {mapping_doc.get('createdAt', 'N/A')}\n")
    
    # Show structure
    months = mapping_doc.get('months', {})
    print(f"📊 Total Months Mapped: {len(months)}\n")
    
    for month_key, month_data in sorted(months.items()):
        print(f"\n{'─'*80}")
        print(f"MONTH {month_key}")
        print(f"{'─'*80}")
        
        weeks = month_data.get('weeks', {})
        print(f"Weeks in this month: {len(weeks)}\n")
        
        for week_key, week_data in sorted(weeks.items()):
            print(f"  Week {week_key}:")
            skills = week_data.get('skills', [])
            print(f"    Skills taught: {len(skills)}")
            for skill in skills[:5]:  # Show first 5 skills
                print(f"      - {skill}")
            if len(skills) > 5:
                print(f"      ... and {len(skills) - 5} more")
            print()
    
    # Show full JSON structure (first month only for brevity)
    print(f"\n{'='*80}")
    print("SAMPLE DATA STRUCTURE (Month 1):")
    print(f"{'='*80}")
    if '1' in months or 1 in months:
        month_1 = months.get('1') or months.get(1)
        print(json.dumps(month_1, indent=2, default=str))
    
else:
    print("❌ No skill_week_mapping found for this user!")
    print("\nThis collection is populated by:")
    print("1. /api/generate-skill-mappings-from-roadmap endpoint")
    print("2. Analyzing Roadmap_Dashboard data with Perplexity AI")
    print("3. Extracting which skills are taught in which weeks")

print(f"\n{'='*80}")
print("DATA SOURCE FOR skill_week_mapping:")
print(f"{'='*80}")
print("📚 Source: Roadmap_Dashboard collection")
print("🤖 Method: Perplexity AI analyzes roadmap content")
print("📝 Purpose: Maps skills to specific weeks they're taught")
print("🎯 Usage: Determines when skills move from 'In Progress' to 'Completed'")
