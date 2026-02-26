"""
Interview Module Routes - Flask Integration with Groq AI
Provides AI interview functionality with smart features:
- Progressive difficulty scaling
- No duplicate questions
- Conditional compliments (only for good answers)
- Position-specific questions
"""
from flask import Blueprint, request, jsonify, session
from datetime import datetime
import os
import json
import re
import random
import requests
from utils.db import get_db
from bson import ObjectId

interview_bp = Blueprint('interview', __name__, url_prefix='/api/interview')

# Groq API configuration (ULTRA FAST ~200-500ms)
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

def get_groq_key():
    """Get Groq API key from environment"""
    key = os.getenv('GROQ_API_KEY')
    if not key:
        print("❌ GROQ_API_KEY not found! Get free key at console.groq.com")
    return key

# Validate key at startup
_startup_key = os.getenv('GROQ_API_KEY')
if _startup_key:
    print(f"✅ Groq API key loaded: {_startup_key[:8]}...{_startup_key[-4:]}")
else:
    print("❌ WARNING: GROQ_API_KEY not set! Get free key at console.groq.com")

# In-memory session storage
active_sessions = {}

class InterviewSession:
    """Enhanced interview session with smart features from Groq engine"""
    def __init__(self, session_id, user_name, phone_number, position="Software Developer"):
        self.session_id = session_id
        self.user_name = user_name
        self.phone_number = phone_number
        self.position = position
        self.state = "greeting"
        self.question_count = 0
        self.conversation_history = []
        self.started_at = datetime.utcnow()
        self.questions_asked = []  # Track to avoid duplicates
        self.asked_topics = []  # Track question topics
        self.answers = []
        # Smart features
        self.difficulty_level = 1  # 1=easy, 2=medium, 3=hard
        self.correct_answers = 0
        self.total_questions = 8
    
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
            "answers": self.answers,
            "difficulty_level": self.difficulty_level,
            "correct_answers": self.correct_answers
        }
    
    def get_question_pool(self):
        """Get questions organized by difficulty level"""
        return {
            1: [  # Easy/Basic questions
                "your technical skills and background",
                "daily tools and technologies you use",
                "your educational background",
                "why you're interested in this role",
                "your previous work experience",
                "your strongest technical skill",
            ],
            2: [  # Medium/Intermediate questions
                "a challenging problem you solved recently",
                "how you handle tight deadlines and pressure",
                "your approach to debugging complex issues",
                "how you stay updated with new technologies",
                "a project you're most proud of",
                "how you handle disagreements with team members",
            ],
            3: [  # Hard/Advanced questions
                "your experience with system design and architecture",
                "how you optimize performance in applications",
                "your approach to managing technical debt",
                "how you mentor or help junior developers",
                "a difficult technical decision you had to make",
                "how you handle production incidents",
            ],
            4: [  # Scenario questions (end of interview)
                f"SCENARIO: You discover a critical bug in production on Friday evening. Walk me through your approach.",
                f"SCENARIO: A teammate wrote code that works but is poorly structured. How would you handle this?",
                f"SCENARIO: Your team disagrees on the technical approach for a project. How do you resolve it?",
                f"SCENARIO: You're given an impossible deadline by management. What do you do?",
            ]
        }
    
    def get_next_question_topic(self):
        """Get next question topic avoiding duplicates"""
        pool = self.get_question_pool()
        available = pool.get(self.difficulty_level, pool[2])
        
        # Filter out already asked topics
        unused = [q for q in available if q not in self.asked_topics]
        
        # If all used, try other difficulty levels
        if not unused:
            for level in [1, 2, 3]:
                if level != self.difficulty_level:
                    unused = [q for q in pool.get(level, []) if q not in self.asked_topics]
                    if unused:
                        break
        
        if not unused:
            unused = available
        
        topic = random.choice(unused) if unused else f"your experience with {self.position}"
        self.asked_topics.append(topic)
        return topic
    
    def get_scenario_topic(self):
        """Get a scenario question"""
        pool = self.get_question_pool()
        scenarios = pool.get(4, [])
        unused = [s for s in scenarios if s not in self.asked_topics]
        if not unused:
            unused = scenarios
        scenario = random.choice(unused) if unused else scenarios[0]
        self.asked_topics.append(scenario)
        return scenario
    
    def analyze_answer(self, message):
        """Comprehensive answer analysis with quality scoring"""
        import re
        
        msg_lower = message.lower().strip()
        word_count = len(message.split())
        
        # === Casual/Social Phrases (not interview content) ===
        casual_phrases = [
            "doing great", "doing good", "i'm good", "i'm fine", "doing fine",
            "good thanks", "fine thanks", "how are you", "what about you",
            "hello", "hi", "hey", "good morning", "good afternoon", "i'm doing well"
        ]
        
        # === Clarification Requests (user didn't understand the question) ===
        clarification_phrases = [
            "what do you mean", "i don't understand", "can you explain",
            "can you rephrase", "repeat that", "say that again", "repeat please",
            "sorry what", "sorry?", "what?", "pardon", "come again",
            "didn't catch that", "clarify", "what exactly"
        ]
        is_clarification_request = any(phrase in msg_lower for phrase in clarification_phrases)
        
        # === Off-Topic/Irrelevant Phrases ===
        off_topic_phrases = [
            "weather", "lunch", "dinner", "movie", "music", "game", "sports",
            "girlfriend", "boyfriend", "party", "vacation", "tell me a joke",
            "pizza", "burger", "i love you", "lol", "haha", "lmao"
        ]
        
        # === Abusive Language Detection ===
        abusive_phrases = [
            "fuck", "shit", "damn", "ass", "bitch", "idiot", "stupid", "dumb",
            "madarchod", "bhenchod", "chutiya", "gandu", "randi", "bc", "mc",
            "bsdk", "harami", "kamina", "bakchod"
        ]
        is_abusive = any(phrase in msg_lower for phrase in abusive_phrases)
        
        # === Non-English Detection (Hindi/other languages) ===
        msg_words = set(re.findall(r'\b[a-z]+\b', msg_lower))
        has_devanagari = any(ord(c) >= 0x0900 and ord(c) <= 0x097F for c in message)
        
        hindi_romanized = {
            'kya', 'kaise', 'hain', 'tum', 'mein', 'kuch', 'bolo', 'baat', 'nahi',
            'kyun', 'aap', 'karo', 'hum', 'yeh', 'woh', 'kaun', 'accha', 'theek',
            'meri', 'mera', 'bahut', 'gaya', 'gayi', 'abhi', 'kaha', 'lekin',
            'matlab', 'samajh', 'dekho', 'suno', 'batao', 'chalo', 'ruko',
            'main', 'hoon', 'tumhe', 'mujhe', 'pata', 'batata', 'phir', 'bohot',
            'hogaya', 'milega', 'sahi', 'galat', 'yaar', 'arey', 'jaata', 'aata',
            'kaisa', 'kahan', 'apna', 'apni', 'uska', 'uski', 'sakta', 'chahiye',
            'dena', 'lena', 'aaya', 'ghar', 'kaam', 'wala', 'koi', 'aisa', 'tujhe',
            'tumhara', 'humara', 'khana', 'jaana', 'aana', 'samjha', 'milna',
            'hona', 'hota', 'toh', 'kyunki', 'jab', 'bilkul', 'zaroor', 'shayad'
        }
        hindi_word_matches = msg_words.intersection(hindi_romanized)
        is_non_english = has_devanagari or len(hindi_word_matches) >= 2
        
        # === Analysis ===
        is_casual = any(phrase in msg_lower for phrase in casual_phrases) and word_count < 12
        is_off_topic = any(phrase in msg_lower for phrase in off_topic_phrases) or is_non_english
        
        # === Calculate Quality Score (0-3) ===
        quality_score = 1
        if is_off_topic or is_casual or is_abusive or is_non_english:
            quality_score = 0
        elif word_count < 8:
            quality_score = 1
        elif word_count < 20:
            quality_score = 2
        else:
            quality_score = 3
        
        has_substance = quality_score >= 2
        
        return {
            "is_casual": is_casual,
            "is_off_topic": is_off_topic,
            "is_abusive": is_abusive,
            "is_non_english": is_non_english,
            "is_clarification_request": is_clarification_request,
            "has_substance": has_substance,
            "quality_score": quality_score,
            "word_count": word_count
        }


