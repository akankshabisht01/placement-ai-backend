"""
Test script to verify the weekly test fix for showing all questions from weekly_tests array
"""
import requests
import json

# Backend URL
BACKEND_URL = "http://localhost:5000"

# Test mobile number (the one with weekly_tests array)
MOBILE = "+91 8864862270"

print("=" * 100)
print("Testing Weekly Test Question Retrieval Fix")
print("=" * 100)

# Test 1: Call /api/weekly-test-generator endpoint
print("\n📞 Test 1: Calling /api/weekly-test-generator")
print("-" * 100)

try:
    response = requests.post(
        f"{BACKEND_URL}/api/weekly-test-generator",
        json={"mobile": MOBILE},
        timeout=10
    )
    
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"Success: {data.get('success')}")
        print(f"Status: {data.get('status')}")
        
        if data.get('success') and data.get('data'):
            test_data = data['data']
            questions = test_data.get('questions', [])
            total_questions = test_data.get('totalQuestions', 0)
            
            print(f"\n✅ Test Data Retrieved:")
            print(f"  Test Title: {test_data.get('testTitle')}")
            print(f"  Week: {test_data.get('week')}, Month: {test_data.get('month')}")
            print(f"  Total Questions: {total_questions}")
            print(f"  Questions Array Length: {len(questions)}")
            
            # Check for array questions
            array_questions = []
            for i, q in enumerate(questions):
                q_text = q.get('question', '').lower()
                skill = q.get('skill', '').lower()
                if 'array' in q_text or 'array' in skill:
                    array_questions.append({
                        'index': i + 1,
                        'text': q.get('question', '')[:80]
                    })
            
            print(f"\n📊 Array-related questions found: {len(array_questions)}")
            for aq in array_questions:
                print(f"  Question {aq['index']}: {aq['text']}")
            
            print(f"\n{'='*100}")
            print(f"✅ FIX VERIFICATION:")
            if total_questions == 40 and len(questions) == 40:
                print(f"  ✅ SUCCESS: All 40 questions are being returned!")
                print(f"  ✅ Before fix: Only 20 questions were returned")
                print(f"  ✅ After fix: All 40 questions from both weekly_tests array elements")
                if array_questions:
                    print(f"  ✅ Array questions are now visible!")
            else:
                print(f"  ❌ ISSUE: Expected 40 questions, got {total_questions}")
        else:
            print(f"❌ Error: {data.get('error')}")
    else:
        print(f"❌ HTTP Error: {response.status_code}")
        print(f"Response: {response.text}")
        
except requests.exceptions.ConnectionError:
    print("❌ ERROR: Cannot connect to backend. Make sure the backend is running on port 5000")
except Exception as e:
    print(f"❌ ERROR: {str(e)}")

print("\n" + "=" * 100)
