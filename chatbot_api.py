"""
Secure Chatbot Backend using FastAPI, Gemini API, and MongoDB
With PII filtering and Tool Calling architecture
"""

import os
import re
import json
import asyncio
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

import google.generativeai as genai

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================
# Configuration
# ============================================

MONGODB_URI = os.getenv("MONGODB_URI") or os.getenv("MONGO_URI")
MONGODB_DB = os.getenv("MONGODB_DB", "Placement_Ai")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_API") or os.getenv("GOOGLE_API_KEY")

# Validate required environment variables
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY, GEMINI_API, or GOOGLE_API_KEY must be set in .env")

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)

# ============================================
# PII Filter Configuration
# ============================================

# Fields to ALWAYS exclude from LLM context (sensitive PII)
SENSITIVE_FIELDS = {
    "_id",
    "password",
    "password_hash",
    "hashed_password",
    "ssn",
    "social_security",
    "credit_card",
    "card_number",
    "cvv",
    "bank_account",
    "otp",
    "otp_expiry",
    "token",
    "refresh_token",
    "access_token",
    "secret_key",
    "api_key",
    "private_key",
}

# Fields to partially mask (show only last 4 chars)
MASK_FIELDS = {
    "phone",
    "mobile",
    "phoneNumber",
}

# ============================================
# MongoDB Projection Builder
# ============================================

def build_safe_projection() -> Dict[str, int]:
    """Build MongoDB projection to exclude sensitive fields"""
    return {field: 0 for field in SENSITIVE_FIELDS}


