from dotenv import load_dotenv
load_dotenv()
import os
from pymongo import MongoClient
import pprint

uri = os.environ.get('MONGODB_URI')
client = MongoClient(uri)
db = client['Placement_Ai']
coll = db['Course']

print(f"\n{'='*60}")
print(f"Collection: Course")
print(f"{'='*60}")
print(f"\nTotal documents: {coll.count_documents({})}\n")

# Get all documents
docs = list(coll.find({}))

if docs:
    print(f"Document keys in first doc:")
    print(sorted(docs[0].keys()))
    print(f"\n{'='*60}")
    print(f"All Documents:")
    print(f"{'='*60}\n")
    
    for idx, doc in enumerate(docs, 1):
        print(f"{idx}. ID: {doc.get('_id')}")
        print(f"   Title: {doc.get('title') or doc.get('name') or doc.get('courseName', 'N/A')}")
        
        # Show key fields
        for key in ['domain', 'role', 'category', 'description', 'url', 'link', 'provider', 'duration', 'level']:
            if key in doc:
                value = doc[key]
                if isinstance(value, str) and len(value) > 100:
                    print(f"   {key.capitalize()}: {value[:100]}...")
                else:
                    print(f"   {key.capitalize()}: {value}")
        
        print(f"   All keys: {sorted(doc.keys())}")
        print()
else:
    print("No documents found.")

print(f"{'='*60}\n")
