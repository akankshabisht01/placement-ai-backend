from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()

client = MongoClient(os.getenv('MONGODB_URI'))
doc = client['Placement_Ai']['week_test'].find_one({'_id': '+91 8864862270'})

# Check questions 1-3
for i in range(3):
    q = doc['questions'][i]
    print(f"\n{'='*80}")
    print(f"QUESTION {i+1}")
    print(f"{'='*80}")
    print(f"Question: {q['question_text']}")
    print(f"\nOptions:")
    for j, opt in enumerate(q['options']):
        print(f"  [{j}] {opt}")
    print(f"\nCorrect Answer (stored): {repr(q['correct_answer'])}")
    print(f"Type: {type(q['correct_answer'])}")
    
    # Simulate what backend receives
    print(f"\n--- TESTING LOGIC ---")
    user_answers = ["D) @", "D) Image", "D) Address"]
    user_answer = user_answers[i]
    correct_answer = q['correct_answer']
    
    print(f"User sent: {repr(user_answer)}")
    print(f"Correct answer is: {repr(correct_answer)}")
    
    # Test the matching logic
    normalized_user = user_answer.strip().lower()
    
    if len(str(correct_answer).strip()) == 1 and str(correct_answer).strip().upper() in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
        letter = str(correct_answer).strip().upper()
        print(f"Single letter detected: {letter}")
        
        if normalized_user.startswith(letter.lower() + ')'):
            print(f"✅ Match: User answer starts with '{letter.lower()})'")
            is_correct = True
        else:
            print(f"❌ No match: User answer doesn't start with '{letter.lower()})'")
            is_correct = False
    else:
        print("Not a single letter format")
        is_correct = False
    
    print(f"\nResult: {'CORRECT ✅' if is_correct else 'INCORRECT ❌'}")
