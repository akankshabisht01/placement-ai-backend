# Quick Reference: n8n to Backend Integration

## 🎯 n8n Webhook URL

```
POST http://localhost:5000/api/receive-test-questions
```

## 📤 JSON Body Format

```json
{
  "mobile": "+91 9084113772",
  "testType": "quick",
  "skills": ["Python", "SQL", "Data Cleaning"],
  "questions": [
    {
      "question": "What is Python?",
      "options": ["A programming language", "A snake", "A framework", "A database"],
      "correctAnswer": 0,
      "skill": "Python",
      "difficulty": "easy"
    },
    {
      "question": "Which SQL command retrieves data?",
      "options": ["INSERT", "SELECT", "UPDATE", "DELETE"],
      "correctAnswer": 1,
      "skill": "SQL",
      "difficulty": "easy"
    }
  ]
}
```

## ✅ Fields Required

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `mobile` | ✅ Yes | string | User's mobile number |
| `testType` | No | string | "quick" or "comprehensive" |
| `skills` | No | array | List of skills |
| `questions` | ✅ Yes | array | Must have at least 1 question |

## 📋 Question Object

| Field | Required | Type | Values |
|-------|----------|------|--------|
| `question` | ✅ Yes | string | Question text |
| `options` | ✅ Yes | array | 4 answer options |
| `correctAnswer` | ✅ Yes | number | 0, 1, 2, or 3 |
| `skill` | No | string | Skill category |
| `difficulty` | No | string | "easy", "medium", "hard" |

## 🧪 Test with cURL

```bash
curl -X POST http://localhost:5000/api/receive-test-questions \
  -H "Content-Type: application/json" \
  -d '{
    "mobile": "+91 9084113772",
    "testType": "quick",
    "skills": ["Python"],
    "questions": [
      {
        "question": "What is Python?",
        "options": ["Language", "Snake", "Framework", "Database"],
        "correctAnswer": 0,
        "skill": "Python",
        "difficulty": "easy"
      }
    ]
  }'
```

## ✅ Success Response

```json
{
  "success": true,
  "message": "Test questions received and stored in memory (not in database)",
  "data": {
    "testId": "+91 9084113772_quick_1729430400",
    "mobile": "+91 9084113772",
    "testType": "quick",
    "totalQuestions": 1,
    "storage": "memory"
  }
}
```

## ❌ Common Errors

### Missing mobile
```json
{"success": false, "error": "Mobile number is required"}
```

### Empty questions
```json
{"success": false, "error": "Questions array is required and must not be empty"}
```

### Invalid question
```json
{"success": false, "error": "Question at index 0 is missing required fields (question, options, correctAnswer)"}
```

## 📝 Notes

- ⚠️ Data stored in **RAM only** (lost on server restart)
- ⚠️ One test per mobile (new test overwrites old)
- ⚠️ Correct answers **never sent** to frontend
- ✅ Instant score calculation
- ✅ Skill-wise performance tracking
