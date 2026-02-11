"""
Create a test user account in MongoDB for testing purposes
"""
from pymongo import MongoClient
from dotenv import load_dotenv
import os
import hashlib
from datetime import datetime

load_dotenv()

# MongoDB connection
mongo_uri = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
db_name = os.getenv('MONGODB_DB', 'Placement_Ai')

client = MongoClient(mongo_uri)
db = client[db_name]
users_collection = db['users']

# Test user credentials
TEST_EMAIL = "test@placementai.com"
TEST_PASSWORD = "Test@123"
TEST_MOBILE = "9999999999"

# Hash password (simple hash - adjust based on your actual auth implementation)
password_hash = hashlib.sha256(TEST_PASSWORD.encode()).hexdigest()

# Create test user document
test_user = {
    'email': TEST_EMAIL,
    'password': password_hash,
    'mobile': TEST_MOBILE,
    'name': 'Test User',
    'isVerified': True,
    'createdAt': datetime.now(),
    'role': 'student'
}

try:
    # Check if test user already exists
    existing_user = users_collection.find_one({'email': TEST_EMAIL})
    
    if existing_user:
        print("⚠️  Test user already exists!")
        print(f"Email: {TEST_EMAIL}")
        print(f"Password: {TEST_PASSWORD}")
    else:
        # Insert test user
        result = users_collection.insert_one(test_user)
        print("✅ Test user created successfully!")
        print("\n" + "="*50)
        print("📧 TEST USER CREDENTIALS")
        print("="*50)
        print(f"Email: {TEST_EMAIL}")
        print(f"Password: {TEST_PASSWORD}")
        print(f"Mobile: {TEST_MOBILE}")
        print("="*50)
        print(f"\nUser ID: {result.inserted_id}")
        
except Exception as e:
    print(f"❌ Error creating test user: {e}")
finally:
    client.close()
