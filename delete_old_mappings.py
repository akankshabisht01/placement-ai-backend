from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

# Connect to MongoDB
MONGODB_URI = os.getenv('MONGODB_URI')
client = MongoClient(MONGODB_URI)
db = client['Placement_Ai']

mobile = "8864862270"

print(f"\n{'='*80}")
print(f"DELETING OLD SKILL MAPPINGS FOR {mobile}")
print(f"{'='*80}\n")

# Delete from skill_week_mapping collection
mapping_col = db['skill_week_mapping']
result = mapping_col.delete_one({'_id': mobile})

if result.deleted_count > 0:
    print(f"✅ Deleted {result.deleted_count} skill mapping document")
else:
    print(f"⚠️ No skill mapping found for {mobile}")

print(f"\n{'='*80}\n")