def get_smart_system_prompt(session):
    """Generate intelligent system prompt like Groq engine"""
    difficulty_desc = {1: "basic/entry-level", 2: "intermediate", 3: "advanced/senior-level"}.get(session.difficulty_level, "intermediate")
    already_asked = ", ".join(session.asked_topics[-5:]) if session.asked_topics else "none yet"
    
    return f"""You are Alex, a professional AI interviewer for the {session.position} position.

CURRENT STATE:
- Difficulty Level: {session.difficulty_level}/3 ({difficulty_desc})
- Question #{session.question_count + 1} of {session.total_questions}
- Already asked about: {already_asked}

STRICT RULES:
1. ANALYZE the candidate's response quality:
   - If answer is RELEVANT and shows understanding → Brief appreciation (1-2 words like "Good!" or "Nice!") + next question
   - If answer is IRRELEVANT, vague, or off-topic → Skip appreciation, just ask next question directly
   - If answer is casual/social (like "I'm good", "doing great") → Move to next question without praise

2. NEVER repeat a question you already asked (check the "Already asked about" list)
3. Ask {difficulty_desc} questions appropriate for the current level
4. Keep total response under 35 words
5. Ask questions specifically relevant to {session.position}
6. Never cut off mid-sentence
7. ALWAYS respond in English only. Never use Hindi or any other language.

RESPONSE FORMAT:
- Good technical answer: "Good! [Next question about new topic]"
- Poor/irrelevant answer: "[Next question directly without any praise]"
- Casual social response: "[Next question directly]"
"""


