from pymongo import MongoClient
import os
from dotenv import load_dotenv
import json

load_dotenv()

mongo_uri = os.getenv('MONGODB_URI')
client = MongoClient(mongo_uri)
db = client['Placement_Ai']

print("="*100)
print("WEEKLY TEST RELATED COLLECTIONS - DETAILED VIEW")
print("="*100)

weekly_collections = [
    'week_test',
    'week_test_answers', 
    'week_test_result',
    'Weekly_test_analysis',
    'weekly_plans',
    'skill_week_mapping'
]

for col_name in weekly_collections:
    collection = db[col_name]
    count = collection.count_documents({})
    
    print(f"\n{'='*100}")
    print(f"📦 {col_name.upper()}")
    print(f"{'='*100}")
    print(f"Total documents: {count}\n")
    
    if count > 0:
        # Show sample document
        sample = collection.find_one()
        print("Sample document structure:")
        print("-" * 100)
        
        # Pretty print with limited depth
        def print_structure(obj, indent=0, max_depth=3):
            prefix = "  " * indent
            if indent >= max_depth:
                print(f"{prefix}...")
                return
                
            if isinstance(obj, dict):
                for key, value in list(obj.items())[:10]:  # Limit to first 10 keys
                    if isinstance(value, (dict, list)):
                        value_type = f"{type(value).__name__} with {len(value)} items"
                        print(f"{prefix}{key}: <{value_type}>")
                        if indent < 2:  # Show nested structure for first 2 levels
                            print_structure(value, indent+1, max_depth)
                    else:
                        value_str = str(value)[:80] if value else "None"
                        print(f"{prefix}{key}: {value_str}")
                if len(obj) > 10:
                    print(f"{prefix}... and {len(obj) - 10} more fields")
            elif isinstance(obj, list):
                print(f"{prefix}[List with {len(obj)} items]")
                if len(obj) > 0 and indent < 2:
                    print(f"{prefix}First item:")
                    print_structure(obj[0], indent+1, max_depth)
        
        print_structure(sample)
        
        # Show all document IDs for this collection
        print(f"\n{'-' * 100}")
        print(f"All document IDs in {col_name}:")
        docs = list(collection.find({}, {'_id': 1, 'mobile': 1, 'week': 1, 'month': 1}))
        for doc in docs[:20]:  # Show first 20
            id_str = f"_id: {doc['_id']}"
            if 'mobile' in doc:
                id_str += f", mobile: {doc['mobile']}"
            if 'week' in doc:
                id_str += f", week: {doc.get('week')}"
            if 'month' in doc:
                id_str += f", month: {doc.get('month')}"
            print(f"  • {id_str}")
        if len(docs) > 20:
            print(f"  ... and {len(docs) - 20} more documents")

print("\n" + "="*100)
print("SUMMARY")
print("="*100)
print("\n📊 Collections and their purposes:")
print("  • week_test: Stores generated weekly test questions")
print("  • week_test_answers: Stores user's answers to weekly tests")
print("  • week_test_result: Stores completed weekly test results (scores)")
print("  • Weekly_test_analysis: Stores AI-generated analysis of weekly performance")
print("  • weekly_plans: Stores weekly learning plans")
print("  • skill_week_mapping: Maps skills to weeks for curriculum planning")
print("="*100)
