import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

perplexity_api_key = os.getenv('PERPLEXITY_API_KEY')

# Sample month data from the database
month_data = {
    "Skill Focus": "Text Preprocessing & Natural Language Processing (NLP)",
    "Learning Goals": [
        "Master text preprocessing techniques",
        "Understand NLP fundamentals",
        "Build text classification models"
    ],
    "Daily Plan (2 hours/day)": [
        "Week 1: Text Preprocessing - Tokenization, Stemming, Lemmatization",
        "Week 2: Feature Extraction - TF-IDF, Word Embeddings",  
        "Week 3: NLP Models - Classification, Sentiment Analysis",
        "Week 4: Advanced NLP - Named Entity Recognition, Topic Modeling"
    ],
    "Mini Project": "Build a sentiment analysis system",
    "Expected Outcome": "Proficiency in NLP techniques"
}

# Format data
skill_focus = month_data.get('Skill Focus', '')
learning_goals = month_data.get('Learning Goals', [])
daily_plan = month_data.get('Daily Plan (2 hours/day)', [])
mini_project = month_data.get('Mini Project', '')
expected_outcome = month_data.get('Expected Outcome', '')

goals_text = '\n'.join([f"- {goal}" for goal in learning_goals])
weeks_text = '\n'.join(daily_plan)

roadmap_summary = f"""**Skill Focus:** {skill_focus}

**Learning Goals:**
{goals_text}

**Weekly Plan:**
{weeks_text}

**Mini Project:** {mini_project}

**Expected Outcome:** {expected_outcome}
"""

prompt = f"""You are an expert curriculum analyzer. Analyze this monthly learning roadmap and determine IN WHICH WEEKS each skill appears.

**Roadmap:**
{roadmap_summary}

**Task:** Identify all distinct skills mentioned in the Skill Focus, Learning Goals, and Weekly Plan. For each skill, list ALL the weeks (1, 2, 3, or 4) where that skill is taught or practiced.

**Rules:**
1. Parse the "Daily Plan" to identify which skills are covered in which weeks
2. Extract week numbers from text like "Week 1: ...", "Week 2: ...", etc.
3. If a skill spans multiple weeks (e.g., "Python in Week 1, 2, 3"), list ALL those weeks
4. If a skill appears only once (e.g., "Machine Learning in Week 4"), list only that week
5. Break down broad skills into specific sub-skills when mentioned (e.g., "Excel" → "Excel Formulas", "Pivot Tables", "Excel Charts")
6. Each skill should map to an array of week numbers where it appears

**IMPORTANT:** Return ONLY valid JSON mapping skill names to arrays of week numbers.

**Example Output:**
{{
  "Python": [1, 2, 3],
  "Excel Formulas": [1],
  "Data Cleaning": [2],
  "Pivot Tables": [3],
  "Machine Learning": [4]
}}

**Return only the JSON object, no markdown, no explanations.**"""

print("\n" + "="*80)
print("TESTING PERPLEXITY API CALL")
print("="*80 + "\n")

headers = {
    'Authorization': f'Bearer {perplexity_api_key}',
    'Content-Type': 'application/json'
}

payload = {
    'model': 'sonar',
    'messages': [
        {
            'role': 'system',
            'content': 'You are a curriculum analysis expert. Always respond with valid JSON only.'
        },
        {
            'role': 'user',
            'content': prompt
        }
    ],
    'temperature': 0.0,
    'max_tokens': 500
}

print("Calling Perplexity API...")
try:
    response = requests.post(
        'https://api.perplexity.ai/chat/completions',
        headers=headers,
        json=payload,
        timeout=30
    )
    
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        content = result['choices'][0]['message']['content']
        
        print(f"\n✅ SUCCESS! Raw response:")
        print(content)
        
        # Try to parse JSON
        try:
            # Remove markdown code blocks if present
            if '```' in content:
                content = content.split('```')[1]
                if content.startswith('json'):
                    content = content[4:]
            
            skill_mapping = json.loads(content.strip())
            print(f"\n✅ Parsed JSON successfully:")
            print(json.dumps(skill_mapping, indent=2))
            
        except json.JSONDecodeError as e:
            print(f"\n❌ JSON parsing failed: {e}")
            
    else:
        print(f"❌ API Error: {response.status_code}")
        print(response.text)
        
except Exception as e:
    print(f"❌ Exception: {e}")

print("\n" + "="*80 + "\n")
