from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()

client = MongoClient(os.getenv('MONGODB_URI'))
doc = client['Placement_Ai']['week_test'].find_one({'_id': '+91 8864862270'})

q = doc['questions'][0]
print('='*80)
print('FIRST QUESTION ANALYSIS')
print('='*80)
print(f'\nQuestion: {q["question_text"]}')
print(f'\nOptions:')
for i, opt in enumerate(q['options']):
    print(f'  [{i}] {opt}')
print(f'\nCorrect Answer: {repr(q["correct_answer"])}')
print(f'Correct Answer Type: {type(q["correct_answer"])}')
print('\n' + '='*80)
