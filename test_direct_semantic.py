"""
Test semantic matching directly without API
"""
from pymongo import MongoClient
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

print("="*100)
print("TESTING SEMANTIC SKILL MATCHING DIRECTLY")
print("="*100)

# Connect to database
client = MongoClient('mongodb://localhost:27017/')
db = client['Placement_Ai']

# Get user's week test result
result = db.week_test_result.find_one({'_id': '+918864862270'})

if not result:
    print("❌ No test result found")
    exit(1)

print(f"\n✅ Found test result for {result['_id']}")
print(f"Week {result['week']}, Month {result['month']}")
print(f"Overall score: {result['scorePercentage']}%")
print(f"\nSkill Performance:")
for topic, score in result['skillPerformance'].items():
    print(f"  - {topic}: {score}%")

# Load semantic model
print("\n" + "="*100)
print("Loading sentence transformer model...")
model = SentenceTransformer('all-MiniLM-L6-v2')
print("✅ Model loaded")

# Test skills
test_skills = [
    "Machine Learning Fundamentals",
    "Machine Learning Models",
    "scikit-learn",
    "Python",
    "Data Science"
]

print("\n" + "="*100)
print("SEMANTIC MATCHING RESULTS")
print("="*100)

for skill in test_skills:
    print(f"\n🔍 Skill: {skill}")
    
    # Get skill embedding
    skill_embedding = model.encode([skill], convert_to_tensor=False)
    
    best_match = None
    best_score_val = None
    best_similarity = 0
    
    for topic, score in result['skillPerformance'].items():
        # Get topic embedding
        topic_embedding = model.encode([topic], convert_to_tensor=False)
        
        # Calculate similarity
        similarity = cosine_similarity(skill_embedding, topic_embedding)[0][0]
        
        print(f"   Topic: {topic}")
        print(f"   Similarity: {similarity:.3f}")
        print(f"   Score: {score}%")
        
        if similarity > best_similarity:
            best_similarity = similarity
            best_match = topic
            best_score_val = score
    
    print(f"\n   ✅ BEST MATCH: {best_match}")
    print(f"   Similarity: {best_similarity:.3f}")
    print(f"   Score: {best_score_val}%")
    print("   " + "-"*80)

print("\n" + "="*100)
print("✅ TEST COMPLETE")
print("="*100)
