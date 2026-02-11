# n8n Webhook Setup for Skills Test

## Overview
This document explains how to configure your n8n workflow to send test questions to the backend API. The test questions are stored **in-memory only** (RAM) and will be lost when the server restarts.

---

## 📍 Webhook Endpoint

### **Backend URL (Local Development)**
```
http://localhost:5000/api/receive-test-questions
```

### **Backend URL (Production)**
```
http://YOUR_DOMAIN/api/receive-test-questions
```

**Method:** `POST`  
**Content-Type:** `application/json`

---

## 📤 Request Format

### JSON Payload Structure

```json
{
  "mobile": "+91 9084113772",
  "testType": "quick",
  "skills": ["Python", "SQL", "Data Cleaning"],
  "questions": [
    {
      "question": "What is a list comprehension in Python?",
      "options": [
        "A way to create lists using a compact syntax",
        "A method to compress lists",
        "A type of loop",
        "None of the above"
      ],
      "correctAnswer": 0,
      "skill": "Python",
      "difficulty": "medium"
    },
    {
      "question": "Which SQL command is used to retrieve data?",
      "options": [
        "INSERT",
        "SELECT",
        "UPDATE",
        "DELETE"
      ],
      "correctAnswer": 1,
      "skill": "SQL",
      "difficulty": "easy"
    }
  ]
}
```

### Field Descriptions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `mobile` | string | ✅ Yes | User's mobile number (with country code) |
| `testType` | string | ❌ No | Test type: "quick" or "comprehensive" (default: "quick") |
| `skills` | array | ❌ No | List of skills being tested |
| `questions` | array | ✅ Yes | Array of question objects (must not be empty) |

### Question Object Structure

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `question` | string | ✅ Yes | The question text |
| `options` | array | ✅ Yes | Array of 4 answer options (strings) |
| `correctAnswer` | number | ✅ Yes | Index of correct answer (0-3) |
| `skill` | string | ❌ No | Skill category (default: "General") |
| `difficulty` | string | ❌ No | Difficulty level: "easy", "medium", "hard" |

---

## ✅ Success Response

**Status Code:** `200 OK`

```json
{
  "success": true,
  "message": "Test questions received and stored in memory (not in database)",
  "data": {
    "testId": "+91 9084113772_quick_1729430400",
    "mobile": "+91 9084113772",
    "testType": "quick",
    "skills": ["Python", "SQL", "Data Cleaning"],
    "totalQuestions": 2,
    "createdAt": "2025-10-20T10:00:00.000000",
    "storage": "memory"
  }
}
```

---

## ❌ Error Responses

### Missing Mobile Number
**Status Code:** `400 Bad Request`
```json
{
  "success": false,
  "error": "Mobile number is required"
}
```

### Empty Questions Array
**Status Code:** `400 Bad Request`
```json
{
  "success": false,
  "error": "Questions array is required and must not be empty"
}
```

### Invalid Question Format
**Status Code:** `400 Bad Request`
```json
{
  "success": false,
  "error": "Question at index 0 is missing required fields (question, options, correctAnswer)"
}
```

---

## 🔄 n8n Workflow Configuration

### Step 1: Add HTTP Request Node

1. In n8n, add an **HTTP Request** node
2. Configure the node:
   - **Method:** POST
   - **URL:** `http://localhost:5000/api/receive-test-questions`
   - **Authentication:** None
   - **Body Content Type:** JSON
   - **Send Body:** Yes
   - **Specify Body:** Using Fields Below

### Step 2: Configure Request Body

Use **JSON** format and map your workflow data:

```json
{
  "mobile": "={{ $node['Get User Data'].json.mobile }}",
  "testType": "quick",
  "skills": "={{ $node['Get Selected Skills'].json.skills }}",
  "questions": "={{ $node['Generate Questions'].json.questions }}"
}
```

### Step 3: Handle Response

Add an **IF** node to check the response:

- **Condition:** `{{ $json.success }} is equal to true`
- **If True:** Proceed to next step (e.g., send notification)
- **If False:** Handle error (e.g., log error, retry)

---

## 🎯 Frontend Integration

### Check for Pending Test

The frontend should call this endpoint to check if a test is available:

```javascript
const response = await fetch(`http://localhost:5000/api/get-test-questions/${mobile}`);
const data = await response.json();

if (data.success) {
  // Test is available
  console.log(`Test ID: ${data.data.testId}`);
  console.log(`Total Questions: ${data.data.totalQuestions}`);
  // Show "Start Test" button
} else {
  // No test available
  console.log('No pending test');
}
```

### Submit Test Answers

When user completes the test:

```javascript
const response = await fetch('http://localhost:5000/api/submit-test-answers', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    mobile: '+91 9084113772',
    testId: 'test_id_from_previous_call',
    answers: [0, 2, 1, 3] // Array of selected option indices
  })
});

const result = await response.json();
console.log(`Score: ${result.data.scorePercentage}%`);
console.log(`Correct: ${result.data.correctAnswers}/${result.data.totalQuestions}`);
```

---

## 🧪 Testing with cURL

### Send Test Questions

```bash
curl -X POST http://localhost:5000/api/receive-test-questions \
  -H "Content-Type: application/json" \
  -d '{
    "mobile": "+91 9084113772",
    "testType": "quick",
    "skills": ["Python", "SQL"],
    "questions": [
      {
        "question": "What is Python?",
        "options": ["A language", "A snake", "A framework", "A database"],
        "correctAnswer": 0,
        "skill": "Python",
        "difficulty": "easy"
      }
    ]
  }'
```

### Get Test Questions

```bash
curl http://localhost:5000/api/get-test-questions/+91%209084113772
```

### Submit Answers

```bash
curl -X POST http://localhost:5000/api/submit-test-answers \
  -H "Content-Type: application/json" \
  -d '{
    "mobile": "+91 9084113772",
    "testId": "test_id_here",
    "answers": [0]
  }'
```

---

## 📊 Backend Console Output

When n8n sends test questions, the backend will print:

```
============================================================
✅ TEST QUESTIONS RECEIVED (Stored in Memory)
============================================================
📱 Mobile: +91 9084113772
📝 Test Type: quick
🎯 Skills: Python, SQL
❓ Total Questions: 10
🔑 Test ID: +91 9084113772_quick_1729430400
💾 Storage: RAM (In-Memory) - NOT SAVED TO DATABASE
============================================================
```

---

## ⚠️ Important Notes

1. **In-Memory Storage:** 
   - Test questions are stored in RAM only
   - Data will be **lost** when the backend server restarts
   - No database persistence

2. **One Test Per User:**
   - Each mobile number can have only **one active test** at a time
   - Sending new questions will **overwrite** the existing test

3. **Security:**
   - Correct answers are **never sent** to the frontend when fetching questions
   - Answers are only used server-side for score calculation

4. **Validation:**
   - All questions must have exactly 4 options
   - `correctAnswer` must be 0, 1, 2, or 3 (index of correct option)

---

## 🔗 API Endpoints Summary

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/receive-test-questions` | POST | Receive questions from n8n |
| `/api/get-test-questions/<mobile>` | GET | Fetch questions for user |
| `/api/submit-test-answers` | POST | Submit answers and get score |

---

## 🚀 Next Steps

1. Configure your n8n workflow with the webhook URL
2. Test the integration using cURL or Postman
3. Verify the backend console shows the received questions
4. Update your frontend Dashboard to fetch and display the test
5. Implement the test interface for users to answer questions

---

**Documentation Last Updated:** October 20, 2025
