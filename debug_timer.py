from pymongo import MongoClient
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
mongo_uri = os.getenv('MONGO_URI') or os.getenv('MONGODB_URI')
client = MongoClient(mongo_uri)
db = client['Placement_Ai']

# Check analysis_timer_tracking collection
print('=== Analysis Timer Tracking Documents ===')
docs = list(db['analysis_timer_tracking'].find({}).limit(10))
if not docs:
    print('No tracking documents found!')
else:
    for doc in docs:
        print(f"_id: {doc.get('_id')}")
        print(f"mobile: {doc.get('mobile')}")
        print(f"type: {doc.get('type')}")
        print(f"week: {doc.get('week')}")
        print(f"month: {doc.get('month')}")
        completed_at = doc.get('completed_at')
        print(f"completed_at: {completed_at}")
        
        # Calculate elapsed time
        if completed_at:
            now = datetime.utcnow()
            elapsed = (now - completed_at).total_seconds()
            print(f"Current UTC time: {now}")
            print(f"Elapsed seconds: {elapsed}")
            
            # Week 9 is not divisible by 4, so timer is 300 seconds
            week = doc.get('week', 1)
            timer_duration = 180 if (week % 4 == 0) else 300
            remaining = timer_duration - elapsed
            print(f"Timer duration: {timer_duration}s")
            print(f"Remaining: {remaining}s")
        print('---')
    
client.close()
