import os
from pymongo import MongoClient
from dotenv import load_dotenv
import hashlib

# Load environment variables
load_dotenv()

# Get MongoDB URI
MONGO_URI = os.getenv('MONGO_URI')
print(f"Connecting to MongoDB...")

try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client['Placement_Ai']
    
    # Check if user exists
    user = db.users.find_one({'email': 'test@placementai.com'})
    
    if user:
        print("✅ User found in database!")
        print(f"Email: {user.get('email')}")
        print(f"Mobile: {user.get('mobile')}")
        print(f"User ID: {user.get('_id')}")
        print(f"Password hash (first 30 chars): {user.get('password')[:30]}...")
        
        # Test password verification
        test_password = "Test@123"
        hashed_password = hashlib.sha256(test_password.encode()).hexdigest()
        
        print(f"\nPassword Verification:")
        print(f"Stored hash: {user.get('password')}")
        print(f"Test hash:   {hashed_password}")
        print(f"Match: {user.get('password') == hashed_password}")
    else:
        print("❌ User NOT found in database!")
        print("\nLet's check all users in the collection:")
        all_users = list(db.users.find({}, {'email': 1, 'mobile': 1}))
        print(f"Total users: {len(all_users)}")
        for u in all_users[:5]:  # Show first 5
            print(f"  - {u.get('email')} | {u.get('mobile')}")
            
except Exception as e:
    print(f"❌ Error: {e}")
    print("\nThis is likely a DNS resolution issue.")
    print("Please change your DNS settings to Google DNS (8.8.8.8) or Cloudflare (1.1.1.1)")
