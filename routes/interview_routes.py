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
    # Try different possible variable names
    key = os.getenv('GROQ_API_KEY') or os.getenv('groq_api_key') or os.getenv('GROQ_KEY')
    if not key:
        # Debug: print available env vars that contain 'GROQ' or 'API'
        groq_vars = [k for k in os.environ.keys() if 'GROQ' in k.upper() or 'groq' in k.lower()]
        print(f"❌ GROQ_API_KEY not found! Available GROQ-related vars: {groq_vars}")
        print("❌ Get free key at console.groq.com and set GROQ_API_KEY in Railway")
    return key

# Validate key at startup
_startup_key = get_groq_key()
if _startup_key:
    print(f"✅ Groq API key loaded: {_startup_key[:8]}...{_startup_key[-4:]}")
else:
    print("❌ WARNING: GROQ_API_KEY not set in Railway environment variables!")

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
        self.questions_asked = []  # Track actual question text to avoid duplicates
        self.asked_topics = []  # Track question topics
        self.answers = []
        self.substantive_answers = []  # Only answers with real content (for scoring)
        self.last_question_topic = None  # Track what was just asked for answer matching
        self.quality_scores = []  # Track quality score (0-3) for each answer
        # Track inappropriate responses
        self.inappropriate_count = 0  # Abusive/non-English/off-topic responses
        self.abusive_count = 0  # Abusive language specifically
        self.non_english_count = 0  # Non-English responses
        self.off_topic_count = 0  # Off-topic responses
        # Smart features
        self.difficulty_level = 1  # 1=easy, 2=medium, 3=hard
        self.correct_answers = 0
        self.total_questions = 8
        self.interview_duration_minutes = 30  # Total interview time
        self.scenario_time_threshold = 20  # Start scenarios after 20 minutes
        # Follow-up tracking for professional conversation flow
        self.last_answer_was_vague = False  # Track if we need to follow up
        self.follow_up_asked = False  # Prevent multiple follow-ups on same topic
        self.last_good_answer_topic = None  # Track for referencing in later questions
        self.praise_index = 0  # Rotate through praise phrases
    
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
            "substantive_answers": self.substantive_answers,
            "quality_scores": self.quality_scores,
            "difficulty_level": self.difficulty_level,
            "correct_answers": self.correct_answers,
            "inappropriate_count": self.inappropriate_count,
            "abusive_count": self.abusive_count,
            "non_english_count": self.non_english_count,
            "off_topic_count": self.off_topic_count
        }
    
    def get_elapsed_minutes(self):
        """Get elapsed time since interview started"""
        return (datetime.utcnow() - self.started_at).total_seconds() / 60
    
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
        """
        Comprehensive answer analysis with off-topic detection and quality scoring.
        Returns: {is_casual, is_off_topic, has_substance, quality_score, is_relevant}
        quality_score: 0=poor/off-topic, 1=vague/minimal, 2=decent, 3=excellent
        """
        msg_lower = message.lower().strip()
        word_count = len(message.split())
        
        # === Casual/Social Phrases ===
        casual_phrases = [
            "doing great", "doing good", "i'm good", "i'm fine", "doing fine",
            "good thanks", "fine thanks", "how are you", "what about you",
            "hello", "hi", "hey", "good morning", "good afternoon", "i'm doing well",
            "nice to meet", "pleasure to meet", "thank you for asking"
        ]
        
        # === Off-Topic/Irrelevant Phrases ===
        off_topic_phrases = [
            "weather", "lunch", "dinner", "breakfast", "food", "hungry",
            "movie", "music", "game", "sports", "cricket", "football", "basketball",
            "girlfriend", "boyfriend", "dating", "party", "vacation", "holiday",
            "what time is it", "what day is it", "where are you from",
            "how old are you", "are you real", "are you a bot", "are you ai",
            "tell me a joke", "sing a song", "write a poem",
            "pizza", "burger", "coffee", "tea", "water",
            "i love you", "that's funny", "lol", "haha", "lmao"
        ]
        
        # === Abusive/Inappropriate Language Detection ===
        abusive_phrases = [
            "fuck", "shit", "damn", "ass", "bitch", "bastard", "crap",
            "idiot", "stupid", "dumb", "hate you", "shut up", "go away",
            "f**k", "f***", "s**t", "a**", "b**ch", "wtf", "stfu",
            "screw you", "piss off", "get lost", "you suck", "loser",
            # Hindi/Hinglish abusive words (multiple spellings)
            "madarchod", "madarcho", "motherchod", "mc",
            "bhenchod", "behenchod", "banchod", "benchod", "bc", "bsdk",
            "chutiya", "chutia", "chodu", "chod", "chodna",
            "gandu", "gand", "gaand", "gand mara", "gand maro", "gand mar",
            "harami", "haramkhor", "haraamkhor",
            "sala", "saala", "sali", "saali",
            "lund", "lauda", "lawda", "loda",
            "chut", "bhosdike", "bhosdi", "bhos",
            "randi", "rand", "raand",
            "kutte", "kutta", "kamina", "kamine",
            "ullu", "gadha", "bakchod", "bakchodi"
        ]
        
        # === Non-English Detection (Hindi/other languages) ===
        # Split message into actual words for proper matching
        msg_words = set(re.findall(r'\b[a-z]+\b', msg_lower))
        
        # Check for non-ASCII characters that indicate non-English text
        has_devanagari = any(ord(c) >= 0x0900 and ord(c) <= 0x097F for c in message)
        has_arabic = any(ord(c) >= 0x0600 and ord(c) <= 0x06FF for c in message)
        has_chinese = any(ord(c) >= 0x4E00 and ord(c) <= 0x9FFF for c in message)
        
        # Common Hindi romanized words - only match FULL WORDS (not substrings)
        hindi_romanized = {
            'kya', 'kaise', 'hain', 'tum', 'mein', 'kuch', 'bolo', 'baat', 'nahi', 
            'kyun', 'aap', 'karo', 'hum', 'yeh', 'woh', 'kaun', 'kitna', 'accha', 'theek',
            'teri', 'tera', 'tere', 'meri', 'mera', 'bahut', 'gaya', 'gayi', 'gaye',
            'maru', 'maro', 'masti', 'bhaiya', 'bhai', 'didi', 'behen', 'abhi', 'kaha',
            'raha', 'rahi', 'rahe', 'karna', 'karta', 'karti', 'acha', 
            'lekin', 'matlab', 'samajh', 'dekh', 'dekho', 'suno', 'bata', 'batao',
            'jao', 'aao', 'chalo', 'ruko', 'bolna', 'bolta', 'nhi', 'kro', 'krna',
            'btao', 'bolo', 'sunna', 'bolte', 'karte', 'krte'
        }
        # Removed short words that cause false positives: 'hai', 'kar', 'aur', 'mere', 'bol', 'chal', 'ruk'
        
        # Count how many Hindi words appear as FULL WORDS in message
        hindi_word_matches = msg_words.intersection(hindi_romanized)
        
        # Only flag as non-English if: non-Latin script OR multiple (2+) Hindi words found
        is_non_english = has_devanagari or has_arabic or has_chinese or len(hindi_word_matches) >= 2
        
        if is_non_english and hindi_word_matches:
            print(f"[Non-English] Detected Hindi words: {hindi_word_matches}")
        
        # Check for abusive language
        is_abusive = any(phrase in msg_lower for phrase in abusive_phrases)
        
        # === Negative/Uncertain Indicators ===
        negative_phrases = [
            "i don't know", "i dont know", "not sure", "no idea", "can't answer",
            "cannot answer", "i have no", "never done", "never worked",
            "i guess", "maybe", "perhaps", "i think so", "probably",
            "i'm not familiar", "haven't used", "don't have experience",
            "no experience", "not really", "sorry i", "sorry, i"
        ]
        
        # === Positive/Quality Indicators ===
        positive_indicators = [
            "for example", "such as", "specifically", "in particular",
            "i implemented", "i developed", "i created", "i built", "i designed",
            "my approach", "my strategy", "my solution", "i solved",
            "years of experience", "worked on", "contributed to",
            "led the", "managed the", "responsible for",
            "using", "with", "through", "by implementing"
        ]
        
        # === Technical Keywords ===
        technical_keywords = [
            'algorithm', 'database', 'api', 'framework', 'architecture', 'deploy',
            'testing', 'agile', 'scrum', 'git', 'docker', 'kubernetes', 'cloud',
            'aws', 'azure', 'react', 'node', 'python', 'java', 'sql', 'mongodb',
            'microservice', 'ci/cd', 'optimization', 'performance', 'debug',
            'machine learning', 'data structure', 'component', 'server', 'client'
        ]
        
        # === Analysis ===
        is_casual = any(phrase in msg_lower for phrase in casual_phrases) and word_count < 12
        is_off_topic = any(phrase in msg_lower for phrase in off_topic_phrases) or is_non_english
        has_negative = any(phrase in msg_lower for phrase in negative_phrases)
        has_positive = any(phrase in msg_lower for phrase in positive_indicators)
        tech_count = sum(1 for kw in technical_keywords if kw in msg_lower)
        
        # === Check relevance to last question ===
        is_relevant = True
        if self.last_question_topic:
            topic_keywords = self.last_question_topic.lower().split()
            # Remove common words
            topic_keywords = [w for w in topic_keywords if len(w) > 3 and w not in ['your', 'about', 'with', 'the', 'and', 'how', 'what', 'when', 'where', 'experience']]
            # Check if any topic keyword appears in answer
            has_topic_match = any(kw in msg_lower for kw in topic_keywords)
            # If question was about specific topic and answer has no relation
            if not has_topic_match and not has_positive and tech_count == 0:
                is_relevant = word_count > 15  # Give benefit of doubt for longer answers
        
        # === Calculate Quality Score (0-3) ===
        quality_score = 0
        
        if is_off_topic:
            quality_score = 0
        elif is_casual:
            quality_score = 0
        elif has_negative and word_count < 15:
            quality_score = 1
        elif not is_relevant:
            quality_score = 0
        else:
            # Base score on content quality
            if word_count < 8:
                quality_score = 1
            elif word_count < 15:
                quality_score = 1 if not has_positive else 2
            elif word_count < 25:
                quality_score = 2 if has_positive or tech_count > 0 else 1
            else:
                # Long answer
                if has_positive and tech_count >= 2:
                    quality_score = 3
                elif has_positive or tech_count >= 1:
                    quality_score = 2
                else:
                    quality_score = 1 if not has_negative else 1
        
        # Boost for technical content
        if tech_count >= 3 and quality_score < 3:
            quality_score = min(3, quality_score + 1)
        
        # Penalize heavy negatives
        if has_negative and "don't know" in msg_lower:
            quality_score = min(quality_score, 1)
        
        has_substance = quality_score >= 2
        
        # Abusive or non-English = quality 0
        if is_abusive or is_non_english:
            quality_score = 0
            has_substance = False
        
        return {
            "is_casual": is_casual,
            "is_off_topic": is_off_topic,
            "is_abusive": is_abusive,
            "is_non_english": is_non_english,
            "has_substance": has_substance,
            "quality_score": quality_score,
            "is_relevant": is_relevant,
            "word_count": word_count,
            "tech_count": tech_count,
            "has_negative": has_negative
        }


