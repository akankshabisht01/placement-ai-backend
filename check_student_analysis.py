from dotenv import load_dotenv
load_dotenv()
import os
from pymongo import MongoClient
import pprint

uri = os.environ.get('MONGODB_URI')
client = MongoClient(uri)
db = client['Placement_Ai']
coll = db['student analysis ']  # Note: has trailing space

print(f"\n{'='*60}")
print(f"Collection: 'student analysis ' (note trailing space)")
print(f"{'='*60}")
print(f"\nTotal documents: {coll.count_documents({})}\n")

# Get all documents
docs = list(coll.find({}))

if docs:
    print(f"Document keys in first doc:")
    print(sorted(docs[0].keys()))
    print(f"\n{'='*60}")
    print(f"All Documents Summary:")
    print(f"{'='*60}\n")
    
    for idx, doc in enumerate(docs, 1):
        print(f"{idx}. ID: {doc.get('_id')}")
        print(f"   Name: {doc.get('name', 'N/A')}")
        print(f"   Email: {doc.get('email', 'N/A')}")
        print(f"   Phone: {doc.get('phone') or doc.get('mobile', 'N/A')}")
        print(f"   Submitted: {doc.get('submittedAt') or doc.get('createdAt', 'N/A')}")
        print()
else:
    print("No documents found.")

print(f"{'='*60}\n")