def sanitize_document(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize a MongoDB document by:
    1. Removing sensitive fields
    2. Masking partially sensitive fields
    3. Converting ObjectId to string
    """
    if not doc:
        return {}
    
    sanitized = {}
    
    for key, value in doc.items():
        # Skip sensitive fields
        if key.lower() in {f.lower() for f in SENSITIVE_FIELDS}:
            continue
        
        # Mask phone numbers (show last 4 digits)
        if key.lower() in {f.lower() for f in MASK_FIELDS}:
            if isinstance(value, str) and len(value) >= 4:
                sanitized[key] = f"***{value[-4:]}"
            else:
                sanitized[key] = "***"
            continue
        
        # Handle ObjectId
        if hasattr(value, '__str__') and key == '_id':
            continue  # Skip _id entirely
        
        # Handle nested documents
        if isinstance(value, dict):
            sanitized[key] = sanitize_document(value)
        # Handle lists
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_document(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            sanitized[key] = value
    
    return sanitized


# ============================================
# Database Functions (Tools)
# ============================================

class DatabaseTools:
    """Secure database query tools for the chatbot"""
    
    def __init__(self, db):
        self.db = db
    
    async def get_user_profile(self, email: Optional[str] = None, name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get user profile from database with PII filtering.
        
        Args:
            email: User's email address
            name: User's name
            
        Returns:
            Sanitized user profile without sensitive PII
        """
        if not email and not name:
            return {"error": "Please provide either email or name to search"}
        
        # Build query
        query = {}
        if email:
            query["email"] = {"$regex": email, "$options": "i"}
        elif name:
            query["name"] = {"$regex": name, "$options": "i"}
        
        # Use projection to exclude sensitive fields at DB level
        projection = build_safe_projection()
        
        try:
            # Try multiple collections where user data might exist
            collections_to_search = ["users", "Resume", "students", "profiles"]
            
            for collection_name in collections_to_search:
                collection = self.db[collection_name]
                user = await collection.find_one(query, projection)
                
                if user:
                    # Additional sanitization layer
                    sanitized = sanitize_document(user)
                    sanitized["_source_collection"] = collection_name
                    logger.info(f"Found user in {collection_name}: {list(sanitized.keys())}")
                    return sanitized
            
            return {"message": "No user found with the provided information"}
            
        except Exception as e:
            logger.error(f"Database query error: {e}")
            return {"error": "Failed to query user profile"}
    
    async def get_user_skills(self, email: Optional[str] = None, name: Optional[str] = None) -> Dict[str, Any]:
        """Get user's skills from their resume/profile"""
        if not email and not name:
            return {"error": "Please provide either email or name"}
        
        query = {}
        if email:
            query["email"] = {"$regex": email, "$options": "i"}
        elif name:
            query["name"] = {"$regex": name, "$options": "i"}
        
        # Use exclusion projection only (no mixing with inclusion)
        projection = build_safe_projection()
        
        try:
            collection = self.db["Resume"]
            user = await collection.find_one(query, projection)
            
            if user:
                # Extract only skills-related fields after fetch
                sanitized = sanitize_document(user)
                skills_data = {
                    "name": sanitized.get("name"),
                    "email": sanitized.get("email"),
                    "skills": sanitized.get("skills", []),
                }
                return {k: v for k, v in skills_data.items() if v}
            return {"message": "No skills data found"}
            
        except Exception as e:
            logger.error(f"Skills query error: {e}")
            return {"error": "Failed to query skills"}
    
    async def get_user_education(self, email: Optional[str] = None, name: Optional[str] = None) -> Dict[str, Any]:
        """Get user's education information"""
        if not email and not name:
            return {"error": "Please provide either email or name"}
        
        query = {}
        if email:
            query["email"] = {"$regex": email, "$options": "i"}
        elif name:
            query["name"] = {"$regex": name, "$options": "i"}
        
        projection = build_safe_projection()
        
        try:
            collection = self.db["Resume"]
            user = await collection.find_one(query, projection)
            
            if user:
                # Extract only education-related fields
                education_data = {
                    "name": user.get("name"),
                    "degree": user.get("degree"),
                    "university": user.get("university"),
                    "cgpa": user.get("cgpa"),
                    "bachelorDegree": user.get("bachelorDegree"),
                    "bachelorUniversity": user.get("bachelorUniversity"),
                    "bachelorCGPA": user.get("bachelorCGPA"),
                    "mastersDegree": user.get("mastersDegree"),
                    "mastersUniversity": user.get("mastersUniversity"),
                    "mastersCGPA": user.get("mastersCGPA"),
                }
                # Remove None values
                return {k: v for k, v in education_data.items() if v is not None}
            
            return {"message": "No education data found"}
            
        except Exception as e:
            logger.error(f"Education query error: {e}")
            return {"error": "Failed to query education"}
    
    async def get_user_experience(self, email: Optional[str] = None, name: Optional[str] = None) -> Dict[str, Any]:
        """Get user's work experience and internships"""
        if not email and not name:
            return {"error": "Please provide either email or name"}
        
        query = {}
        if email:
            query["email"] = {"$regex": email, "$options": "i"}
        elif name:
            query["name"] = {"$regex": name, "$options": "i"}
        
        projection = build_safe_projection()
        
        try:
            collection = self.db["Resume"]
            user = await collection.find_one(query, projection)
            
            if user:
                experience_data = {
                    "name": user.get("name"),
                    "internships": user.get("internships", []),
                    "experience": user.get("experience", []),
                    "projects": user.get("projects", []),
                }
                return {k: v for k, v in experience_data.items() if v}
            
            return {"message": "No experience data found"}
            
        except Exception as e:
            logger.error(f"Experience query error: {e}")
            return {"error": "Failed to query experience"}
    
    async def get_placement_prediction(self, email: Optional[str] = None, name: Optional[str] = None) -> Dict[str, Any]:
        """Get user's placement prediction score and all related scores"""
        if not email and not name:
            return {"error": "Please provide either email or name"}
        
        query = {}
        if email:
            query["email"] = {"$regex": email, "$options": "i"}
        elif name:
            query["name"] = {"$regex": name, "$options": "i"}
        
        projection = build_safe_projection()
        
        try:
            # First check Resume collection which has the most complete prediction data
            resume_collection = self.db["Resume"]
            resume = await resume_collection.find_one(query, projection)
            
            if resume and resume.get("prediction"):
                prediction = resume.get("prediction", {})
                ats_data = resume.get("atsScore", {})
                score_breakdown = prediction.get("scoreBreakdown", {})
                
                result = {
                    "name": resume.get("name"),
                    # Main scores
                    "placementScore": prediction.get("placementScore"),
                    "isEligible": prediction.get("isEligible"),
                    "mlModelScore": prediction.get("mlModelScore"),
                    "predictionConfidence": prediction.get("predictionConfidence"),
                    # Component scores
                    "academicScore": prediction.get("academicScore"),
                    "skillScore": prediction.get("skillScore"),
                    "projectScore": prediction.get("projectScore"),
                    "dsaScore": prediction.get("dsaScore"),
                    "experienceScore": prediction.get("experienceScore"),
                    "certificationScore": prediction.get("certificationScore"),
                    "achievementScore": prediction.get("achievementScore"),
                    # Weighted contributions
                    "weightedAcademics": score_breakdown.get("academics"),
                    "weightedSkills": score_breakdown.get("skills"),
                    "weightedProjects": score_breakdown.get("projects"),
                    "weightedDSA": score_breakdown.get("dsa"),
                    "weightedExperience": score_breakdown.get("experience"),
                    # ATS Score if available
                    "atsScore": ats_data.get("total_score") if ats_data else None,
                    "atsRating": ats_data.get("rating") if ats_data else None,
                    # Top 3 recommendations only
                    "recommendations": prediction.get("recommendations", [])[:3],
                }
                
                # Remove None values for cleaner output
                return {k: v for k, v in result.items() if v is not None}
            
            # Fallback to student_analysis collection
            analysis_collection = self.db["student_analysis"]
            analysis = await analysis_collection.find_one(query, projection)
            
            if analysis:
                return sanitize_document(analysis)
            
            return {"message": "No placement prediction found for this user. They should go to the Prediction page to generate their placement score."}
            
        except Exception as e:
            logger.error(f"Prediction query error: {e}")
            return {"error": "Failed to query prediction"}
    
    async def get_user_job_selection(self, email: Optional[str] = None, name: Optional[str] = None) -> Dict[str, Any]:
        """Get user's selected job role and domain from their resume"""
        if not email and not name:
            return {"error": "Please provide either email or name"}
        
        query = {}
        if email:
            query["email"] = {"$regex": email, "$options": "i"}
        elif name:
            query["name"] = {"$regex": name, "$options": "i"}
        
        projection = build_safe_projection()
        
        try:
            collection = self.db["Resume"]
            user = await collection.find_one(query, projection)
            
            if user:
                job_selection = user.get("jobSelection", {})
                job_role_skills = user.get("jobRoleSkills", {})
                
                result = {
                    "name": user.get("name"),
                    "email": user.get("email"),
                    "selectedJobRole": job_selection.get("jobRole") or job_role_skills.get("role"),
                    "selectedDomain": job_selection.get("jobDomain") or job_role_skills.get("domain"),
                    "selectedSkills": job_selection.get("selectedSkills", []) or job_role_skills.get("current", []),
                    "skillsToLearn": job_selection.get("unselectedSkills", []) or job_role_skills.get("toLearn", []),
                }
                
                if result["selectedJobRole"] or result["selectedDomain"]:
                    return {k: v for k, v in result.items() if v}
                else:
                    return {"message": "No job role selected yet. The user should go to the Prediction page and select their target job role."}
            
            return {"message": "No profile found. The user should upload their resume first."}
            
        except Exception as e:
            logger.error(f"Job selection query error: {e}")
            return {"error": "Failed to query job selection"}


# ============================================
# Gemini Tool Definitions
# ============================================

# Define tools for Gemini function calling
TOOL_DEFINITIONS = [
    {
        "name": "get_user_profile",
        "description": "Get a user's profile information from the database. Use this when asked about a user's details, subscription, plan, or general information. Sensitive data like passwords and SSN are automatically filtered out.",
        "parameters": {
            "type": "object",
            "properties": {
                "email": {
                    "type": "string",
                    "description": "The user's email address to search for"
                },
                "name": {
                    "type": "string",
                    "description": "The user's name to search for"
                }
            },
            "required": []
        }
    },
    {
        "name": "get_user_skills",
        "description": "Get a user's technical and soft skills from their resume. Use this when asked about someone's skills, technologies they know, or programming languages.",
        "parameters": {
            "type": "object",
            "properties": {
                "email": {
                    "type": "string",
                    "description": "The user's email address"
                },
                "name": {
                    "type": "string",
                    "description": "The user's name"
                }
            },
            "required": []
        }
    },
    {
        "name": "get_user_education",
        "description": "Get a user's educational background including degree, university, and CGPA. Use this when asked about someone's education, college, or academic performance.",
        "parameters": {
            "type": "object",
            "properties": {
                "email": {
                    "type": "string",
                    "description": "The user's email address"
                },
                "name": {
                    "type": "string",
                    "description": "The user's name"
                }
            },
            "required": []
        }
    },
    {
        "name": "get_user_experience",
        "description": "Get a user's work experience, internships, and projects. Use this when asked about someone's work history, internships, or projects they've worked on.",
        "parameters": {
            "type": "object",
            "properties": {
                "email": {
                    "type": "string",
                    "description": "The user's email address"
                },
                "name": {
                    "type": "string",
                    "description": "The user's name"
                }
            },
            "required": []
        }
    },
    {
        "name": "get_placement_prediction",
        "description": "Get a user's complete placement prediction including all scores: placementScore, mlModelScore, skillScore, academicScore, projectScore, dsaScore, experienceScore, certificationScore, achievementScore, atsScore, and recommendations. Use this when asked about placement chances, prediction score, any specific score, score breakdown, how to improve scores, or career prospects.",
        "parameters": {
            "type": "object",
            "properties": {
                "email": {
                    "type": "string",
                    "description": "The user's email address"
                },
                "name": {
                    "type": "string",
                    "description": "The user's name"
                }
            },
            "required": []
        }
    },
    {
        "name": "get_user_job_selection",
        "description": "Get a user's selected job role, target domain, and skills they have or need to learn. Use this when asked about someone's job role, career target, selected domain, or what job they're aiming for.",
        "parameters": {
            "type": "object",
            "properties": {
                "email": {
                    "type": "string",
                    "description": "The user's email address"
                },
                "name": {
                    "type": "string",
                    "description": "The user's name"
                }
            },
            "required": []
        }
    }
]


# ============================================
# Gemini Chat Handler
# ============================================

class GeminiChatHandler:
    """Handles chat interactions with Gemini API using function calling"""
    
    def __init__(self, db_tools: DatabaseTools):
        self.db_tools = db_tools
        self.model = genai.GenerativeModel(
            model_name="gemini-2.5-flash-lite",
            system_instruction="""You are the Career Assistant for PlacementAI platform. You ONLY help with career-related topics.

=== PLACEMENTAI WEBSITE NAVIGATION ===
When users need to do something on the website, guide them with these steps:

TO GENERATE PLACEMENT PREDICTION SCORE:
1. Click on "Prediction" in the navigation menu
2. Fill in your academic details (10th %, 12th %, College CGPA)
3. Upload your resume (PDF/DOCX)
4. Select your target job domain and role
5. Choose the skills you have from the list
6. Click "Get Prediction" to see your placement score

TO UPLOAD/UPDATE RESUME:
1. Go to "Prediction" page
2. Click on "Upload Resume" section
3. Select your resume file (PDF or DOCX format)
4. The system will automatically parse your skills, education, and experience

TO VIEW DASHBOARD:
1. Click on "Dashboard" in the navigation menu
2. View your profile summary, skills analysis, and recommendations

TO SELECT JOB ROLE:
1. Go to "Prediction" page
2. In Step 2, select your target domain (e.g., Data Science, Web Development)
3. Choose your desired job role from the dropdown
4. Select the skills you already have

TO TAKE SKILL ASSESSMENT TEST:
1. Go to "Test" page from the navigation
2. Select the skill you want to be tested on
3. Complete the quiz to assess your knowledge

TO VIEW LEARNING ROADMAP:
1. Go to "Roadmap" page
2. View personalized learning paths based on your skill gaps

=== SCORES EXPLAINED ===
PlacementAI calculates multiple scores. Here's what each one means and how it's calculated:

**1. PLACEMENT SCORE (0-100)** - The main composite score predicting placement success
   - This is a weighted combination of all your profile factors:
   - WEIGHTS: Academics (20%) + Skills (32%) + Projects (25%) + DSA (10%) + Experience (8%) + Achievements & Certifications (10%)
   - Score >= 50 means "Eligible for Placement"
   - Score < 50 means "Needs Improvement" before placements

**2. ML MODEL SCORE (0-100%)** - Machine Learning model prediction
   - Calculated using a trained Stacking Classifier model
   - Based primarily on academic performance (10th %, 12th %, College CGPA)
   - This is shown as a confidence indicator, not directly weighted into placement score
   - Provides an AI-based prediction of placement probability

**3. PREDICTION CONFIDENCE (75-95%)** - How confident the ML model is
   - 95%: For extreme scores (above 80% or below 20%)
   - 85%: For good/low scores (60-80% or 20-40%)
   - 75%: For middle-range scores (40-60%)

**4. SKILL SCORE (0-100)** - How well your skills match the target job role
   - Base Coverage (0-50 pts): How many relevant skills you have
   - Skill Diversity (0-20 pts): Skills across multiple categories (Programming, Web, Data/ML, DevOps)
   - Skill Depth (0-20 pts): Quality from projects and certifications
   - Form Verification (0-10 pts): Skills backed by evidence in resume/projects
   - If ALL skills for a role are selected = 100% automatically

**5. ACADEMIC SCORE (0-100)** - Based on your academic performance
   - Calculated as: College CGPA * 10 (converted to percentage)
   - Example: CGPA 8.5 → Academic Score = 85
   - Contributes 20% to the final Placement Score

**6. PROJECT SCORE (0-100)** - Quality of your projects
   - Based on number of projects, technologies used, and complexity
   - Project depth: basic/intermediate/advanced based on tech stack
   - Strong projects with multiple technologies score higher
   - Contributes 25% to the final Placement Score

**7. DSA SCORE (0-100)** - Data Structures & Algorithms proficiency
   - Based on LeetCode/problem-solving performance
   - Easy problems: 1 point each
   - Medium problems: 2 points each
   - Hard problems: 5 points each
   - Capped at 100 points
   - Contributes 10% to the final Placement Score

**8. EXPERIENCE SCORE (0-10)** - Work experience and internships
   - Based on internships, hackathons, work experience
   - More relevant experience = higher score
   - Contributes 8% to the final Placement Score

**9. CERTIFICATION SCORE** - Based on certifications you have
   - Relevant industry certifications add points
   - Part of the 10% Achievements & Certifications weight

**10. ACHIEVEMENT SCORE** - Based on achievements and awards
   - Hackathon wins, scholarships, coding competition ranks
   - Part of the 10% Achievements & Certifications weight

**11. ATS SCORE (0-100)** - Resume optimization score (Applicant Tracking System)
   - Contact Info (5 pts): Email, phone, name present
   - Education (15 pts): Degree, university, CGPA details
   - Experience (20 pts): Internships, action verbs, work history
   - Skills (25 pts): Technical and soft skills - MOST IMPORTANT
   - Keywords (5 pts): Industry-relevant terms
   - Projects (15 pts): Project descriptions with metrics
   - Achievements (5 pts): Awards and certifications
   - Format (5 pts): Proper resume structure
   - Spelling/Grammar (5 pts): Error-free content
   - Ratings: Excellent (88+), Good (72+), Fair (55+), Needs Improvement (<55)

=== HOW TO IMPROVE SCORES ===
- Low Placement Score: Focus on the category with lowest contribution (check scoreBreakdown)
- Low Skill Score: Add more relevant skills and demonstrate them in projects
- Low Project Score: Add more projects with clear tech stack and measurable outcomes
- Low DSA Score: Practice more problems on LeetCode (medium and hard for bonus)
- Low ATS Score: Use action verbs, add metrics, include keywords from job descriptions
- Low Academic Score: This is fixed, but you can compensate with strong skills and projects

=== ALLOWED TOPICS ===
- Career guidance and planning
- Resume building and optimization
- Interview preparation and tips
- Skills assessment and improvement
- Placement predictions and scores
- Education and academic advice
- Job search strategies
- Professional development
- Technical skills for jobs
- Internship guidance
- Website navigation help
- Score explanations and improvement tips

=== FORBIDDEN TOPICS (politely decline) ===
Games, vacations, movies, sports, cooking, relationships, politics, religion, or anything unrelated to careers.

If asked about forbidden topics, say:
"I'm your Career Assistant and I can only help with career-related topics. How can I assist you with your career today?"

=== USER CONTEXT ===
Every message includes: [Current logged-in user: Name: <name>, Email: <email>]

=== AUTO-FETCH DATA ===
When user asks about "my" anything, IMMEDIATELY use the appropriate tool:
- "What are my skills?" → get_user_skills
- "Analyze my profile" → get_user_profile  
- "Show my education" → get_user_education
- "What's my placement score?" → get_placement_prediction
- "My experience" → get_user_experience
- "My job role / selected role" → get_user_job_selection
- "Resume tips" → Fetch profile first
- "What's my ATS score?" → get_user_profile (atsScore is stored in Resume)
- "How are scores calculated?" → Explain from SCORES EXPLAINED section

=== HANDLING MISSING DATA ===
If data is not found, provide helpful navigation:
- No placement score → Guide them to Prediction page to generate it
- No job role selected → Guide them to select job role in Prediction page
- No resume → Guide them to upload resume in Prediction page
- No skills → Guide them to complete their profile

Be helpful, professional, and always provide actionable next steps. When explaining scores, be specific about what each one means and how to improve it."""
        )
        
        # Convert tool definitions to Gemini format
        self.tools = self._create_gemini_tools()
        
        # Store conversation history per session
        self.conversations: Dict[str, List] = {}
        
        # Store user context per session (email, name, phone)
        self.user_contexts: Dict[str, Dict] = {}
    
    def _create_gemini_tools(self):
        """Create Gemini-compatible tool definitions"""
        from google.generativeai.types import FunctionDeclaration, Tool
        
        function_declarations = []
        for tool_def in TOOL_DEFINITIONS:
            func_decl = FunctionDeclaration(
                name=tool_def["name"],
                description=tool_def["description"],
                parameters=tool_def["parameters"]
            )
            function_declarations.append(func_decl)
        
        return [Tool(function_declarations=function_declarations)]
    
    async def execute_tool(self, function_name: str, args: Dict) -> Dict:
        """Execute a tool function and return sanitized results"""
        tool_map = {
            "get_user_profile": self.db_tools.get_user_profile,
            "get_user_skills": self.db_tools.get_user_skills,
            "get_user_education": self.db_tools.get_user_education,
            "get_user_experience": self.db_tools.get_user_experience,
            "get_placement_prediction": self.db_tools.get_placement_prediction,
            "get_user_job_selection": self.db_tools.get_user_job_selection,
        }
        
        if function_name not in tool_map:
            return {"error": f"Unknown tool: {function_name}"}
        
        logger.info(f"Executing tool: {function_name} with args: {args}")
        result = await tool_map[function_name](**args)
        logger.info(f"Tool result keys: {list(result.keys()) if isinstance(result, dict) else 'N/A'}")
        
        return result
    
    async def chat(self, session_id: str, user_message: str, user_context: Optional[Dict] = None) -> str:
        """
        Process a chat message with function calling support.
        
        Args:
            session_id: Unique session identifier for conversation history
            user_message: The user's message
            user_context: Optional dict with user's email, name, phone
            
        Returns:
            The assistant's response
        """
        try:
            # Store user context for this session if provided
            if user_context:
                self.user_contexts[session_id] = user_context
            
            # Get or create conversation history
            if session_id not in self.conversations:
                self.conversations[session_id] = []
            
            history = self.conversations[session_id]
            
            # Create chat session
            chat = self.model.start_chat(history=history)
            
            # Prepend user context to the message so the AI knows who is asking
            enhanced_message = user_message
            if session_id in self.user_contexts:
                ctx = self.user_contexts[session_id]
                user_info_parts = []
                if ctx.get('name'):
                    user_info_parts.append(f"Name: {ctx['name']}")
                if ctx.get('email'):
                    user_info_parts.append(f"Email: {ctx['email']}")
                if user_info_parts:
                    enhanced_message = f"[Current logged-in user: {', '.join(user_info_parts)}]\n\n{user_message}"
                    logger.info(f"Enhanced message with user context: {user_info_parts}")
            
            # Send message with tools
            response = chat.send_message(
                enhanced_message,
                tools=self.tools
            )
            
            # Check if the model wants to call a function
            while response.candidates[0].content.parts:
                part = response.candidates[0].content.parts[0]
                
                # Check for function call
                if hasattr(part, 'function_call') and part.function_call:
                    function_call = part.function_call
                    function_name = function_call.name
                    function_args = dict(function_call.args)
                    
                    logger.info(f"Function call requested: {function_name}")
                    
                    # Auto-fill user email/name from session context if not provided in args
                    if session_id in self.user_contexts:
                        ctx = self.user_contexts[session_id]
                        if not function_args.get('email') and ctx.get('email'):
                            function_args['email'] = ctx['email']
                        if not function_args.get('name') and ctx.get('name'):
                            function_args['name'] = ctx['name']
                        logger.info(f"Using user context - email: {function_args.get('email')}, name: {function_args.get('name')}")
                    
                    # Execute the tool
                    tool_result = await self.execute_tool(function_name, function_args)
                    
                    # Send function result back to Gemini using protos
                    from google.generativeai import protos
                    
                    function_response = protos.Part(
                        function_response=protos.FunctionResponse(
                            name=function_name,
                            response={"result": json.dumps(tool_result, default=str)}
                        )
                    )
                    
                    response = chat.send_message(function_response)
                else:
                    # No more function calls, we have the final response
                    break
            
            # Extract text response - filter out any raw function response data
            final_response = ""
            if hasattr(response, 'text'):
                final_response = response.text
            else:
                # Try to extract text from parts
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'text') and part.text:
                        final_response += part.text
            
            # Clean up any leaked function response data from the text
            # Remove patterns like {"get_user_*_response": ...}
            final_response = re.sub(r'\{"get_user_\w+_response":\s*\{[^}]*\}[^}]*\}\s*', '', final_response)
            # Remove any JSON-like function response patterns
            final_response = re.sub(r'\{"result":\s*"[^"]*"\}\s*', '', final_response)
            # Clean up extra whitespace
            final_response = final_response.strip()
            
            # Update conversation history
            self.conversations[session_id] = chat.history
            
            return final_response
            
        except Exception as e:
            logger.error(f"Chat error: {e}", exc_info=True)
            return f"I apologize, but I encountered an error processing your request. Please try again."


