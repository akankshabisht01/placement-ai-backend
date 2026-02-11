# Loading Questions & Facts System

## Overview
This system provides interactive questions and motivational facts during loading screens to:
1. **Engage users** during wait times
2. **Collect valuable preference data** for personalization
3. **Enable targeted coupon delivery** based on user interests

## Database Collections

### 1. `loading_questions`
Stores interactive questions with multiple-choice options.

**Schema:**
```json
{
  "question_id": "coffee_preference",
  "category": "lifestyle",
  "question_text": "What's your go-to coffee order?",
  "question_type": "single_choice",
  "icon_emoji": "☕",
  "options": [
    {
      "option_id": "espresso",
      "text": "Espresso",
      "icon": "☕",
      "coupon_category": "coffee_shops"
    }
  ],
  "display_contexts": ["registration_loading", "quiz_submission"],
  "weight": 10,
  "active": true,
  "created_at": "2025-12-05T..."
}
```

**Fields:**
- `question_id`: Unique identifier
- `category`: lifestyle, career, personality, tech, fun
- `question_type`: single_choice or multiple_choice
- `display_contexts`: Where to show this question
- `weight`: Higher weight = more likely to be shown (1-10)
- `coupon_category`: Used for matching coupons to user preferences

### 2. `loading_facts`
Stores motivational facts and tips.

**Schema:**
```json
{
  "fact_id": "fact_001",
  "category": "tech_history",
  "fact_text": "💡 Did you know? The first computer bug was an actual moth!",
  "icon": "💡",
  "display_contexts": ["all"],
  "weight": 8,
  "active": true,
  "created_at": "2025-12-05T..."
}
```

### 3. `loading_question_responses`
Stores user responses to questions.

**Schema:**
```json
{
  "user_id": "user123",
  "question_id": "coffee_preference",
  "selected_options": ["espresso"],
  "context": "registration_loading",
  "response_time_ms": 1500,
  "timestamp": "2025-12-05T..."
}
```

## API Endpoints

### 1. Get Random Question
**Endpoint:** `GET /api/loading/question`

**Query Parameters:**
- `context` (optional): Filter by context (registration_loading, quiz_submission, etc.)
- `user_id` (optional): Avoids showing recently answered questions

**Example Request:**
```javascript
fetch('http://localhost:5000/api/loading/question?context=registration_loading&user_id=user123')
```

**Response:**
```json
{
  "success": true,
  "question": {
    "question_id": "coffee_preference",
    "category": "lifestyle",
    "question_text": "What's your go-to coffee order?",
    "icon_emoji": "☕",
    "options": [...]
  }
}
```

### 2. Get Random Fact
**Endpoint:** `GET /api/loading/fact`

**Query Parameters:**
- `category` (optional): Filter by category

**Example Request:**
```javascript
fetch('http://localhost:5000/api/loading/fact')
```

**Response:**
```json
{
  "success": true,
  "fact": {
    "fact_id": "fact_001",
    "fact_text": "💡 Did you know? The first computer bug was an actual moth!",
    "icon": "💡"
  }
}
```

### 3. Save Response
**Endpoint:** `POST /api/loading/response`

**Request Body:**
```json
{
  "user_id": "user123",
  "question_id": "coffee_preference",
  "selected_options": ["espresso"],
  "context": "registration_loading",
  "response_time_ms": 1500
}
```

**Response:**
```json
{
  "success": true,
  "message": "Response saved successfully",
  "response_id": "507f1f77bcf86cd799439011"
}
```

### 4. Get User Preferences
**Endpoint:** `GET /api/loading/user-preferences/{user_id}`

**Example Request:**
```javascript
fetch('http://localhost:5000/api/loading/user-preferences/user123')
```

**Response:**
```json
{
  "success": true,
  "user_id": "user123",
  "preferences": {
    "lifestyle": [
      {
        "question": "What's your go-to coffee order?",
        "answer": "Espresso",
        "icon": "☕",
        "timestamp": "2025-12-05T..."
      }
    ]
  },
  "coupon_categories": ["coffee_shops", "online_courses"],
  "total_responses": 5
}
```

### 5. Get Statistics
**Endpoint:** `GET /api/loading/stats`

**Response:**
```json
{
  "success": true,
  "stats": {
    "total_questions": 17,
    "total_facts": 15,
    "total_responses": 1234,
    "questions_by_category": {
      "lifestyle": 4,
      "career": 4,
      "tech": 5
    },
    "most_answered_questions": [...]
  }
}
```

## Integration Guide

### Frontend Integration

#### 1. During Loading Screens

```javascript
// Show question during loading
async function showLoadingQuestion() {
    const context = 'registration_loading'; // or quiz_submission, etc.
    const userId = getCurrentUserId();
    
    try {
        const response = await fetch(
            `http://localhost:5000/api/loading/question?context=${context}&user_id=${userId}`
        );
        const data = await response.json();
        
        if (data.success) {
            displayQuestion(data.question);
        }
    } catch (error) {
        console.error('Failed to load question:', error);
        // Show fact as fallback
        showLoadingFact();
    }
}