# Response variety lists for natural conversation
PRAISE_PHRASES = [
    "Good point!", "Nice!", "That's helpful.", "Good insight.", 
    "I see.", "Interesting.", "Makes sense.", "That's useful.",
    "Good example!", "Thanks for sharing that."
]

EXCELLENT_PHRASES = [
    "Excellent!", "Great answer!", "Very impressive!", "That's exactly what I was looking for.",
    "Great example!", "Well explained!", "That shows strong experience."
]

ACKNOWLEDGMENT_PHRASES = [
    "I understand.", "Got it.", "Okay.", "I see.", "Alright."
]

FOLLOW_UP_PROMPTS = [
    "Can you give me a specific example?",
    "Could you elaborate on that?",
    "What was the outcome?",
    "Can you walk me through your approach?",
    "What was your specific role in that?"
]

def get_smart_system_prompt(session):
    """Generate intelligent system prompt like Groq engine"""
    difficulty_desc = {1: "basic/entry-level", 2: "intermediate", 3: "advanced/senior-level"}.get(session.difficulty_level, "intermediate")
    already_asked = ", ".join(session.asked_topics[-5:]) if session.asked_topics else "none yet"
    elapsed_minutes = session.get_elapsed_minutes()
    remaining_questions = session.total_questions - session.question_count
    
    # Get varied phrases for this response
    praise_phrase = PRAISE_PHRASES[session.praise_index % len(PRAISE_PHRASES)]
    excellent_phrase = EXCELLENT_PHRASES[session.praise_index % len(EXCELLENT_PHRASES)]
    
    # Time awareness
    time_context = ""
    if remaining_questions <= 2:
        time_context = "\n- WRAPPING UP: Only 1-2 questions left. Consider asking about final thoughts."
    
    return f"""You are Alex, a professional and friendly AI interviewer for the {session.position} position.

CURRENT STATE:
- Difficulty Level: {session.difficulty_level}/3 ({difficulty_desc})
- Question #{session.question_count + 1} of {session.total_questions}
- Time elapsed: {elapsed_minutes:.1f} minutes
- Already asked about: {already_asked}{time_context}

CRITICAL RULES FOR RESPONSE HANDLING:

1. OFF-TOPIC (weather, food, movies, jokes, unrelated):
   → Say "Let's get back to the interview." + ask next question. NO praise.

2. CASUAL GREETING ("I'm good", "how are you", "what about you"):
   → Say "Good to hear!" briefly, then redirect to interview question.

3. "I DON'T KNOW" / UNCERTAIN ("not sure", "can't answer", "no idea"):
   → Say "That's okay, let's try something else." + ask EASIER question. Be supportive.

4. VAGUE BUT RELEVANT (short answer, no examples, no specifics):
   → Ask a FOLLOW-UP: "Can you give me a specific example?" or "Could you elaborate?"
   → Only ask ONE follow-up, then move to next topic if still vague.

5. GOOD ANSWER (relevant with some detail):
   → Use VARIED praise: "{praise_phrase}" then ask next question.

6. EXCELLENT ANSWER (specific examples, technical details, STAR format):
   → Say "{excellent_phrase}" and reference their answer when asking harder question.
   → Example: "Great example of problem-solving. Building on that, how would you handle..."

7. BEHAVIORAL QUESTIONS - Use STAR prompting:
   → If answer lacks specifics, ask: "What was YOUR specific role?" or "What was the outcome?"

CONVERSATION STYLE:
- Vary your acknowledgments: "I see", "Got it", "Interesting", "Makes sense"
- Connect questions when possible: "You mentioned X earlier, how does that relate to..."
- Be encouraging but not over-praising
- Sound natural, not robotic

NEVER repeat a question you already asked (check "Already asked about" list).
Ask {difficulty_desc} questions appropriate for current level.
Keep response under 40 words total.
Never cut off mid-sentence.

RESPONSE EXAMPLES:
- Excellent: "{excellent_phrase} Building on that, [harder question]"
- Good: "{praise_phrase} [Next question]"
- Vague: "Can you give me a specific example of that?"
- Off-topic: "Let's get back to the interview. [Next question]"
- "I don't know": "That's okay. [Easier question]"
- Casual: "Good to hear! [Redirect to question]"
"""


