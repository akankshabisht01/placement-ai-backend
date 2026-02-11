from pymongo import MongoClient
from dotenv import load_dotenv
import os
import re

load_dotenv()

client = MongoClient(os.getenv('MONGODB_URI'))
doc = client['Placement_Ai']['week_test'].find_one({'_id': '+91 8864862270'})

def normalize_text(val):
    try:
        s = str(val)
    except Exception:
        s = ''
    # Remove simple HTML tags
    s = re.sub(r'<[^>]*>', '', s)
    # Collapse whitespace
    s = ' '.join(s.split())
    return s.strip().lower()

print('='*80)
print('TESTING ANSWER MATCHING LOGIC')
print('='*80)

# Test first 3 questions
for i in range(3):
    q = doc['questions'][i]
    correct = q['correct_answer']
    options = q['options']
    
    print(f'\n--- Question {i+1} ---')
    print(f'Question: {q["question_text"][:50]}...')
    print(f'\nOptions:')
    for j, opt in enumerate(options):
        print(f'  [{j}] {opt}')
    print(f'\nCorrect Answer (stored): {repr(correct)}')
    print(f'Correct Answer Type: {type(correct).__name__}')
    
    # Simulate what user might send based on screenshot
    if i == 0:
        user_answer = "D) @"
    elif i == 1:
        user_answer = "D) Image"
    elif i == 2:
        user_answer = "D) Address"
    
    print(f'User Answer: {repr(user_answer)}')
    
    # Apply the matching logic
    normalized_user = normalize_text(user_answer)
    normalized_correct = normalize_text(correct)
    
    print(f'Normalized User: {repr(normalized_user)}')
    print(f'Normalized Correct: {repr(normalized_correct)}')
    
    # Check if correct_answer is a single letter
    is_correct = False
    if len(str(correct).strip()) == 1 and str(correct).strip().upper() in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
        letter = str(correct).strip().upper()
        print(f'Single letter detected: {letter}')
        
        # Check if user answer starts with "A)", "a)", etc.
        if normalized_user.startswith(letter.lower() + ')') or normalized_user.startswith(letter.lower() + ' '):
            print(f'✅ MATCH: User answer starts with "{letter.lower()})"')
            is_correct = True
        else:
            print(f'❌ NO MATCH: User answer does NOT start with "{letter.lower()})"')
            is_correct = False
    else:
        print('Not a single letter - using direct comparison')
        is_correct = normalized_user == normalized_correct
    
    print(f'\n{"✅ CORRECT" if is_correct else "❌ INCORRECT"}')
    print('='*80)