# ============================================
# FastAPI Application
# ============================================

# Global instances
db_client: Optional[AsyncIOMotorClient] = None
db_tools: Optional[DatabaseTools] = None
chat_handler: Optional[GeminiChatHandler] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown"""
    global db_client, db_tools, chat_handler
    
    # Startup
    logger.info("Starting Chatbot API...")
    
    # Retry connection logic for MongoDB Atlas
    max_retries = 3
    retry_delay = 5  # seconds
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Attempting MongoDB connection (attempt {attempt + 1}/{max_retries})...")
            
            # Connect to MongoDB with connection pool settings for reliability
            db_client = AsyncIOMotorClient(
                MONGODB_URI,
                serverSelectionTimeoutMS=30000,  # 30 second timeout for server selection (Atlas needs more time)
                connectTimeoutMS=30000,  # 30 second connection timeout
                socketTimeoutMS=60000,  # 60 second socket timeout
                maxPoolSize=10,  # Maximum connection pool size
                minPoolSize=1,  # Minimum connections to keep alive
                maxIdleTimeMS=45000,  # Close idle connections after 45 seconds
                retryWrites=True,  # Retry failed writes
                retryReads=True,  # Retry failed reads
            )
            db = db_client[MONGODB_DB]
            
            # Test connection
            await db.command("ping")
            logger.info(f"✅ Connected to MongoDB: {MONGODB_DB}")
            
            # Initialize tools and handler
            db_tools = DatabaseTools(db)
            chat_handler = GeminiChatHandler(db_tools)
            logger.info("✅ Chatbot handler initialized")
            break  # Success, exit retry loop
            
        except Exception as e:
            logger.warning(f"⚠️ MongoDB connection attempt {attempt + 1} failed: {e}")
            if db_client:
                db_client.close()
                db_client = None
            
            if attempt < max_retries - 1:
                logger.info(f"Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                logger.error(f"❌ Failed to connect to MongoDB after {max_retries} attempts")
                raise
    
    yield
    
    # Shutdown
    if db_client:
        db_client.close()
        logger.info("MongoDB connection closed")


# Create FastAPI app
app = FastAPI(
    title="PlacementAI Chatbot API",
    description="Secure chatbot backend with PII filtering",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================
# Pydantic Models
# ============================================

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000, description="User's message")
    session_id: Optional[str] = Field(None, description="Session ID for conversation history")
    user_email: Optional[str] = Field(None, description="Logged-in user's email")
    user_name: Optional[str] = Field(None, description="Logged-in user's name")
    user_phone: Optional[str] = Field(None, description="Logged-in user's phone number")


class ChatResponse(BaseModel):
    response: str
    session_id: str
    timestamp: str


class HealthResponse(BaseModel):
    status: str
    database: str
    gemini: str


# ============================================
# API Endpoints
# ============================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint with connection validation"""
    global db_client, db_tools, chat_handler
    
    db_status = "disconnected"
    gemini_status = "configured" if GEMINI_API_KEY else "not configured"
    
    # Actually test MongoDB connection
    if db_client:
        try:
            await db_client[MONGODB_DB].command("ping")
            db_status = "connected"
        except Exception as e:
            logger.warning(f"MongoDB ping failed, attempting reconnection: {e}")
            # Attempt to reconnect
            try:
                db_client = AsyncIOMotorClient(
                    MONGODB_URI,
                    serverSelectionTimeoutMS=5000,
                    connectTimeoutMS=10000,
                    socketTimeoutMS=30000,
                    maxPoolSize=10,
                    minPoolSize=1,
                    maxIdleTimeMS=45000,
                    retryWrites=True,
                    retryReads=True,
                )
                db = db_client[MONGODB_DB]
                await db.command("ping")
                db_tools = DatabaseTools(db)
                chat_handler = GeminiChatHandler(db_tools)
                db_status = "reconnected"
                logger.info("✅ MongoDB reconnected successfully")
            except Exception as reconnect_error:
                logger.error(f"❌ MongoDB reconnection failed: {reconnect_error}")
                db_status = "disconnected"
    
    return HealthResponse(
        status="healthy" if db_status in ["connected", "reconnected"] else "degraded",
        database=db_status,
        gemini=gemini_status
    )


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Main chat endpoint.
    
    Receives user message, processes with Gemini (including tool calls),
    and returns the response with sanitized data.
    """
    if not chat_handler:
        raise HTTPException(status_code=503, detail="Chatbot not initialized")
    
    # Generate session ID if not provided
    session_id = request.session_id or f"session_{datetime.now().timestamp()}"
    
    # Build user context from request
    user_context = None
    if request.user_email or request.user_name or request.user_phone:
        user_context = {
            "email": request.user_email,
            "name": request.user_name,
            "phone": request.user_phone
        }
        logger.info(f"User context for session {session_id}: email={request.user_email}, name={request.user_name}")
    
    try:
        # Process chat message with user context
        response = await chat_handler.chat(session_id, request.message, user_context)
        
        return ChatResponse(
            response=response,
            session_id=session_id,
            timestamp=datetime.now().isoformat()
        )
        
    except Exception as e:
        logger.error(f"Chat endpoint error: {e}")
        raise HTTPException(status_code=500, detail="Failed to process chat message")


@app.post("/chat/clear")
async def clear_conversation(session_id: str):
    """Clear conversation history for a session"""
    if chat_handler and session_id in chat_handler.conversations:
        del chat_handler.conversations[session_id]
        return {"message": "Conversation cleared", "session_id": session_id}
    
    return {"message": "No conversation found", "session_id": session_id}


# ============================================
# Run the application
# ============================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=5001,
        timeout_keep_alive=120,  # Keep connections alive for 120 seconds
        log_level="info"
    )
