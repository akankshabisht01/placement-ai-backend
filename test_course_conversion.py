from dotenv import load_dotenv
load_dotenv()
import os
from pymongo import MongoClient
import json

# Test the course conversion logic
mobile = '+91 9346333208'

uri = os.environ.get('MONGODB_URI')
client = MongoClient(uri)
db = client['Placement_Ai']
courses_collection = db['Course']

user_courses = courses_collection.find_one({'_id': mobile})

if not user_courses:
    print("❌ No courses found")
    exit()

print("✅ Found course document")

# Get array-based course data
youtube_resources = user_courses.get('youtube_resources', [])
professional_courses = user_courses.get('professional_courses', [])
microsoft_learn = user_courses.get('microsoft_learn_courses', [])

print(f"\n📊 Raw data:")
print(f"  - youtube_resources: {len(youtube_resources)} items (type: {type(youtube_resources).__name__})")
print(f"  - professional_courses: {len(professional_courses)} items (type: {type(professional_courses).__name__})")
print(f"  - microsoft_learn_courses: {len(microsoft_learn)} items (type: {type(microsoft_learn).__name__})")

# Convert array format to skill-keyed format
merged_courses = {}

# Process YouTube resources
if isinstance(youtube_resources, list):
    for course in youtube_resources:
        skill = course.get('skill', 'Unknown')
        if skill not in merged_courses:
            merged_courses[skill] = []
        merged_courses[skill].append(course)
    print(f"\n✅ Processed {len(youtube_resources)} YouTube courses")

# Process professional courses
if isinstance(professional_courses, list):
    for course in professional_courses:
        skill = course.get('skill', 'Unknown')
        if skill not in merged_courses:
            merged_courses[skill] = []
        merged_courses[skill].append(course)
    print(f"✅ Processed {len(professional_courses)} professional courses")

# Process Microsoft Learn courses
if isinstance(microsoft_learn, list):
    for course in microsoft_learn:
        skill = course.get('skill', 'Unknown')
        if skill not in merged_courses:
            merged_courses[skill] = []
        merged_courses[skill].append(course)
    print(f"✅ Processed {len(microsoft_learn)} Microsoft Learn courses")

print(f"\n📚 Final result:")
print(f"  - Total skills: {len(merged_courses)}")
print(f"  - Skills: {list(merged_courses.keys())[:10]}")

# Show sample skill
if merged_courses:
    sample_skill = list(merged_courses.keys())[0]
    print(f"\n🔍 Sample skill: {sample_skill}")
    print(f"  - Number of courses: {len(merged_courses[sample_skill])}")
    print(f"  - First course: {merged_courses[sample_skill][0].get('title', 'N/A')}")

# Test JSON serialization
print("\n🧪 Testing JSON serialization...")
try:
    json_str = json.dumps(merged_courses, indent=2, default=str)
    print(f"✅ JSON serialization successful ({len(json_str)} chars)")
except Exception as e:
    print(f"❌ JSON serialization failed: {e}")