def get_instruction_for_state(session, user_message, answer_analysis):
    """Get specific instruction based on interview state"""
    has_substance = answer_analysis["has_substance"]
    is_casual = answer_analysis["is_casual"]
    
    if session.state == "greeting":
        if is_casual:
            return f"Skip appreciation. Ask them to introduce themselves and their interest in the {session.position} role. Under 25 words."
        return f"Briefly acknowledge, then ask them to tell you about themselves and why they're interested in {session.position}. Under 25 words."
    
    elif session.state == "introduction":
        question_topic = session.get_next_question_topic()
        if has_substance:
            return f"Say 'Thanks!' briefly, then ask about {question_topic}. Under 30 words."
        else:
            return f"Ask about {question_topic} directly without praise. Under 25 words."
    
    elif session.state == "interviewing":
        # Check if time for scenario questions (last 2 questions)
        if session.question_count >= session.total_questions - 2:
            scenario_topic = session.get_scenario_topic()
            if has_substance:
                return f"Say 'Good!' then present this scenario: {scenario_topic}. Under 45 words total."
            else:
                return f"Present this scenario directly: {scenario_topic}. Under 40 words."
        
        # Check if time to close
        if session.question_count >= session.total_questions:
            return "Thank them warmly and ask if they have any questions for you. Under 20 words."
        
        # Get next question based on difficulty
        question_topic = session.get_next_question_topic()
        if has_substance:
            return f"Say 'Good!' or 'Nice!' (1-2 words), then ask about {question_topic}. Under 30 words total."
        else:
            return f"Ask about {question_topic} directly without any appreciation. Under 25 words."
    
    elif session.state == "closing":
        return "Give a warm closing, thank them for their time, wish them luck. Under 20 words."
    
    return "Respond naturally and professionally as Alex the interviewer."


