"""
Create sample test data to verify semantic skill matching
"""
from pymongo import MongoClient

# Connect to MongoDB
client = MongoClient('mongodb://localhost:27017/')
db = client['Placement_Ai']

# Sample week_test_result with skillPerformance
test_result = {
    "_id": "+918864862270",
    "mobile": "+918864862270",
    "week": 4,
    "month": 1,
    "scorePercentage": 46.23,  # Overall score
    "skillPerformance": {
        "30 mins review overfitting/underfitting and regularization": 43.4,
        "90 mins build and compare 2-3 models on a small dataset": 49.06
    },
    "completed": True
}

# Insert data
db.week_test_result.delete_many({})  # Clear existing
result = db.week_test_result.insert_one(test_result)

print("✅ Test data created successfully!")
print(f"Inserted document _id: {result.inserted_id}")
print(f"\nSkillPerformance topics:")
for topic, score in test_result['skillPerformance'].items():
    print(f"  - {topic}: {score}%")
