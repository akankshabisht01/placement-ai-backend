"""Check detailed Roadmap_Dashboard content"""
import os
from pymongo import MongoClient
from dotenv import load_dotenv
import json

load_dotenv()

mongo_uri = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
db_name = os.getenv('MONGODB_DB', 'Placement_Ai')

client = MongoClient(mongo_uri)
db = client[db_name]
collection = db['Roadmap_Dashboard ']  # Note: trailing space!

# Get one sample document
doc = collection.find_one()

print(f"\n{'='*80}")
print(f"SAMPLE ROADMAP_DASHBOARD DOCUMENT")
print(f"{'='*80}\n")

# Print full document (pretty)
print(json.dumps(doc, indent=2, default=str))

print(f"\n{'='*80}\n")