def update_session_state(session, answer_analysis):
    """Update interview state and difficulty based on answer quality"""
    has_substance = answer_analysis["has_substance"]
    
    if session.state == "greeting":
        session.state = "introduction"
    
    elif session.state == "introduction":
        session.state = "interviewing"
        session.question_count = 1
    
    elif session.state == "interviewing":
        session.question_count += 1
        
        # Increase difficulty if answer was good
        if has_substance:
            session.correct_answers += 1
            # Increase difficulty every 2 good answers
            if session.correct_answers % 2 == 0 and session.difficulty_level < 3:
                session.difficulty_level += 1
                print(f"⬆️ Difficulty increased to level {session.difficulty_level}")
        
        # Check if time to close
        if session.question_count >= session.total_questions:
            session.state = "closing"

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
    """Process user's response using Groq AI with smart features"""
    import time
    start_time = time.time()
    
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        user_message = data.get('message', '')
        
        # Get session
        if session_id not in active_sessions:
            return jsonify({
                "success": False,
                "error": "Session not found",
                "session_expired": True
            }), 404
        
        interview_session = active_sessions[session_id]
        
        # Analyze user's answer quality
        answer_analysis = interview_session.analyze_answer(user_message)

        # === DIRECT HANDLING: Abusive language ===
        if answer_analysis.get('is_abusive', False):
            last_q = interview_session.questions_asked[-1] if interview_session.questions_asked else "Tell me about yourself."
            warning_response = "Please maintain professional language. " + last_q
            interview_session.conversation_history.append({"role": "user", "content": user_message})
            interview_session.conversation_history.append({"role": "assistant", "content": warning_response})
            return jsonify({
                "success": True,
                "message": warning_response,
                "state": interview_session.state,
                "question_count": interview_session.question_count,
                "difficulty_level": interview_session.difficulty_level,
                "should_speak": True
            })

        # === DIRECT HANDLING: Non-English response ===
        if answer_analysis.get('is_non_english', False):
            last_q = interview_session.questions_asked[-1] if interview_session.questions_asked else "Tell me about yourself."
            english_response = "Please respond in English. " + last_q
            interview_session.conversation_history.append({"role": "user", "content": user_message})
            interview_session.conversation_history.append({"role": "assistant", "content": english_response})
            return jsonify({
                "success": True,
                "message": english_response,
                "state": interview_session.state,
                "question_count": interview_session.question_count,
                "difficulty_level": interview_session.difficulty_level,
                "should_speak": True
            })

        # === DIRECT HANDLING: Clarification request ===
        if answer_analysis.get('is_clarification_request', False):
            last_q = interview_session.questions_asked[-1] if interview_session.questions_asked else "What are your key skills?"
            clarify_response = "Sure, let me rephrase. " + last_q
            interview_session.conversation_history.append({"role": "user", "content": user_message})
            interview_session.conversation_history.append({"role": "assistant", "content": clarify_response})
            return jsonify({
                "success": True,
                "message": clarify_response,
                "state": interview_session.state,
                "question_count": interview_session.question_count,
                "difficulty_level": interview_session.difficulty_level,
                "should_speak": True
            })
        
        # Add user message to history
        interview_session.conversation_history.append({
            "role": "user",
            "content": user_message
        })
        interview_session.answers.append(user_message)
        
        # Generate smart system prompt and instruction
        system_prompt = get_smart_system_prompt(interview_session)
        instruction = get_instruction_for_state(interview_session, user_message, answer_analysis)
        
        # Combine system prompt with instruction
        full_system = f"{system_prompt}\n\nCURRENT INSTRUCTION: {instruction}"
        
        try:
            api_key = get_groq_key()
            if not api_key:
                print("❌ No Groq API key, using fallback")
                raise Exception("GROQ_API_KEY not configured")
            
            print(f"🚀 Groq API call (Difficulty: {interview_session.difficulty_level}, Q#{interview_session.question_count})")
            
            # Call Groq API (ULTRA FAST ~200-500ms)
            response = requests.post(
                GROQ_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "llama-3.1-8b-instant",
                    "messages": [
                        {"role": "system", "content": full_system},
                        *interview_session.conversation_history[-6:]
                    ],
                    "temperature": 0.6,
                    "max_tokens": 200
                },
                timeout=15
            )
            
            elapsed = int((time.time() - start_time) * 1000)
            
            if response.status_code == 200:
                result = response.json()
                ai_message = result['choices'][0]['message']['content']
                
                # Clean any weird formatting
                ai_message = ai_message.strip()
                
                # Update conversation history
                interview_session.conversation_history.append({
                    "role": "assistant",
                    "content": ai_message
                })
                interview_session.questions_asked.append(ai_message)
                
                # Update state and difficulty
                update_session_state(interview_session, answer_analysis)
                
                print(f"⚡ Groq response in {elapsed}ms")
                
                return jsonify({
                    "success": True,
                    "message": ai_message,
                    "state": interview_session.state,
                    "question_count": interview_session.question_count,
                    "difficulty_level": interview_session.difficulty_level,
                    "should_speak": True
                })
            else:
                print(f"Groq API error: {response.status_code} - {response.text[:200]}")
                raise Exception(f"Groq API error {response.status_code}")
        
        except Exception as e:
            print(f"Error calling Groq API: {e}")
            # Fallback to predefined questions
            fallback_response = get_fallback_question(interview_session)
            interview_session.conversation_history.append({
                "role": "assistant",
                "content": fallback_response
            })
            update_session_state(interview_session, answer_analysis)
            
            return jsonify({
                "success": True,
                "message": fallback_response,
                "state": interview_session.state,
                "question_count": interview_session.question_count,
                "difficulty_level": interview_session.difficulty_level,
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
        confidence_analysis = data.get('confidence_analysis')  # Client-side MediaPipe results
        
        if session_id not in active_sessions:
            return jsonify({
                "success": False,
                "error": "Session not found"
            }), 404
        
        interview_session = active_sessions[session_id]
        
        # Generate feedback
        feedback = generate_interview_feedback(interview_session)
        
        # Add confidence analysis to feedback if available
        if confidence_analysis and confidence_analysis.get('framesAnalyzed', 0) > 0:
            feedback['confidence_analysis'] = {
                'eye_contact_score': confidence_analysis.get('avgEyeContact', 0),
                'head_stability_score': confidence_analysis.get('avgHeadStability', 0),
                'overall_confidence_score': confidence_analysis.get('avgOverall', 0),
                'confidence_level': confidence_analysis.get('level', 'Unknown'),
                'frames_analyzed': confidence_analysis.get('framesAnalyzed', 0),
                'analysis_duration_seconds': confidence_analysis.get('duration', 0)
            }
            print(f"📹 Confidence analysis saved: Eye={confidence_analysis.get('avgEyeContact')}%, Stability={confidence_analysis.get('avgHeadStability')}%, Overall={confidence_analysis.get('avgOverall')}%")
        
        # Save to database
        db = get_db()
        interview_data = {
            **interview_session.to_dict(),
            "ended_at": datetime.utcnow(),
            "feedback": feedback,
            "status": "completed"
        }
        
        # Also store confidence analysis at top level for easy querying
        if confidence_analysis and confidence_analysis.get('framesAnalyzed', 0) > 0:
            interview_data['confidence_analysis'] = feedback['confidence_analysis']
        
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


# ============= GROQ WHISPER SPEECH-TO-TEXT =============
# Ultra-fast transcription using Groq's Whisper API (~200-500ms)

GROQ_AUDIO_API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

@interview_bp.route('/transcribe', methods=['POST'])
def transcribe_audio():
    """
    Transcribe audio using Groq's Whisper API (ULTRA FAST ~200-500ms)
    Accepts audio file via multipart/form-data
    
    Returns:
        JSON with transcribed text and confidence
    """
    import time
    start_time = time.time()
    
    try:
        # Check if audio file was sent
        if 'audio' not in request.files:
            return jsonify({
                "success": False,
                "error": "No audio file provided"
            }), 400
        
        audio_file = request.files['audio']
        
        if audio_file.filename == '':
            return jsonify({
                "success": False,
                "error": "Empty filename"
            }), 400
        
        # Get Groq API key
        api_key = get_groq_key()
        if not api_key:
            return jsonify({
                "success": False,
                "error": "Groq API key not configured"
            }), 500
        
        # Read audio file content
        audio_content = audio_file.read()
        
        # Determine file extension
        filename = audio_file.filename or 'audio.webm'
        if not filename.endswith(('.webm', '.mp3', '.wav', '.m4a', '.ogg', '.flac')):
            filename = 'audio.webm'  # Default for browser recordings
        
        # Call Groq Whisper API
        import io
        files = {
            'file': (filename, io.BytesIO(audio_content), audio_file.content_type or 'audio/webm')
        }
        data = {
            'model': 'whisper-large-v3-turbo',  # Fastest model
            'language': 'en',
            'response_format': 'json'
        }
        headers = {
            'Authorization': f'Bearer {api_key}'
        }
        
        response = requests.post(
            GROQ_AUDIO_API_URL,
            headers=headers,
            files=files,
            data=data,
            timeout=30
        )
        
        elapsed_ms = int((time.time() - start_time) * 1000)
        
        if response.status_code == 200:
            result = response.json()
            transcript = result.get('text', '').strip()
            
            print(f"🎤 Groq Whisper transcribed in {elapsed_ms}ms: '{transcript[:50]}...'")
            
            return jsonify({
                "success": True,
                "text": transcript,
                "confidence": 0.95,  # Groq doesn't return confidence, assume high
                "duration_ms": elapsed_ms,
                "model": "whisper-large-v3-turbo"
            })
        else:
            error_msg = response.text[:200]
            print(f"❌ Groq Whisper error ({response.status_code}): {error_msg}")
            return jsonify({
                "success": False,
                "error": f"Transcription failed: {error_msg}"
            }), response.status_code
    
    except requests.Timeout:
        return jsonify({
            "success": False,
            "error": "Transcription timed out"
        }), 504
    
    except Exception as e:
        print(f"❌ Transcription error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500




# ============= EDGE TTS: Natural Voice Synthesis =============
# Uses Microsoft Edge's TTS service for high-quality, natural-sounding voices
# No API key required, ~50KB package, HTTP-only

@interview_bp.route('/tts', methods=['POST'])
def text_to_speech():
    """
    Convert text to speech using Edge TTS (FAST, Natural Voice)
    
    Input JSON: { "text": "Hello there" }
    Returns: Audio file (MP3)
    """
    import asyncio
    import tempfile
    import os as os_module
    
    try:
        data = request.get_json()
        text = data.get('text', '').strip()
        voice = data.get('voice', 'en-US-GuyNeural')  # Male interviewer voice
        
        if not text:
            return jsonify({
                "success": False,
                "error": "No text provided"
            }), 400
        
        # Limit text length for safety
        if len(text) > 1000:
            text = text[:1000]
        
        async def generate_audio():
            import edge_tts
            
            # Create temp file for audio
            fd, temp_path = tempfile.mkstemp(suffix='.mp3')
            os_module.close(fd)
            
            try:
                communicate = edge_tts.Communicate(text, voice)
                await communicate.save(temp_path)
                
                # Read the audio file
                with open(temp_path, 'rb') as f:
                    audio_data = f.read()
                
                return audio_data
            finally:
                # Clean up temp file
                if os_module.path.exists(temp_path):
                    os_module.unlink(temp_path)
        
        # Run async function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            audio_data = loop.run_until_complete(generate_audio())
        finally:
            loop.close()
        
        from flask import Response
        return Response(
            audio_data,
            mimetype='audio/mpeg',
            headers={
                'Content-Disposition': 'inline; filename="speech.mp3"',
                'Content-Length': str(len(audio_data))
            }
        )
        
    except Exception as e:
        print(f"TTS error: {e}")
        import traceback
        traceback.print_exc()
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

⚠️ CRITICAL: ALL scores MUST be on a 0-100 scale (NOT 1-10). 
Example: An average/mediocre response = 50, a good response = 70, excellent = 85+.
DO NOT use single digit scores like 5 or 7. Use proper 0-100 values.

SCORING RUBRIC (0-100 for each category):
- technical_knowledge: Technical understanding demonstrated (15-30: vague/incorrect, 35-55: basic understanding, 60-75: good knowledge with examples, 80-95: expert level with specific technical depth)
- communication: Expression clarity (15-30: unclear/rambling, 35-55: understandable but basic, 60-75: clear and well-structured, 80-95: excellent articulation using STAR method)
- problem_solving: Analytical thinking shown (15-30: no analysis visible, 35-55: basic approach mentioned, 60-75: structured logical thinking, 80-95: systematic with trade-off analysis)
- professionalism: Professional demeanor (15-30: too casual/unprepared, 35-55: adequate professionalism, 60-75: professional responses, 80-95: exemplary workplace readiness)
- enthusiasm: Interest in the role (15-30: seems disinterested, 35-55: neutral tone, 60-75: clearly interested, 80-95: genuinely passionate and eager)
- confidence: Self-assurance level (15-30: very unsure/hesitant, 35-55: somewhat confident, 60-75: confident delivery, 80-95: poised and assured throughout)

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
        
        # FIX: Auto-detect if AI returned 1-10 scale instead of 0-100
        # If all scores are <= 10, multiply by 10 to convert to 0-100 scale
        score_values = [int(v) for v in scores.values() if isinstance(v, (int, float))]
        if score_values and all(v <= 10 for v in score_values):
            print(f"[Interview Feedback] Detected 1-10 scale, converting to 0-100: {scores}")
            for key in scores:
                scores[key] = int(scores[key]) * 10
            print(f"[Interview Feedback] Converted scores: {scores}")
        
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