def get_instruction_for_state(session, user_message, answer_analysis):
    """Get specific instruction based on interview state with quality-aware logic"""
    has_substance = answer_analysis["has_substance"]
    is_casual = answer_analysis["is_casual"]
    is_off_topic = answer_analysis.get("is_off_topic", False)
    has_negative = answer_analysis.get("has_negative", False)
    quality_score = answer_analysis.get("quality_score", 1)
    word_count = answer_analysis.get("word_count", 0)
    elapsed_minutes = session.get_elapsed_minutes()
    remaining_questions = session.total_questions - session.question_count
    
    # Get varied phrases
    praise = PRAISE_PHRASES[session.praise_index % len(PRAISE_PHRASES)]
    excellent = EXCELLENT_PHRASES[session.praise_index % len(EXCELLENT_PHRASES)]
    ack = ACKNOWLEDGMENT_PHRASES[session.praise_index % len(ACKNOWLEDGMENT_PHRASES)]
    follow_up = FOLLOW_UP_PROMPTS[session.praise_index % len(FOLLOW_UP_PROMPTS)]
    
    # Increment praise index for variety
    session.praise_index += 1
    
    # Build EXPLICIT analysis summary for AI
    user_said_summary = f"USER SAID: \"{user_message[:100]}...\"" if len(user_message) > 100 else f"USER SAID: \"{user_message}\""
    analysis_note = f"ANALYSIS: quality={quality_score}/3, words={word_count}, "
    if is_off_topic:
        analysis_note += "OFF-TOPIC (weather/food/unrelated), "
    if is_casual:
        analysis_note += "CASUAL/SOCIAL (not interview answer), "
    if has_negative:
        analysis_note += "SHOWS UNCERTAINTY, "
    if quality_score == 0:
        analysis_note += "POOR/IRRELEVANT. "
    elif quality_score == 1:
        analysis_note += "VAGUE/BRIEF - needs follow-up. "
    elif quality_score == 2:
        analysis_note += "DECENT - good answer. "
    else:
        analysis_note += "EXCELLENT - great detail! "
    
    # Track if this answer was vague for follow-up logic
    is_vague = quality_score == 1 and not is_off_topic and not is_casual and word_count >= 5
    
    # Handle "I don't know" / uncertainty - be supportive
    if has_negative and ("don't know" in user_message.lower() or "not sure" in user_message.lower() or "no idea" in user_message.lower()):
        question_topic = session.get_next_question_topic()
        session.last_question_topic = question_topic
        # Decrease difficulty for easier question
        if session.difficulty_level > 1:
            session.difficulty_level -= 1
        return f"{user_said_summary}\\n{analysis_note}\\nRESPOND: Say \"That's okay, let's try something else.\" then ask an EASIER question about {question_topic}. Be supportive. Under 30 words."
    
    # Handle off-topic responses in any state
    if is_off_topic:
        question_topic = session.get_next_question_topic()
        session.last_question_topic = question_topic
        return f"{user_said_summary}\\n{analysis_note}\\nRESPOND: Say 'Let's get back to the interview.' then ask about {question_topic}. NO praise. Under 30 words."
    
    if session.state == "greeting":
        # Check if this was actually a greeting or casual chat
        if is_casual or word_count < 5:
            return f"{user_said_summary}\\n{analysis_note}\\nRESPOND: Say 'Good to hear!' then ask them to introduce themselves and share their interest in {session.position}. Under 30 words."
        return f"{user_said_summary}\\n{analysis_note}\\nRESPOND: Say '{ack}' then ask them to tell you about themselves and why they're interested in {session.position}. Under 30 words."
    
    elif session.state == "introduction":
        question_topic = session.get_next_question_topic()
        session.last_question_topic = question_topic  # Track for relevance checking
        
        # Check if they actually introduced themselves
        intro_keywords = ['name is', 'i am', "i'm a", 'my background', 'i have experience', 'i graduated', 'i work', 'i studied', 'years of', 'pursuing', 'studying', 'student', 'engineering', 'degree']
        has_intro_content = any(kw in user_message.lower() for kw in intro_keywords)
        
        if quality_score >= 2 and has_intro_content:
            session.last_good_answer_topic = "their background"
            return f"{user_said_summary}\\n{analysis_note}User gave a proper introduction.\\nRESPOND: Say 'Thanks for sharing that!' then ask about {question_topic}. Under 30 words."
        elif is_casual or not has_intro_content:
            return f"{user_said_summary}\\n{analysis_note}User did NOT actually introduce themselves.\\nRESPOND: Say 'I'd like to know more about you.' then ask about their background and experience relevant to {session.position}. Under 30 words."
        else:
            return f"{user_said_summary}\\n{analysis_note}\\nRESPOND: Say '{ack}' and ask about {question_topic}. Under 30 words."
    
    elif session.state == "interviewing":
        # TIME-BASED scenario trigger (after 20 minutes) OR count-based (last 2 questions)
        should_do_scenario = (elapsed_minutes >= session.scenario_time_threshold) or (session.question_count >= session.total_questions - 2)
        
        if should_do_scenario and session.question_count < session.total_questions:
            scenario_topic = session.get_scenario_topic()
            session.last_question_topic = scenario_topic
            if quality_score >= 2:
                return f"{user_said_summary}\\n{analysis_note}\\nRESPOND: Say '{praise}' then present this scenario: {scenario_topic}. Under 45 words total."
            else:
                return f"{user_said_summary}\\n{analysis_note}\\nRESPOND: Present this scenario directly: {scenario_topic}. NO praise. Under 40 words."
        
        # Check if time to close / wrapping up
        if session.question_count >= session.total_questions:
            return f"{user_said_summary}\\n{analysis_note}\\nRESPOND: Thank them warmly for the conversation and ask if they have any questions for you. Under 25 words."
        
        # WRAPPING UP - last 1-2 questions
        if remaining_questions <= 2 and quality_score >= 2:
            return f"{user_said_summary}\\n{analysis_note}\\nRESPOND: Say '{praise}' then say 'We're wrapping up. Any final thoughts on why you'd be a great fit for this {session.position} role?' Under 35 words."
        
        # === FOLLOW-UP LOGIC for vague answers ===
        # If answer was vague and we haven't asked follow-up yet, probe deeper
        if is_vague and not session.follow_up_asked and session.last_question_topic:
            session.follow_up_asked = True
            session.last_answer_was_vague = True
            # Use STAR prompting for behavioral questions
            if any(word in session.last_question_topic.lower() for word in ['challenge', 'problem', 'conflict', 'difficult', 'team', 'project']):
                return f"{user_said_summary}\\n{analysis_note}Answer is vague - use STAR prompting.\\nRESPOND: Ask '{follow_up}' to get more specifics. Under 20 words."
            else:
                return f"{user_said_summary}\\n{analysis_note}Answer is vague - ask for elaboration.\\nRESPOND: Say 'Can you give me a specific example?' Under 15 words."
        
        # Reset follow-up tracking when moving to new topic
        session.follow_up_asked = False
        session.last_answer_was_vague = False
        
        # Get next question based on difficulty
        question_topic = session.get_next_question_topic()
        session.last_question_topic = question_topic  # Track for relevance checking
        
        # Quality-aware response with VARIETY
        if quality_score >= 3:
            session.last_good_answer_topic = question_topic
            # Reference their excellent answer
            return f"{user_said_summary}\\n{analysis_note}EXCELLENT answer!\\nRESPOND: Say '{excellent}' and connect to next question: 'Building on that, {question_topic}?' Under 35 words."
        elif quality_score == 2:
            session.last_good_answer_topic = question_topic
            return f"{user_said_summary}\\n{analysis_note}Good answer.\\nRESPOND: Say '{praise}' then ask about {question_topic}. Under 30 words."
        elif is_casual:
            return f"{user_said_summary}\\n{analysis_note}Casual response.\\nRESPOND: Say 'Good to hear!' then ask about {question_topic}. Under 30 words."
        else:
            # Poor/vague answer after follow-up - just move on
            return f"{user_said_summary}\\n{analysis_note}\\nRESPOND: Say '{ack}' and ask about {question_topic}. Under 30 words."
    
    elif session.state == "closing":
        # Personalized closing based on interview quality
        avg_score = sum(session.quality_scores) / len(session.quality_scores) if session.quality_scores else 1
        if avg_score >= 2:
            return f"{user_said_summary}\\n{analysis_note}\\nRESPOND: Give a warm, positive closing. Say you enjoyed the conversation and wish them the best. Under 25 words."
        else:
            return f"{user_said_summary}\\n{analysis_note}\\nRESPOND: Give a professional closing. Thank them for their time and wish them luck. Under 20 words."
    
    return "Respond naturally and professionally as Alex the interviewer."


