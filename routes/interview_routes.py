"""
Interview Module Routes - Flask Integration
Provides AI interview functionality integrated with existing Placement AI system
"""
from flask import Blueprint, request, jsonify, session
from datetime import datetime
import os
import json
import re
import requests
from utils.db import get_db
from bson import ObjectId

interview_bp = Blueprint('interview', __name__, url_prefix='/api/interview')

# Perplexity API configuration
PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"

def clean_ai_response(text):
    """Remove Perplexity citation markers [1], [2], etc. and clean response"""
    if not text:
        return text
    # Remove citation markers like [1], [2], [1][2], etc.
    cleaned = re.sub(r'\[\d+\]', '', text)
    # Remove multiple spaces that may result
    cleaned = re.sub(r'\s+', ' ', cleaned)
    # Remove any leading/trailing whitespace
    return cleaned.strip()

def get_perplexity_key():
    """Get Perplexity API key from environment at request time"""
    key = os.getenv('PERPLEXITY_API_KEY')
    if not key:
        print("❌ PERPLEXITY_API_KEY not found in environment variables!")
    return key

# Validate key at startup
_startup_key = os.getenv('PERPLEXITY_API_KEY')
if _startup_key:
    print(f"✅ Perplexity API key loaded: {_startup_key[:8]}...{_startup_key[-4:]}")
else:
    print("❌ WARNING: PERPLEXITY_API_KEY not set in .env file!")

# In-memory session storage (replace with Redis in production)
active_sessions = {}

class InterviewSession:
    def __init__(self, session_id, user_name, phone_number, position="Software Developer"):
        self.session_id = session_id
        self.user_name = user_name
        self.phone_number = phone_number
        self.position = position
        self.state = "greeting"
        self.question_count = 0
        self.conversation_history = []
        self.started_at = datetime.utcnow()
        self.questions_asked = []
        self.answers = []
    
    def to_dict(self):
        return {
            "session_id": self.session_id,
            "user_name": self.user_name,
            "phone_number": self.phone_number,
            "position": self.position,
            "state": self.state,
            "question_count": self.question_count,
            "conversation_history": self.conversation_history,
            "started_at": self.started_at.isoformat(),
            "questions_asked": self.questions_asked,
            "answers": self.answers
        }