function displayQuestion(question) {
    const html = `
        <div class="loading-question">
            <h3>${question.icon_emoji} ${question.question_text}</h3>
            <div class="options">
                ${question.options.map(opt => `
                    <button onclick="selectOption('${opt.option_id}')">
                        ${opt.icon} ${opt.text}
                    </button>
                `).join('')}
            </div>
        </div>
    `;
    document.getElementById('loadingContainer').innerHTML = html;
}
```

#### 2. Save User Response

```javascript
async function saveResponse(questionId, selectedOptionId) {
    const userId = getCurrentUserId();
    const context = 'registration_loading';
    const responseTime = Date.now() - startTime;
    
    try {
        const response = await fetch('http://localhost:5000/api/loading/response', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                user_id: userId,
                question_id: questionId,
                selected_options: [selectedOptionId],
                context: context,
                response_time_ms: responseTime
            })
        });
        
        const data = await response.json();
        if (data.success) {
            console.log('Response saved!');
        }
    } catch (error) {
        console.error('Failed to save response:', error);
    }
}
```

#### 3. Show Facts as Alternative

```javascript
async function showLoadingFact() {
    try {
        const response = await fetch('http://localhost:5000/api/loading/fact');
        const data = await response.json();
        
        if (data.success) {
            const html = `
                <div class="loading-fact">
                    ${data.fact.icon} ${data.fact.fact_text}
                </div>
            `;
            document.getElementById('loadingContainer').innerHTML = html;
        }
    } catch (error) {
        console.error('Failed to load fact:', error);
    }
}
```

### React Integration Example

```jsx
import React, { useState, useEffect } from 'react';

function LoadingQuestion({ context, userId }) {
    const [question, setQuestion] = useState(null);
    const [selectedOption, setSelectedOption] = useState(null);
    const [startTime] = useState(Date.now());

    useEffect(() => {
        loadQuestion();
    }, []);

    const loadQuestion = async () => {
        try {
            const response = await fetch(
                `http://localhost:5000/api/loading/question?context=${context}&user_id=${userId}`
            );
            const data = await response.json();
            if (data.success) {
                setQuestion(data.question);
            }
        } catch (error) {
            console.error('Failed to load question:', error);
        }
    };

    const handleSubmit = async () => {
        if (!selectedOption) return;

        const responseTime = Date.now() - startTime;
        
        try {
            const response = await fetch('http://localhost:5000/api/loading/response', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    user_id: userId,
                    question_id: question.question_id,
                    selected_options: [selectedOption],
                    context: context,
                    response_time_ms: responseTime
                })
            });
            
            const data = await response.json();
            if (data.success) {
                console.log('Response saved!');
            }
        } catch (error) {
            console.error('Failed to save response:', error);
        }
    };

    if (!question) return <div>Loading...</div>;

    return (
        <div className="loading-question">
            <h3>{question.icon_emoji} {question.question_text}</h3>
            <div className="options">
                {question.options.map(option => (
                    <button
                        key={option.option_id}
                        onClick={() => setSelectedOption(option.option_id)}
                        className={selectedOption === option.option_id ? 'selected' : ''}
                    >
                        {option.icon} {option.text}
                    </button>
                ))}
            </div>
            <button onClick={handleSubmit} disabled={!selectedOption}>
                Submit
            </button>
        </div>
    );
}

export default LoadingQuestion;
```

## Coupon Matching Strategy

Use the `coupon_categories` from user preferences to deliver targeted coupons:

```javascript
async function getUserCouponCategories(userId) {
    const response = await fetch(
        `http://localhost:5000/api/loading/user-preferences/${userId}`
    );
    const data = await response.json();
    
    if (data.success) {
        return data.coupon_categories;
        // Example: ["coffee_shops", "online_courses", "fitness"]
    }
    return [];
}

// Match coupons to user preferences
function matchCoupons(userCategories, availableCoupons) {
    return availableCoupons.filter(coupon => 
        userCategories.includes(coupon.category)
    );
}
```

## Display Contexts

Use these contexts to show relevant questions at the right time:

- `registration_loading` - During user registration
- `quiz_submission` - While processing quiz results
- `profile_update` - During profile updates
- `resume_analysis` - While analyzing resume
- `all` - Can be shown anywhere

## Best Practices

1. **Show questions during actual loading** - Only display when there's a genuine wait time
2. **Rotate between questions and facts** - Mix educational content with interactive elements
3. **Respect user time** - Keep questions simple and quick to answer
4. **Store responses asynchronously** - Don't block the main loading process
5. **Use weighted random selection** - Show more important questions more frequently
6. **Track response time** - Understand user engagement
7. **Avoid repetition** - Use `user_id` parameter to avoid showing same questions

## Testing

Use the demo page to test the system:
```
http://localhost:5000/templates/loading_questions_demo.html
```

## Future Enhancements

1. **A/B Testing** - Test different question formats
2. **Analytics Dashboard** - Visualize response patterns
3. **Smart Recommendations** - ML-based coupon matching
4. **Gamification** - Points/badges for answering questions
5. **Social Sharing** - Let users share their preferences
6. **Dynamic Coupons** - Auto-generate coupons based on responses