def get_direct_question(session, repeat_last=True):
    """Get a direct question without calling AI - for handling inappropriate responses
    If repeat_last=True, re-ask the last question (for bad responses)
    If repeat_last=False, get next question
    """
    if session.state == "greeting":
        return f"Could you please introduce yourself and tell me about your interest in the {session.position} role?"
    elif session.state == "introduction":
        # For introduction, ask them to introduce themselves again
        return f"Please tell me about yourself and your background relevant to {session.position}."
    elif session.state == "interviewing":
        # Re-ask the SAME question if they didn't answer properly
        if repeat_last and session.last_question_topic:
            return f"Can you please answer: {session.last_question_topic}?"
        else:
            topic = session.get_next_question_topic()
            session.last_question_topic = topic
            return f"Can you tell me about {topic}?"
    else:
        return "Do you have any questions for me?"


def update_session_state(session, answer_analysis):
    """Update interview state and difficulty based on answer quality score"""
    quality_score = answer_analysis.get("quality_score", 1)
    is_off_topic = answer_analysis.get("is_off_topic", False)
    has_negative = answer_analysis.get("has_negative", False)
    word_count = answer_analysis.get("word_count", 0)
    
    # Track quality score
    session.quality_scores.append(quality_score)
    
    if session.state == "greeting":
        session.state = "introduction"
    
    elif session.state == "introduction":
        session.state = "interviewing"
        session.question_count = 1
    
    elif session.state == "interviewing":
        session.question_count += 1
        
        # === PROGRESSIVE DIFFICULTY ADJUSTMENT ===
        # Increase difficulty for good answers (quality_score >= 2 AND decent length)
        if quality_score >= 2 and not is_off_topic and word_count >= 15:
            session.correct_answers += 1
            print(f"✅ Good answer #{session.correct_answers} (quality={quality_score}, words={word_count})")
            
            # Increase difficulty every 2 good answers (faster progression)
            if session.correct_answers >= 2 and session.difficulty_level < 3:
                if session.correct_answers % 2 == 0:
                    session.difficulty_level += 1
                    print(f"⬆️ Difficulty increased to level {session.difficulty_level}/3")
        
        # EXCELLENT answer (quality 3 with good length) - immediate difficulty increase
        elif quality_score >= 3 and word_count >= 25:
            session.correct_answers += 2  # Counts as 2 good answers
            print(f"🌟 Excellent answer! (quality={quality_score}, words={word_count})")
            if session.difficulty_level < 3:
                session.difficulty_level += 1
                print(f"⬆️ Difficulty increased to level {session.difficulty_level}/3 (excellent answer)")
        
        # DECREASE difficulty if struggling (multiple poor answers in a row)
        recent_scores = session.quality_scores[-3:] if len(session.quality_scores) >= 3 else session.quality_scores
        if len(recent_scores) >= 3 and all(s <= 1 for s in recent_scores):
            if session.difficulty_level > 1:
                session.difficulty_level -= 1
                print(f"⬇️ Difficulty decreased to level {session.difficulty_level}/3 (struggling)")
        
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
        user_message = data.get('message', '').strip()
        
        # Get session
        if session_id not in active_sessions:
            return jsonify({
                "success": False,
                "error": "Session not found",
                "session_expired": True
            }), 404
        
        interview_session = active_sessions[session_id]
        
        # === Handle empty/silence responses ===
        if not user_message or len(user_message) < 3:
            # Treat as "no response" - prompt them to answer
            return jsonify({
                "success": True,
                "message": "I didn't catch that. Could you please repeat your answer?",
                "state": interview_session.state,
                "question_count": interview_session.question_count,
                "difficulty_level": interview_session.difficulty_level,
                "should_speak": True,
                "was_empty": True
            })
        
        # Analyze user's answer quality (comprehensive analysis)
        answer_analysis = interview_session.analyze_answer(user_message)
        
        # Log analysis for debugging
        print(f"📊 Answer Analysis: quality={answer_analysis['quality_score']}, "
              f"off_topic={answer_analysis['is_off_topic']}, "
              f"casual={answer_analysis['is_casual']}, "
              f"abusive={answer_analysis.get('is_abusive', False)}, "
              f"non_english={answer_analysis.get('is_non_english', False)}, "
              f"tech_count={answer_analysis['tech_count']}")
        
        # === DIRECT HANDLING: Abusive language - don't even call AI ===
        if answer_analysis.get('is_abusive', False):
            # Track inappropriate response
            interview_session.inappropriate_count += 1
            interview_session.abusive_count += 1
            # Re-ask the SAME question, don't advance state
            warning_response = "Please maintain professional language. " + get_direct_question(interview_session, repeat_last=True)
            interview_session.conversation_history.append({"role": "user", "content": user_message})
            interview_session.conversation_history.append({"role": "assistant", "content": warning_response})
            # Don't add to answers, don't update state - just re-ask
            interview_session.quality_scores.append(0)
            
            return jsonify({
                "success": True,
                "message": warning_response,
                "state": interview_session.state,
                "question_count": interview_session.question_count,
                "difficulty_level": interview_session.difficulty_level,
                "should_speak": True,
                "was_inappropriate": True
            })
        
        # === DIRECT HANDLING: Non-English response ===
        if answer_analysis.get('is_non_english', False):
            # Track inappropriate response
            interview_session.inappropriate_count += 1
            interview_session.non_english_count += 1
            # Re-ask the SAME question, don't advance state
            english_response = "Please respond in English. " + get_direct_question(interview_session, repeat_last=True)
            interview_session.conversation_history.append({"role": "user", "content": user_message})
            interview_session.conversation_history.append({"role": "assistant", "content": english_response})
            # Don't add to answers, don't update state - just re-ask
            interview_session.quality_scores.append(0)
            
            return jsonify({
                "success": True,
                "message": english_response,
                "state": interview_session.state,
                "question_count": interview_session.question_count,
                "difficulty_level": interview_session.difficulty_level,
                "should_speak": True,
                "was_non_english": True
            })
        
        # === DIRECT HANDLING: Clearly off-topic (weather, movies, jokes, etc.) ===
        if answer_analysis.get('is_off_topic', False):
            # Track inappropriate response
            interview_session.inappropriate_count += 1
            interview_session.off_topic_count += 1
            # Re-ask the SAME question, don't advance state
            offtopic_response = "Let's focus on the interview. " + get_direct_question(interview_session, repeat_last=True)
            interview_session.conversation_history.append({"role": "user", "content": user_message})
            interview_session.conversation_history.append({"role": "assistant", "content": offtopic_response})
            # Don't add to answers, don't update state - just re-ask
            interview_session.quality_scores.append(0)
            
            return jsonify({
                "success": True,
                "message": offtopic_response,
                "state": interview_session.state,
                "question_count": interview_session.question_count,
                "difficulty_level": interview_session.difficulty_level,
                "should_speak": True,
                "was_off_topic": True
            })
        
        # Add user message to history
        interview_session.conversation_history.append({
            "role": "user",
            "content": user_message
        })
        interview_session.answers.append(user_message)
        
        # === Track substantive answers separately (for accurate scoring) ===
        if answer_analysis["quality_score"] >= 2 and not answer_analysis["is_off_topic"]:
            interview_session.substantive_answers.append(user_message)
        
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
    """Generate comprehensive AI-powered feedback for completed interview using Groq"""
    
    duration_minutes = round((datetime.utcnow() - session.started_at).total_seconds() / 60, 1)
    questions_answered = len(session.answers)
    
    # Use SUBSTANTIVE answers for quality analysis (excludes casual/off-topic)
    substantive_count = len(session.substantive_answers)
    quality = _analyze_response_quality(session.substantive_answers if session.substantive_answers else session.answers)
    
    # Add substantive_answers to quality dict for ratio calculation
    quality['substantive_answers'] = session.substantive_answers
    
    # Calculate average quality score from tracked scores
    avg_quality_score = sum(session.quality_scores) / len(session.quality_scores) if session.quality_scores else 0
    
    # Count technical discussion (quality >= 2 means actual technical content)
    technical_responses = sum(1 for s in session.quality_scores if s >= 2)
    
    print(f"[Feedback] Duration: {duration_minutes:.1f}min, Total answers: {questions_answered}, Substantive: {substantive_count}, Technical: {technical_responses}, Avg quality: {avg_quality_score:.1f}")
    
    # === STRICT EARLY TERMINATION / NO EFFORT DETECTION ===
    early_termination = None
    max_score_cap = 100  # Default no cap
    
    # VERY early termination (< 2 min OR < 2 questions) - SEVERE penalty
    if duration_minutes < 2 or questions_answered < 2:
        early_termination = {
            "detected": True,
            "severity": "critical",
            "message": "Interview ended extremely early. Unable to properly assess candidate.",
            "penalty": 50
        }
        max_score_cap = 30  # Cap all scores at 30
    
    # Early termination (< 5 min OR < 4 questions)
    elif duration_minutes < 5 or questions_answered < 4:
        early_termination = {
            "detected": True,
            "severity": "high",
            "message": "Interview ended early with insufficient questions to assess skills.",
            "penalty": 35
        }
        max_score_cap = 45  # Cap all scores at 45
    
    # Short interview (< 8 min OR < 6 questions)
    elif duration_minutes < 8 or questions_answered < 6:
        early_termination = {
            "detected": True,
            "severity": "medium", 
            "message": "Interview was shorter than recommended. More questions would better demonstrate skills.",
            "penalty": 20
        }
        max_score_cap = 65  # Cap all scores at 65
    
    # NO TECHNICAL DISCUSSION - user never gave technical answers
    if technical_responses == 0 and questions_answered >= 2:
        early_termination = {
            "detected": True,
            "severity": "critical",
            "message": "No technical or substantive discussion occurred during the interview.",
            "penalty": 45
        }
        max_score_cap = min(max_score_cap, 35)  # Cap at 35 if no technical
    
    # Check for mostly casual/off-topic responses
    elif substantive_count < max(1, questions_answered * 0.3):  # Less than 30% substantive
        early_termination = {
            "detected": True,
            "severity": "high",
            "message": "Most responses were off-topic, casual, or lacked substance.",
            "penalty": 40
        }
        max_score_cap = min(max_score_cap, 40)
    
    # Try AI-powered analysis using GROQ (instead of Perplexity)
    ai_analysis = None
    try:
        api_key = get_groq_key()
        if api_key and session.conversation_history:
            # Build conversation summary (only substantive parts)
            conv_text = ""
            for msg in session.conversation_history:
                role = "Interviewer" if msg['role'] == 'assistant' else "Candidate"
                conv_text += f"{role}: {msg['content']}\n\n"
            
            analysis_prompt = f"""You are an expert interview evaluator. Analyze this interview transcript for a {session.position} position.

INTERVIEW TRANSCRIPT:
{conv_text}

CANDIDATE METRICS:
- Name: {session.user_name}
- Position: {session.position}
- Total responses: {questions_answered}
- Substantive responses: {substantive_count}
- Average quality score: {avg_quality_score:.1f}/3
- Average response length: {quality['avg_length']} words
- Technical keywords used: {quality['technical_keywords']}
- Casual/filler phrases: {quality['casual_count']}
- INAPPROPRIATE RESPONSES: {session.inappropriate_count} total ({session.abusive_count} abusive, {session.non_english_count} non-English, {session.off_topic_count} off-topic)

CRITICAL SCORING RULES:
1. If ANY abusive language was used, professionalism MUST be 20 or below
2. If multiple inappropriate responses ({session.inappropriate_count}), communication should be LOW (20-40)
3. If most responses were off-topic/casual (substantive < 50%), scores should be LOW (20-40)
4. If candidate said "I don't know" frequently, technical_knowledge should be LOW
5. Short vague answers = LOW scores (30-50)
6. Only give 70+ for specific examples and demonstrated knowledge
7. Only give 85+ for exceptional detail with real project examples

SCORING RUBRIC (0-100):
- technical_knowledge: 0-30=vague/wrong, 31-50=minimal understanding, 51-70=basic knowledge, 71-85=good with examples, 86-100=expert
- communication: 0-30=unclear/inappropriate, 31-50=understandable but unstructured, 51-70=clear, 71-85=well-structured, 86-100=excellent STAR method
- problem_solving: 0-30=no analysis, 31-50=basic, 51-70=some approach, 71-85=structured, 86-100=systematic with trade-offs
- professionalism: 0-30=inappropriate/abusive, 31-50=casual, 51-70=professional, 71-85=polished, 86-100=exemplary
- enthusiasm: 0-30=disinterested, 31-50=neutral, 51-70=interested, 71-85=eager, 86-100=genuinely passionate
- confidence: 0-30=very unsure, 31-50=hesitant, 51-70=confident, 71-85=assured, 86-100=poised

Respond ONLY with this JSON (no markdown, no explanation):
{{
  "scores": {{"technical_knowledge": <num>, "communication": <num>, "problem_solving": <num>, "professionalism": <num>, "enthusiasm": <num>, "confidence": <num>}},
  "strengths": ["<strength1>", "<strength2>", "<strength3>"],
  "improvements": ["<improvement1>", "<improvement2>", "<improvement3>"],
  "knowledge_assessment": {{"demonstrated_skills": ["<skill1>"], "skill_gaps": ["<gap1>"], "depth_of_knowledge": "<shallow/moderate/deep>"}},
  "communication_feedback": {{"clarity": "<assessment>", "structure": "<assessment>", "vocabulary": "<assessment>"}},
  "interviewer_guidance": {{"hiring_recommendation": "<Strong Hire/Hire/Maybe/No Hire>", "reasoning": "<explanation>", "follow_up_areas": ["<area1>"]}},
  "detailed_feedback": "<2-3 sentence assessment>"
}}"""

            print(f"[Interview Feedback] Calling GROQ API for analysis...")
            
            response = requests.post(
                GROQ_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "llama-3.1-8b-instant",
                    "messages": [
                        {"role": "system", "content": "You are an expert interview evaluator. Respond ONLY with valid JSON, no markdown, no code blocks."},
                        {"role": "user", "content": analysis_prompt}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 1000
                },
                timeout=30
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
                json_match = re.search(r'\{[\s\S]*\}', ai_text)
                if json_match:
                    ai_analysis = json.loads(json_match.group())
                    print(f"[Interview Feedback] GROQ analysis successful: scores={ai_analysis.get('scores', {})}")
                else:
                    print(f"[Interview Feedback] Could not find JSON in AI response: {ai_text[:200]}")
            else:
                print(f"[Interview Feedback] GROQ API error: {response.status_code}")
                
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
        
        # === APPLY MAXIMUM SCORE CAP (based on interview quality) ===
        print(f"[Interview Feedback] Max score cap: {max_score_cap}")
        for key in scores:
            scores[key] = min(scores[key], max_score_cap)
        
        # Apply early termination penalty on top of cap
        if early_termination:
            penalty = early_termination['penalty']
            print(f"[Interview Feedback] Applying early termination penalty: -{penalty}")
            for key in scores:
                scores[key] = max(5, scores[key] - penalty)
        
        # === ADJUST BASED ON RESPONSE QUALITY ===
        # Very short answers = low scores
        if quality['avg_length'] < 8:
            print(f"[Interview Feedback] Very short avg response ({quality['avg_length']} words) - capping at 35")
            for key in scores:
                scores[key] = min(scores[key], 35)
        elif quality['avg_length'] < 15:
            print(f"[Interview Feedback] Short avg response ({quality['avg_length']} words) - capping at 50")
            for key in scores:
                scores[key] = min(scores[key], 50)
        elif quality['avg_length'] < 25:
            print(f"[Interview Feedback] Moderate avg response ({quality['avg_length']} words) - capping at 70")
            for key in scores:
                scores[key] = min(scores[key], 70)
        
        # === SPECIFIC CATEGORY ADJUSTMENTS ===
        # Technical knowledge based on actual technical content
        if quality['technical_keywords'] < 2:
            print(f"[Interview Feedback] Low technical keywords ({quality['technical_keywords']}) - capping technical_knowledge at 40")
            scores['technical_knowledge'] = min(scores['technical_knowledge'], 40)
        elif quality['technical_keywords'] < 5:
            scores['technical_knowledge'] = min(scores['technical_knowledge'], 60)
        
        # Communication based on casual phrases
        if quality['casual_count'] > 5:
            scores['communication'] = min(scores['communication'], 40)
            scores['professionalism'] = min(scores['professionalism'], 45)
        elif quality['casual_count'] > 3:
            scores['communication'] = min(scores['communication'], 55)
            scores['professionalism'] = min(scores['professionalism'], 55)
        
        # === CRITICAL: Penalize for inappropriate behavior ===
        if session.abusive_count > 0:
            print(f"[Interview Feedback] ABUSIVE behavior detected ({session.abusive_count}x) - capping professionalism at 15")
            scores['professionalism'] = min(scores['professionalism'], 15)
            scores['communication'] = min(scores['communication'], 30)
            scores['confidence'] = min(scores['confidence'], 35)
        
        if session.inappropriate_count > 2:
            print(f"[Interview Feedback] Multiple inappropriate responses ({session.inappropriate_count}) - reducing scores")
            scores['communication'] = min(scores['communication'], 35)
            scores['professionalism'] = min(scores['professionalism'], 35)
        
        if session.off_topic_count > 3:
            print(f"[Interview Feedback] Many off-topic responses ({session.off_topic_count}) - capping scores")
            scores['communication'] = min(scores['communication'], 40)
            scores['enthusiasm'] = min(scores['enthusiasm'], 40)
        
        # === CRITICAL: Cap scores based on substantive answer ratio ===
        total_responses = questions_answered if questions_answered > 0 else 1
        substantive_ratio = len(quality.get('substantive_answers', [])) / max(1, total_responses)
        print(f"[Interview Feedback] Substantive ratio: {substantive_ratio:.2f} ({len(quality.get('substantive_answers', []))}/{total_responses})")
        
        if substantive_ratio < 0.2:
            # Less than 20% good answers - cap all scores at 35
            print(f"[Interview Feedback] VERY LOW substantive ratio - capping all scores at 35")
            for key in scores:
                scores[key] = min(scores[key], 35)
        elif substantive_ratio < 0.4:
            # Less than 40% good answers - cap all scores at 50
            print(f"[Interview Feedback] LOW substantive ratio - capping all scores at 50")
            for key in scores:
                scores[key] = min(scores[key], 50)
        elif substantive_ratio < 0.6:
            # Less than 60% good answers - cap all scores at 65
            print(f"[Interview Feedback] MEDIUM substantive ratio - capping all scores at 65")
            for key in scores:
                scores[key] = min(scores[key], 65)
        
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
        # Start with base score based on overall engagement
        base_score = 30  # Start lower - must earn points
        
        # Add points for response length
        if quality['avg_length'] >= 30:
            base_score += 25
        elif quality['avg_length'] >= 20:
            base_score += 15
        elif quality['avg_length'] >= 12:
            base_score += 8
        elif quality['avg_length'] < 8:
            base_score -= 10  # Very short answers = penalty
        
        # Add points for technical content
        tech_bonus = min(25, quality['technical_keywords'] * 4)
        
        # Penalty for casual/unprofessional language
        casual_penalty = min(20, quality['casual_count'] * 6)
        
        # Bonus for completing more questions
        completion_bonus = min(15, questions_answered * 2)
        
        scores = {
            'technical_knowledge': max(10, min(max_score_cap, base_score + tech_bonus)),
            'communication': max(10, min(max_score_cap, base_score + 5 - casual_penalty)),
            'problem_solving': max(10, min(max_score_cap, base_score - 5 + tech_bonus // 2)),
            'professionalism': max(10, min(max_score_cap, base_score - casual_penalty)),
            'enthusiasm': max(10, min(max_score_cap, base_score + completion_bonus // 2)),
            'confidence': max(10, min(max_score_cap, base_score))
        }
        
        # Apply early termination penalty
        if early_termination:
            penalty = early_termination['penalty']
            print(f"[Interview Feedback] Fallback - applying penalty: -{penalty}")
            for key in scores:
                scores[key] = max(5, scores[key] - penalty)
        
        # Apply max cap
        for key in scores:
            scores[key] = min(scores[key], max_score_cap)
        
        # If no technical keywords, cap technical knowledge very low
        if quality['technical_keywords'] == 0:
            scores['technical_knowledge'] = min(scores['technical_knowledge'], 30)
        
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