@interview_bp.route('/start', methods=['POST'])
def start_interview():
    """Start a new interview session"""
    try:
        data = request.get_json()
        user_name = data.get('name', 'Candidate')
        phone_number = data.get('phone_number', '')
        position = data.get('position', 'Software Developer')
        
        # Generate session ID
        session_id = f"interview_{datetime.now().timestamp()}"
        
        # Create new interview session
        interview_session = InterviewSession(session_id, user_name, phone_number, position)
        active_sessions[session_id] = interview_session
        
        # Generate greeting
        greeting = f"Hello {user_name}! I'm Alex, your AI interviewer. I'll be conducting a mock interview for the {position} position. How are you doing today?"
        
        return jsonify({
            "success": True,
            "session_id": session_id,
            "message": greeting,
            "state": "greeting",
            "should_speak": True
        })
    
    except Exception as e:
        print(f"Error starting interview: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@interview_bp.route('/respond', methods=['POST'])
def process_response():
    """Process user's response and generate next question"""
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        user_message = data.get('message', '')
        
        # Get session
        if session_id not in active_sessions:
            return jsonify({
                "success": False,
                "error": "Session not found"
            }), 404
        
        interview_session = active_sessions[session_id]
        
        # Add user message to history
        interview_session.conversation_history.append({
            "role": "user",
            "content": user_message
        })
        interview_session.answers.append(user_message)
        
        # Generate AI response using Perplexity
        system_prompt = get_system_prompt(interview_session)
        
        try:
            # Get API key dynamically
            api_key = get_perplexity_key()
            if not api_key:
                print("❌ No Perplexity API key available, using fallback questions")
                raise Exception("PERPLEXITY_API_KEY not configured")
            
            print(f"[Interview] Calling Perplexity API with key: {api_key[:8]}...")
            
            # Call Perplexity API
            response = requests.post(
                PERPLEXITY_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "sonar",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        *interview_session.conversation_history[-6:]
                    ],
                    "temperature": 0.7,
                    "max_tokens": 150
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                ai_message = clean_ai_response(result['choices'][0]['message']['content'])
                
                # Update conversation history
                interview_session.conversation_history.append({
                    "role": "assistant",
                    "content": ai_message
                })
                interview_session.questions_asked.append(ai_message)
                
                # Update state
                update_interview_state(interview_session)
                
                return jsonify({
                    "success": True,
                    "message": ai_message,
                    "state": interview_session.state,
                    "question_count": interview_session.question_count,
                    "should_speak": True
                })
            elif response.status_code == 401:
                print(f"❌ Perplexity API 401 Unauthorized - API key may be expired or invalid")
                print(f"   Key used: {api_key[:8]}...{api_key[-4:]}")
                print(f"   Please check your PERPLEXITY_API_KEY in .env file")
                # Fall through to fallback questions
                raise Exception("Perplexity API key unauthorized (401)")
            else:
                print(f"Perplexity API error: {response.status_code} - {response.text[:200]}")
                raise Exception(f"Perplexity API error {response.status_code}")
        
        except Exception as e:
            print(f"Error calling Perplexity API: {e}")
            # Fallback to predefined questions
            fallback_response = get_fallback_question(interview_session)
            interview_session.conversation_history.append({
                "role": "assistant",
                "content": fallback_response
            })
            update_interview_state(interview_session)
            
            return jsonify({
                "success": True,
                "message": fallback_response,
                "state": interview_session.state,
                "question_count": interview_session.question_count,
                "should_speak": True
            })
    
    except Exception as e:
        print(f"Error processing response: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@interview_bp.route('/end', methods=['POST'])
def end_interview():
    """End interview and generate feedback"""
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        
        if session_id not in active_sessions:
            return jsonify({
                "success": False,
                "error": "Session not found"
            }), 404
        
        interview_session = active_sessions[session_id]
        
        # Generate feedback
        feedback = generate_interview_feedback(interview_session)
        
        # Save to database
        db = get_db()
        interview_data = {
            **interview_session.to_dict(),
            "ended_at": datetime.utcnow(),
            "feedback": feedback,
            "status": "completed"
        }
        
        result = db.interviews.insert_one(interview_data)
        interview_id = str(result.inserted_id)
        
        # Remove from active sessions
        del active_sessions[session_id]
        
        return jsonify({
            "success": True,
            "interview_id": interview_id,
            "feedback": feedback
        })
    
    except Exception as e:
        print(f"Error ending interview: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@interview_bp.route('/history/<phone_number>', methods=['GET'])
def get_interview_history(phone_number):
    """Get interview history for a user"""
    try:
        db = get_db()
        interviews = list(db.interviews.find(
            {"phone_number": phone_number}
        ).sort("started_at", -1).limit(10))
        
        # Convert ObjectId to string
        for interview in interviews:
            interview['_id'] = str(interview['_id'])
            if 'started_at' in interview:
                interview['started_at'] = interview['started_at'].isoformat()
            if 'ended_at' in interview:
                interview['ended_at'] = interview['ended_at'].isoformat()
        
        return jsonify({
            "success": True,
            "interviews": interviews
        })
    
    except Exception as e:
        print(f"Error fetching interview history: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@interview_bp.route('/feedback/<interview_id>', methods=['GET'])
def get_interview_feedback(interview_id):
    """Get feedback for a specific interview"""
    try:
        db = get_db()
        interview = db.interviews.find_one({"_id": ObjectId(interview_id)})
        
        if not interview:
            return jsonify({
                "success": False,
                "error": "Interview not found"
            }), 404
        
        interview['_id'] = str(interview['_id'])
        if 'started_at' in interview:
            interview['started_at'] = interview['started_at'].isoformat()
        if 'ended_at' in interview:
            interview['ended_at'] = interview['ended_at'].isoformat()
        
        return jsonify({
            "success": True,
            "interview": interview
        })
    
    except Exception as e:
        print(f"Error fetching interview feedback: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# Helper Functions

def get_system_prompt(session):
    """Generate system prompt based on interview state"""
    position = session.position
    state = session.state
    question_count = session.question_count
    
    if state == "greeting":
        return f"""You are Alex, a friendly AI interviewer. The candidate just responded to your greeting.
Acknowledge their response warmly in 1 sentence, then ask them to tell you about themselves and their interest in the {position} position.
Keep it conversational and brief (2-3 sentences max)."""
    
    elif state == "introduction":
        return f"""You are Alex, an AI interviewer for a {position} position.
The candidate just introduced themselves.
- Give brief positive feedback on their introduction (1 sentence)
- Ask a specific question about their experience or skills relevant to {position}
- Keep response under 3 sentences"""
    
    elif state == "interviewing":
        if question_count >= 7:
            return f"""You are Alex, an AI interviewer. The candidate answered your question.
- Give brief encouraging feedback
- Thank them and wrap up: "Thank you for your answers. Do you have any questions for me?"
Keep it under 2 sentences."""
        
        technical_areas = [
            "specific technical skills and projects",
            "problem-solving approaches and challenges faced",
            "teamwork and collaboration experiences",
            "handling difficult situations or conflicts",
            "career goals and professional development",
            "strengths and areas for improvement"
        ]
        focus_area = technical_areas[question_count % len(technical_areas)]
        
        return f"""You are Alex, an AI interviewer for a {position} position.
The candidate just answered your question.
- Provide brief constructive feedback (1 sentence)
- Ask a specific question about: {focus_area}
- Make it relevant for {position} role
- Keep total response under 3 sentences"""
    
    elif state == "closing":
        return """You are Alex, an AI interviewer. Give a warm closing response.
Thank them for their time and let them know the interview is complete.
Keep it brief and encouraging (2 sentences)."""
    
    return "You are Alex, a helpful AI interviewer. Respond naturally and professionally."

def update_interview_state(session):
    """Update interview state based on progress"""
    if session.state == "greeting":
        session.state = "introduction"
    elif session.state == "introduction":
        session.state = "interviewing"
        session.question_count = 1
    elif session.state == "interviewing":
        session.question_count += 1
        if session.question_count >= 8:
            session.state = "closing"

def get_fallback_question(session):
    """Get fallback question if AI service is unavailable"""
    fallback_questions = {
        "greeting": "That's great! Could you tell me about yourself and why you're interested in this position?",
        "introduction": "Thank you for that introduction. Can you tell me about your technical skills and experience?",
        "interviewing": [
            "Can you describe a challenging project you worked on?",
            "How do you approach problem-solving in your work?",
            "Tell me about a time you worked in a team.",
            "What are your career goals?",
            "How do you handle tight deadlines?",
            "What's your biggest strength?",
            "How do you stay updated with new technologies?",
            "Do you have any questions for me?"
        ],
        "closing": "Thank you for your time today. We'll be in touch soon!"
    }
    
    if session.state == "interviewing":
        questions = fallback_questions["interviewing"]
        idx = min(session.question_count - 1, len(questions) - 1)
        return questions[idx]
    
    return fallback_questions.get(session.state, "Can you tell me more about that?")

def _analyze_response_quality(answers):
    """Analyze the quality of candidate responses"""
    if not answers:
        return {"avg_length": 0, "detail_score": 0, "technical_keywords": 0, "casual_count": 0}
    
    technical_keywords = [
        'algorithm', 'database', 'api', 'framework', 'architecture', 'deploy', 'testing',
        'agile', 'scrum', 'git', 'docker', 'kubernetes', 'cloud', 'aws', 'azure',
        'react', 'node', 'python', 'java', 'sql', 'nosql', 'mongodb', 'rest',
        'microservice', 'ci/cd', 'pipeline', 'optimization', 'scalab', 'performance',
        'debug', 'refactor', 'design pattern', 'solid', 'oop', 'functional',
        'machine learning', 'data structure', 'complexity', 'cache', 'security',
        'authentication', 'authorization', 'encryption', 'ssl', 'http', 'tcp',
        'linux', 'server', 'load balancing', 'cdn', 'webpack', 'typescript',
        'component', 'state management', 'redux', 'context', 'hook', 'middleware'
    ]
    
    casual_phrases = [
        'i guess', 'maybe', 'i think so', 'not sure', 'i don\'t know',
        'whatever', 'stuff like that', 'you know', 'kind of', 'sort of',
        'um', 'uh', 'like yeah', 'basically'
    ]
    
    total_length = 0
    tech_count = 0
    casual_count = 0
    
    for answer in answers:
        answer_lower = answer.lower()
        total_length += len(answer.split())
        for kw in technical_keywords:
            if kw in answer_lower:
                tech_count += 1
        for phrase in casual_phrases:
            if phrase in answer_lower:
                casual_count += 1
    
    avg_length = total_length / len(answers) if answers else 0
    detail_score = min(100, (avg_length / 30) * 100)  # 30 words = 100%
    
    return {
        "avg_length": round(avg_length, 1),
        "detail_score": round(detail_score),
        "technical_keywords": tech_count,
        "casual_count": casual_count
    }


def _calculate_weighted_score(scores):
    """Calculate weighted overall score like the original project"""
    weights = {
        'technical_knowledge': 0.30,
        'communication': 0.25,
        'problem_solving': 0.20,
        'professionalism': 0.10,
        'enthusiasm': 0.10,
        'confidence': 0.05
    }
    
    total = 0
    weight_sum = 0
    for key, weight in weights.items():
        if key in scores:
            total += scores[key] * weight
            weight_sum += weight
    
    return round(total / weight_sum) if weight_sum > 0 else 50


def _get_performance_level(score):
    """Map score to performance level"""
    if score >= 90:
        return {"level": "Outstanding", "emoji": "🌟", "description": "Exceptional performance across all areas"}
    elif score >= 80:
        return {"level": "Excellent", "emoji": "⭐", "description": "Strong performance with minor areas for growth"}
    elif score >= 70:
        return {"level": "Good", "emoji": "👍", "description": "Solid performance with room for improvement"}
    elif score >= 60:
        return {"level": "Satisfactory", "emoji": "📊", "description": "Adequate performance, several areas need development"}
    elif score >= 50:
        return {"level": "Needs Improvement", "emoji": "📈", "description": "Below expectations, significant development needed"}
    else:
        return {"level": "Unsatisfactory", "emoji": "⚠️", "description": "Performance well below expectations"}


def _generate_scorecard(scores):
    """Generate scorecard with categories like the original project"""
    category_info = {
        'technical_knowledge': {'icon': '💻', 'description': 'Understanding of technical concepts and tools'},
        'communication': {'icon': '🗣️', 'description': 'Clarity, articulation, and expression'},
        'problem_solving': {'icon': '🧩', 'description': 'Analytical thinking and approach to challenges'},
        'professionalism': {'icon': '👔', 'description': 'Professional demeanor and workplace readiness'},
        'enthusiasm': {'icon': '🔥', 'description': 'Passion and interest in the role'},
        'confidence': {'icon': '💪', 'description': 'Self-assurance and composure'}
    }
    
    categories = []
    for key, info in category_info.items():
        score = scores.get(key, 50)
        if score >= 80:
            level = "Excellent"
            color = "green"
        elif score >= 60:
            level = "Good"
            color = "blue"
        elif score >= 40:
            level = "Fair"
            color = "yellow"
        else:
            level = "Needs Work"
            color = "red"
        
        categories.append({
            "name": key.replace('_', ' ').title(),
            "key": key,
            "score": score,
            "icon": info['icon'],
            "description": info['description'],
            "level": level,
            "color": color
        })
    
    return {"categories": categories}


def _generate_tips(scores):
    """Generate personalized tips based on scores"""
    tips = []
    
    if scores.get('technical_knowledge', 50) < 70:
        tips.extend([
            "Practice explaining technical concepts in simple terms",
            "Review common data structures and algorithms",
            "Build small projects to demonstrate hands-on experience"
        ])
    
    if scores.get('communication', 50) < 70:
        tips.extend([
            "Use the STAR method (Situation, Task, Action, Result) for behavioral questions",
            "Practice speaking clearly and at a measured pace",
            "Prepare 2-3 stories that showcase different skills"
        ])
    
    if scores.get('problem_solving', 50) < 70:
        tips.extend([
            "Walk through your thought process out loud when solving problems",
            "Practice breaking complex problems into smaller steps",
            "Review problem-solving frameworks and apply them consistently"
        ])
    
    if scores.get('professionalism', 50) < 70:
        tips.extend([
            "Research the company thoroughly before the interview",
            "Prepare thoughtful questions for the interviewer",
            "Dress appropriately and maintain good posture"
        ])
    
    if scores.get('enthusiasm', 50) < 70:
        tips.extend([
            "Show genuine interest by connecting your experience to the role",
            "Express excitement about specific aspects of the company or position",
            "Ask engaging follow-up questions"
        ])
    
    if scores.get('confidence', 50) < 70:
        tips.extend([
            "Practice common interview questions to build confidence",
            "Record yourself and review your body language",
            "Remember: it's okay to take a moment to think before answering"
        ])
    
    if not tips:
        tips = [
            "Continue refining your interview skills with regular practice",
            "Stay updated with industry trends and technologies",
            "Consider mock interviews with peers for additional feedback"
        ]
    
    return tips[:6]  # Max 6 tips


def generate_interview_feedback(session):
    """Generate comprehensive AI-powered feedback for completed interview"""
    
    duration_minutes = round((datetime.utcnow() - session.started_at).total_seconds() / 60, 1)
    questions_answered = len(session.answers)
    quality = _analyze_response_quality(session.answers)
    
    # Check for early termination
    early_termination = None
    if questions_answered < 3:
        early_termination = {
            "detected": True,
            "severity": "high",
            "message": "Interview ended very early with fewer than 3 questions answered.",
            "penalty": 30
        }
    elif questions_answered < 5 and duration_minutes < 3:
        early_termination = {
            "detected": True,
            "severity": "medium", 
            "message": "Interview was shorter than typical. More questions could demonstrate skills better.",
            "penalty": 15
        }
    
    # Try AI-powered analysis using Perplexity
    ai_analysis = None
    try:
        api_key = get_perplexity_key()
        if api_key and session.conversation_history:
            # Build conversation summary
            conv_text = ""
            for msg in session.conversation_history:
                role = "Interviewer" if msg['role'] == 'assistant' else "Candidate"
                conv_text += f"{role}: {msg['content']}\n\n"
            
            analysis_prompt = f"""You are an expert interview evaluator. Analyze this interview transcript for a {session.position} position.

INTERVIEW TRANSCRIPT:
{conv_text}

CANDIDATE INFO:
- Name: {session.user_name}
- Position: {session.position}
- Questions answered: {questions_answered}
- Average response length: {quality['avg_length']} words
- Technical keywords used: {quality['technical_keywords']}

Provide a STRICT and HONEST evaluation. Do NOT inflate scores. Score based on ACTUAL content quality.

SCORING RUBRIC (0-100 for each):
- technical_knowledge: How well did they demonstrate technical understanding? (0-30: vague/wrong, 31-60: basic understanding, 61-80: good knowledge, 81-100: expert level with specific examples)
- communication: How clearly did they express themselves? (0-30: unclear/rambling, 31-60: understandable, 61-80: clear and structured, 81-100: excellent articulation with STAR method)
- problem_solving: Did they show analytical thinking? (0-30: no analysis, 31-60: basic approach, 61-80: structured thinking, 81-100: systematic with trade-off analysis)
- professionalism: Professional demeanor and responses? (0-30: casual/unprepared, 31-60: adequate, 61-80: professional, 81-100: exemplary)
- enthusiasm: Interest and passion for the role? (0-30: disinterested, 31-60: neutral, 61-80: interested, 81-100: genuinely passionate)
- confidence: Self-assurance in responses? (0-30: very unsure, 31-60: somewhat confident, 61-80: confident, 81-100: poised and assured)

You MUST respond in EXACTLY this JSON format (no other text):
{{
  "scores": {{
    "technical_knowledge": <number>,
    "communication": <number>,
    "problem_solving": <number>,
    "professionalism": <number>,
    "enthusiasm": <number>,
    "confidence": <number>
  }},
  "strengths": ["<strength1>", "<strength2>", "<strength3>"],
  "improvements": ["<improvement1>", "<improvement2>", "<improvement3>"],
  "knowledge_assessment": {{
    "demonstrated_skills": ["<skill1>", "<skill2>"],
    "skill_gaps": ["<gap1>", "<gap2>"],
    "depth_of_knowledge": "<shallow/moderate/deep>"
  }},
  "communication_feedback": {{
    "clarity": "<brief assessment>",
    "structure": "<brief assessment>",
    "vocabulary": "<brief assessment>"
  }},
  "interviewer_guidance": {{
    "hiring_recommendation": "<Strong Hire/Hire/Maybe/No Hire>",
    "reasoning": "<1-2 sentence explanation>",
    "follow_up_areas": ["<area1>", "<area2>"]
  }},
  "detailed_feedback": "<2-3 sentence overall assessment>"
}}"""

            print(f"[Interview Feedback] Calling Perplexity API for analysis...")
            
            response = requests.post(
                PERPLEXITY_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "sonar",
                    "messages": [
                        {"role": "system", "content": "You are an expert interview evaluator. Respond ONLY with valid JSON, no markdown, no code blocks, no explanation."},
                        {"role": "user", "content": analysis_prompt}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 1000
                },
                timeout=45
            )
            
            if response.status_code == 200:
                result = response.json()
                ai_text = result['choices'][0]['message']['content'].strip()
                
                # Clean up response - remove markdown code blocks if present
                if ai_text.startswith('```'):
                    ai_text = ai_text.split('\n', 1)[1] if '\n' in ai_text else ai_text[3:]
                if ai_text.endswith('```'):
                    ai_text = ai_text[:-3]
                ai_text = ai_text.strip()
                
                # Try to extract JSON from the response
                import re
                json_match = re.search(r'\{[\s\S]*\}', ai_text)
                if json_match:
                    ai_analysis = json.loads(json_match.group())
                    print(f"[Interview Feedback] AI analysis successful: scores={ai_analysis.get('scores', {})}")
                else:
                    print(f"[Interview Feedback] Could not find JSON in AI response: {ai_text[:200]}")
            else:
                print(f"[Interview Feedback] Perplexity API error: {response.status_code}")
                
    except Exception as e:
        print(f"[Interview Feedback] AI analysis failed: {e}")
        import traceback
        traceback.print_exc()
    
    # Build feedback from AI analysis or fallback
    if ai_analysis and 'scores' in ai_analysis:
        scores = ai_analysis['scores']
        # Validate and cap scores
        for key in scores:
            scores[key] = max(0, min(100, int(scores[key])))
        
        # Apply early termination penalty
        if early_termination:
            penalty = early_termination['penalty']
            for key in scores:
                scores[key] = max(10, scores[key] - penalty)
        
        # Adjust based on response quality
        if quality['avg_length'] < 10:
            for key in scores:
                scores[key] = min(scores[key], 45)
        elif quality['avg_length'] < 20:
            for key in scores:
                scores[key] = min(scores[key], 65)
        
        if quality['casual_count'] > 3:
            scores['professionalism'] = min(scores['professionalism'], 55)
        
        overall_score = _calculate_weighted_score(scores)
        performance_level = _get_performance_level(overall_score)
        
        strengths = ai_analysis.get('strengths', ["Participated in the interview"])
        improvements = ai_analysis.get('improvements', ["Provide more detailed responses"])
        knowledge_assessment = ai_analysis.get('knowledge_assessment', {
            "demonstrated_skills": [], "skill_gaps": [], "depth_of_knowledge": "shallow"
        })
        communication_feedback = ai_analysis.get('communication_feedback', {
            "clarity": "Needs assessment", "structure": "Needs assessment", "vocabulary": "Needs assessment"
        })
        interviewer_guidance = ai_analysis.get('interviewer_guidance', {
            "hiring_recommendation": "Maybe",
            "reasoning": "Needs further evaluation",
            "follow_up_areas": []
        })
        detailed_feedback = ai_analysis.get('detailed_feedback', '')
        
    else:
        # Fallback: generate basic scores from response quality metrics
        base_score = 50
        if quality['avg_length'] > 25:
            base_score += 15
        elif quality['avg_length'] > 15:
            base_score += 8
        elif quality['avg_length'] < 8:
            base_score -= 15
        
        tech_bonus = min(20, quality['technical_keywords'] * 3)
        casual_penalty = min(15, quality['casual_count'] * 5)
        
        scores = {
            'technical_knowledge': max(15, min(85, base_score + tech_bonus - 5)),
            'communication': max(15, min(85, base_score + 5 - casual_penalty)),
            'problem_solving': max(15, min(85, base_score - 5 + tech_bonus // 2)),
            'professionalism': max(15, min(85, base_score - casual_penalty)),
            'enthusiasm': max(15, min(85, base_score + 5)),
            'confidence': max(15, min(85, base_score))
        }
        
        if early_termination:
            penalty = early_termination['penalty']
            for key in scores:
                scores[key] = max(10, scores[key] - penalty)
        
        overall_score = _calculate_weighted_score(scores)
        performance_level = _get_performance_level(overall_score)
        
        strengths = []
        improvements = []
        
        if quality['avg_length'] > 20:
            strengths.append("Provided detailed responses to interview questions")
        if quality['technical_keywords'] > 3:
            strengths.append("Demonstrated awareness of relevant technical concepts")
        if quality['casual_count'] < 2:
            strengths.append("Maintained a professional communication style")
        if questions_answered >= 5:
            strengths.append("Engaged thoroughly throughout the interview")
        if not strengths:
            strengths.append("Participated in the interview process")
        
        if quality['avg_length'] < 15:
            improvements.append("Provide more detailed and thorough answers")
        if quality['technical_keywords'] < 3:
            improvements.append("Include more specific technical details and examples")
        if quality['casual_count'] > 2:
            improvements.append("Use more professional language and reduce filler words")
        if questions_answered < 5:
            improvements.append("Try to engage more fully and answer more questions")
        if not improvements:
            improvements.append("Continue refining communication and technical depth")
        
        knowledge_assessment = {
            "demonstrated_skills": ["Interview participation"],
            "skill_gaps": ["Unable to fully assess without AI analysis"],
            "depth_of_knowledge": "moderate" if quality['technical_keywords'] > 3 else "shallow"
        }
        communication_feedback = {
            "clarity": "Good" if quality['avg_length'] > 15 else "Needs improvement - responses were brief",
            "structure": "Adequate" if quality['avg_length'] > 20 else "Could be more structured",
            "vocabulary": "Professional" if quality['casual_count'] < 2 else "Could be more formal"
        }
        interviewer_guidance = {
            "hiring_recommendation": "Hire" if overall_score >= 75 else "Maybe" if overall_score >= 55 else "No Hire",
            "reasoning": f"Candidate scored {overall_score}/100 overall. {'Strong candidate with good potential.' if overall_score >= 70 else 'Needs further evaluation in key areas.'}",
            "follow_up_areas": ["Technical depth assessment", "Problem-solving with specific scenarios"]
        }
        detailed_feedback = f"The candidate completed {questions_answered} questions with an average response length of {quality['avg_length']} words."
    
    scorecard = _generate_scorecard(scores)
    tips = _generate_tips(scores)
    
    return {
        "overall_score": overall_score,
        "duration_minutes": duration_minutes,
        "questions_answered": questions_answered,
        "strengths": strengths,
        "areas_for_improvement": improvements,
        "recommendation": interviewer_guidance.get('hiring_recommendation', 'Maybe'),
        "detailed_analysis": detailed_feedback,
        "analysis": {
            "scores": scores,
            "overall_score": overall_score,
            "performance_level": performance_level,
            "strengths": strengths,
            "improvements": improvements,
            "knowledge_assessment": knowledge_assessment,
            "communication_feedback": communication_feedback,
            "interviewer_guidance": interviewer_guidance,
            "detailed_feedback": detailed_feedback,
            "early_termination": early_termination,
            "response_quality": quality
        },
        "scorecard": scorecard,
        "tips": tips
    }
