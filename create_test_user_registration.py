from pymongo import MongoClient
from dotenv import load_dotenv
import os
import hashlib

load_dotenv()

# Get MongoDB URI
MONGO_URI = os.getenv('MONGO_URI')
print(f"Creating test user in Registration collection...")

try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client['Placement_Ai']
    
    # Create test user in REGISTRATION collection (not users)
    registration_col = db['Registration']
    
    # Check if user already exists
    existing_user = registration_col.find_one({'email': 'test@placementai.com'})
    
    if existing_user:
        print("⚠️ Test user already exists in Registration collection!")
        print(f"Username: {existing_user.get('_id')}")
        print(f"Email: {existing_user.get('email')}")
    else:
        # Create new test user
        test_user = {
            '_id': 'testuser',  # Username is stored as _id
            'firstName': 'Test',
            'lastName': 'User',
            'email': 'test@placementai.com',
            'passwordHash': hashlib.sha256('Test@123'.encode()).hexdigest(),
            'registrationDate': '2024-12-10'
        }
        
        result = registration_col.insert_one(test_user)
        
        print("✅ Test user created successfully in Registration collection!")
        print("=" * 50)
        print("📧 TEST USER CREDENTIALS")
        print("=" * 50)
        print(f"Email: test@placementai.com")
        print(f"Username: testuser")
        print(f"Password: Test@123")
        print("=" * 50)
        print(f"User ID: {result.inserted_id}")
        
except Exception as e:
    print(f"❌ Error: {e}")
    print("\nThis is likely a DNS resolution issue.")
    print("Please change your DNS settings to:")
    print("  - Google DNS: 8.8.8.8")
    print("  - Cloudflare DNS: 1.1.1.1")
