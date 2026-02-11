"""
Script to populate MongoDB with interactive loading questions and facts
Run this script once to initialize the loading_questions collection
"""
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

from utils.db import get_db
from datetime import datetime
import sys

def populate_loading_questions():
    """Populate the database with interactive questions for loading screens"""
    
    db = get_db()
    questions_collection = db['loading_questions']
    
    # Clear existing data (optional - comment out if you want to keep existing data)
    questions_collection.delete_many({})
    
    questions = [
        # Lifestyle & Preferences
        {
            "question_id": "coffee_preference",
            "category": "lifestyle",
            "question_text": "What's your go-to coffee order?",
            "question_type": "single_choice",
            "icon_emoji": "☕",
            "options": [
                {"option_id": "espresso", "text": "Espresso", "icon": "☕", "coupon_category": "coffee_shops"},
                {"option_id": "cappuccino", "text": "Cappuccino", "icon": "🥛", "coupon_category": "coffee_shops"},
                {"option_id": "cold_brew", "text": "Cold Brew", "icon": "🧊", "coupon_category": "coffee_shops"},
                {"option_id": "latte", "text": "Latte", "icon": "❤️", "coupon_category": "coffee_shops"},
                {"option_id": "tea", "text": "Tea Instead", "icon": "🍵", "coupon_category": "tea_shops"}
            ],
            "display_contexts": ["registration_loading", "quiz_submission", "profile_update", "resume_analysis"],
            "weight": 10,
            "active": True,
            "created_at": datetime.utcnow()
        },
        {
            "question_id": "work_environment",
            "category": "lifestyle",
            "question_text": "Where do you code best?",
            "question_type": "single_choice",
            "icon_emoji": "💻",
            "options": [
                {"option_id": "coffee_shop", "text": "Coffee Shop", "icon": "☕", "coupon_category": "coffee_shops"},
                {"option_id": "home_office", "text": "Home Office", "icon": "🏠", "coupon_category": "home_office"},
                {"option_id": "coworking", "text": "Co-working Space", "icon": "💼", "coupon_category": "coworking"},
                {"option_id": "outdoor", "text": "Outdoor", "icon": "🌳", "coupon_category": "outdoor"},
                {"option_id": "late_night", "text": "Late Night", "icon": "🌙", "coupon_category": "food_delivery"}
            ],
            "display_contexts": ["registration_loading", "profile_update"],
            "weight": 8,
            "active": True,
            "created_at": datetime.utcnow()
        },
        {
            "question_id": "music_while_working",
            "category": "lifestyle",
            "question_text": "Your productivity soundtrack?",
            "question_type": "single_choice",
            "icon_emoji": "🎵",
            "options": [
                {"option_id": "lofi", "text": "Lo-fi Beats", "icon": "🎵", "coupon_category": "music_streaming"},
                {"option_id": "classical", "text": "Classical", "icon": "🎻", "coupon_category": "music_streaming"},
                {"option_id": "silence", "text": "Silence", "icon": "🔇", "coupon_category": "productivity_tools"},
                {"option_id": "podcast", "text": "Podcast", "icon": "🎙️", "coupon_category": "podcast_platforms"},
                {"option_id": "rock", "text": "Rock/Metal", "icon": "🎸", "coupon_category": "music_streaming"}
            ],
            "display_contexts": ["quiz_submission", "profile_update"],
            "weight": 7,
            "active": True,
            "created_at": datetime.utcnow()
        },
        {
            "question_id": "snack_preference",
            "category": "lifestyle",
            "question_text": "Fuel for your coding sessions?",
            "question_type": "single_choice",
            "icon_emoji": "🍕",
            "options": [
                {"option_id": "pizza", "text": "Pizza", "icon": "🍕", "coupon_category": "food_delivery"},
                {"option_id": "energy_drinks", "text": "Energy Drinks", "icon": "⚡", "coupon_category": "beverages"},
                {"option_id": "fruits", "text": "Fruits", "icon": "🍎", "coupon_category": "health_food"},
                {"option_id": "chips", "text": "Chips", "icon": "🥨", "coupon_category": "snacks"},
                {"option_id": "chocolate", "text": "Chocolate", "icon": "🍫", "coupon_category": "snacks"}
            ],
            "display_contexts": ["registration_loading", "resume_analysis"],
            "weight": 9,
            "active": True,
            "created_at": datetime.utcnow()
        },
        
        # Career & Learning
        {
            "question_id": "tech_stack_interest",
            "category": "career",
            "question_text": "Which tech excites you most?",
            "question_type": "single_choice",
            "icon_emoji": "🤖",
            "options": [
                {"option_id": "ai_ml", "text": "AI/ML", "icon": "🤖", "coupon_category": "online_courses"},
                {"option_id": "web_dev", "text": "Web Dev", "icon": "🌐", "coupon_category": "online_courses"},
                {"option_id": "mobile", "text": "Mobile", "icon": "📱", "coupon_category": "online_courses"},
                {"option_id": "cloud", "text": "Cloud", "icon": "☁️", "coupon_category": "online_courses"},
                {"option_id": "blockchain", "text": "Blockchain", "icon": "⛓️", "coupon_category": "online_courses"}
            ],
            "display_contexts": ["registration_loading", "quiz_submission", "profile_update"],
            "weight": 10,
            "active": True,
            "created_at": datetime.utcnow()
        },
        {
            "question_id": "learning_style",
            "category": "career",
            "question_text": "How do you learn best?",
            "question_type": "single_choice",
            "icon_emoji": "📚",
            "options": [
                {"option_id": "video_tutorials", "text": "Video Tutorials", "icon": "📹", "coupon_category": "online_courses"},
                {"option_id": "reading_docs", "text": "Reading Docs", "icon": "📚", "coupon_category": "books"},
                {"option_id": "hands_on", "text": "Hands-on Projects", "icon": "💻", "coupon_category": "online_courses"},
                {"option_id": "bootcamps", "text": "Bootcamps", "icon": "🎓", "coupon_category": "bootcamps"},
                {"option_id": "mentorship", "text": "Mentorship", "icon": "👥", "coupon_category": "mentorship"}
            ],
            "display_contexts": ["registration_loading", "profile_update"],
            "weight": 9,
            "active": True,
            "created_at": datetime.utcnow()
        },
        {
            "question_id": "dream_company_type",
            "category": "career",
            "question_text": "Your ideal workplace?",
            "question_type": "single_choice",
            "icon_emoji": "🚀",
            "options": [
                {"option_id": "startup", "text": "Startup", "icon": "🚀", "coupon_category": "general"},
                {"option_id": "tech_giant", "text": "Tech Giant", "icon": "🏢", "coupon_category": "general"},
                {"option_id": "remote_first", "text": "Remote-First", "icon": "🌍", "coupon_category": "remote_tools"},
                {"option_id": "product_company", "text": "Product Company", "icon": "📦", "coupon_category": "general"},
                {"option_id": "service_company", "text": "Service Company", "icon": "🔧", "coupon_category": "general"}
            ],
            "display_contexts": ["registration_loading", "quiz_submission"],
            "weight": 8,
            "active": True,
            "created_at": datetime.utcnow()
        },
        {
            "question_id": "career_goal_timeline",
            "category": "career",
            "question_text": "When do you want your dream job?",
            "question_type": "single_choice",
            "icon_emoji": "🎯",
            "options": [
                {"option_id": "three_months", "text": "3 Months", "icon": "⚡", "coupon_category": "interview_prep"},
                {"option_id": "six_months", "text": "6 Months", "icon": "📅", "coupon_category": "interview_prep"},
                {"option_id": "one_year", "text": "1 Year", "icon": "🎯", "coupon_category": "online_courses"},
                {"option_id": "exploring", "text": "Still Exploring", "icon": "🔍", "coupon_category": "career_counseling"},
                {"option_id": "already_there", "text": "Already There", "icon": "🎉", "coupon_category": "upskilling"}
            ],
            "display_contexts": ["registration_loading"],
            "weight": 10,
            "active": True,
            "created_at": datetime.utcnow()
        },
        
        # Personality & Habits
        {
            "question_id": "productivity_time",
            "category": "personality",
            "question_text": "When are you most productive?",
            "question_type": "single_choice",
            "icon_emoji": "⏰",
            "options": [
                {"option_id": "early_bird", "text": "Early Bird", "icon": "🌅", "coupon_category": "morning_cafes"},
                {"option_id": "night_owl", "text": "Night Owl", "icon": "🦉", "coupon_category": "food_delivery"},
                {"option_id": "afternoon", "text": "Afternoon Person", "icon": "🌤️", "coupon_category": "general"},
                {"option_id": "anytime", "text": "Anytime", "icon": "⏰", "coupon_category": "general"},
                {"option_id": "varies", "text": "It Varies", "icon": "🔄", "coupon_category": "general"}
            ],
            "display_contexts": ["profile_update", "quiz_submission"],
            "weight": 7,
            "active": True,
            "created_at": datetime.utcnow()
        },
        {
            "question_id": "stress_buster",
            "category": "personality",
            "question_text": "How do you unwind?",
            "question_type": "single_choice",
            "icon_emoji": "😌",
            "options": [
                {"option_id": "gaming", "text": "Gaming", "icon": "🎮", "coupon_category": "gaming"},
                {"option_id": "exercise", "text": "Exercise", "icon": "🏃", "coupon_category": "fitness"},
                {"option_id": "netflix", "text": "Netflix", "icon": "📺", "coupon_category": "streaming"},
                {"option_id": "reading", "text": "Reading", "icon": "📖", "coupon_category": "books"},
                {"option_id": "cooking", "text": "Cooking", "icon": "🍳", "coupon_category": "cooking_classes"}
            ],
            "display_contexts": ["resume_analysis", "profile_update"],
            "weight": 8,
            "active": True,
            "created_at": datetime.utcnow()
        },
        {
            "question_id": "weekend_vibe",
            "category": "personality",
            "question_text": "Perfect weekend activity?",
            "question_type": "single_choice",
            "icon_emoji": "🎉",
            "options": [
                {"option_id": "side_projects", "text": "Coding Side Projects", "icon": "💻", "coupon_category": "online_courses"},
                {"option_id": "outdoor_adventure", "text": "Outdoor Adventure", "icon": "🏔️", "coupon_category": "travel"},
                {"option_id": "social_hangouts", "text": "Social Hangouts", "icon": "🎉", "coupon_category": "entertainment"},
                {"option_id": "sleep_relax", "text": "Sleep & Relax", "icon": "😴", "coupon_category": "wellness"},
                {"option_id": "learning", "text": "Learning New Skills", "icon": "📚", "coupon_category": "online_courses"}
            ],
            "display_contexts": ["profile_update"],
            "weight": 6,
            "active": True,
            "created_at": datetime.utcnow()
        },
        
        # Tech & Tools
        {
            "question_id": "ide_preference",
            "category": "tech",
            "question_text": "Your coding weapon of choice?",
            "question_type": "single_choice",
            "icon_emoji": "💻",
            "options": [
                {"option_id": "vscode", "text": "VS Code", "icon": "💙", "coupon_category": "productivity_tools"},
                {"option_id": "intellij", "text": "IntelliJ", "icon": "🧠", "coupon_category": "productivity_tools"},
                {"option_id": "vim_emacs", "text": "Vim/Emacs", "icon": "⌨️", "coupon_category": "productivity_tools"},
                {"option_id": "sublime", "text": "Sublime", "icon": "💜", "coupon_category": "productivity_tools"},
                {"option_id": "pycharm", "text": "PyCharm", "icon": "🐍", "coupon_category": "productivity_tools"}
            ],
            "display_contexts": ["registration_loading", "quiz_submission"],
            "weight": 7,
            "active": True,
            "created_at": datetime.utcnow()
        },
        {
            "question_id": "os_preference",
            "category": "tech",
            "question_text": "Your operating system?",
            "question_type": "single_choice",
            "icon_emoji": "💻",
            "options": [
                {"option_id": "windows", "text": "Windows", "icon": "🪟", "coupon_category": "software"},
                {"option_id": "macos", "text": "macOS", "icon": "🍎", "coupon_category": "software"},
                {"option_id": "linux", "text": "Linux", "icon": "🐧", "coupon_category": "software"},
                {"option_id": "dual_boot", "text": "Dual Boot", "icon": "⚡", "coupon_category": "software"},
                {"option_id": "cloud", "text": "Cloud-based", "icon": "☁️", "coupon_category": "cloud_services"}
            ],
            "display_contexts": ["quiz_submission"],
            "weight": 5,
            "active": True,
            "created_at": datetime.utcnow()
        },
        {
            "question_id": "debugging_style",
            "category": "tech",
            "question_text": "How do you debug?",
            "question_type": "single_choice",
            "icon_emoji": "🐛",
            "options": [
                {"option_id": "print_statements", "text": "Print Statements", "icon": "📝", "coupon_category": "general"},
                {"option_id": "debugger_tool", "text": "Debugger Tool", "icon": "🔍", "coupon_category": "productivity_tools"},
                {"option_id": "google", "text": "Google/Stack Overflow", "icon": "🔎", "coupon_category": "general"},
                {"option_id": "rubber_duck", "text": "Rubber Duck", "icon": "🦆", "coupon_category": "general"},
                {"option_id": "ask_ai", "text": "Ask AI", "icon": "🤖", "coupon_category": "ai_tools"}
            ],
            "display_contexts": ["quiz_submission", "resume_analysis"],
            "weight": 8,
            "active": True,
            "created_at": datetime.utcnow()
        },
        
        # Fun & Engagement
        {
            "question_id": "coding_superpower",
            "category": "fun",
            "question_text": "If you had a coding superpower?",
            "question_type": "single_choice",
            "icon_emoji": "⚡",
            "options": [
                {"option_id": "bug_free", "text": "Write Bug-free Code", "icon": "🐛❌", "coupon_category": "general"},
                {"option_id": "instant_learning", "text": "Instant Learning", "icon": "🧠⚡", "coupon_category": "online_courses"},
                {"option_id": "read_docs", "text": "Read Docs Instantly", "icon": "📚", "coupon_category": "general"},
                {"option_id": "telepathic_debug", "text": "Debug Telepathically", "icon": "🔮", "coupon_category": "general"},
                {"option_id": "light_speed", "text": "Code at Light Speed", "icon": "⚡", "coupon_category": "general"}
            ],
            "display_contexts": ["registration_loading", "quiz_submission", "profile_update"],
            "weight": 9,
            "active": True,
            "created_at": datetime.utcnow()
        },
        {
            "question_id": "interview_format",
            "category": "fun",
            "question_text": "Preferred interview format?",
            "question_type": "single_choice",
            "icon_emoji": "💼",
            "options": [
                {"option_id": "live_coding", "text": "Live Coding", "icon": "💻", "coupon_category": "interview_prep"},
                {"option_id": "take_home", "text": "Take-home Project", "icon": "🏠", "coupon_category": "interview_prep"},
                {"option_id": "system_design", "text": "System Design", "icon": "🏗️", "coupon_category": "interview_prep"},
                {"option_id": "behavioral", "text": "Behavioral Only", "icon": "💬", "coupon_category": "interview_prep"},
                {"option_id": "no_preference", "text": "No Preference", "icon": "🤷", "coupon_category": "general"}
            ],
            "display_contexts": ["registration_loading"],
            "weight": 7,
            "active": True,
            "created_at": datetime.utcnow()
        },
        {
            "question_id": "collaboration_tool",
            "category": "tech",
            "question_text": "Team communication preference?",
            "question_type": "single_choice",
            "icon_emoji": "💬",
            "options": [
                {"option_id": "slack", "text": "Slack", "icon": "💬", "coupon_category": "productivity_tools"},
                {"option_id": "discord", "text": "Discord", "icon": "🎮", "coupon_category": "productivity_tools"},
                {"option_id": "teams", "text": "Microsoft Teams", "icon": "💼", "coupon_category": "productivity_tools"},
                {"option_id": "email", "text": "Email", "icon": "📧", "coupon_category": "general"},
                {"option_id": "in_person", "text": "In-person", "icon": "👥", "coupon_category": "general"}
            ],
            "display_contexts": ["profile_update"],
            "weight": 6,
            "active": True,
            "created_at": datetime.utcnow()
        }
    ]
    
    # Insert all questions
    result = questions_collection.insert_many(questions)
    print(f"✅ Inserted {len(result.inserted_ids)} questions successfully!")
    
    return len(result.inserted_ids)


def populate_loading_facts():
    """Populate the database with motivational facts for loading screens"""
    
    db = get_db()
    facts_collection = db['loading_facts']
    
    # Clear existing data (optional)
    facts_collection.delete_many({})
    
    facts = [
        {
            "fact_id": "fact_001",
            "category": "tech_history",
            "fact_text": "💡 Did you know? The first computer bug was an actual moth found in a computer in 1947!",
            "icon": "💡",
            "display_contexts": ["all"],
            "weight": 8,
            "active": True,
            "created_at": datetime.utcnow()
        },
        {
            "fact_id": "fact_002",
            "category": "career_motivation",
            "fact_text": "🚀 Fact: The average developer codes 10-20 hours a week. You're building your future!",
            "icon": "🚀",
            "display_contexts": ["all"],
            "weight": 9,
            "active": True,
            "created_at": datetime.utcnow()
        },
        {
            "fact_id": "fact_003",
            "category": "industry_insights",
            "fact_text": "📊 92% of employers value problem-solving skills over specific programming languages.",
            "icon": "📊",
            "display_contexts": ["all"],
            "weight": 10,
            "active": True,
            "created_at": datetime.utcnow()
        },
        {
            "fact_id": "fact_004",
            "category": "tech_trivia",
            "fact_text": "⏰ Fun fact: Most developers spend 75% of their time reading code, not writing it!",
            "icon": "⏰",
            "display_contexts": ["all"],
            "weight": 7,
            "active": True,
            "created_at": datetime.utcnow()
        },
        {
            "fact_id": "fact_005",
            "category": "success_tips",
            "fact_text": "🎯 Success tip: Consistency beats intensity. Code a little every day!",
            "icon": "🎯",
            "display_contexts": ["all"],
            "weight": 10,
            "active": True,
            "created_at": datetime.utcnow()
        },
        {
            "fact_id": "fact_006",
            "category": "industry_insights",
            "fact_text": "💼 Industry insight: Soft skills get you hired, hard skills get you promoted!",
            "icon": "💼",
            "display_contexts": ["all"],
            "weight": 9,
            "active": True,
            "created_at": datetime.utcnow()
        },
        {
            "fact_id": "fact_007",
            "category": "productivity",
            "fact_text": "🧠 Did you know? Taking breaks actually improves coding productivity by 30%!",
            "icon": "🧠",
            "display_contexts": ["all"],
            "weight": 8,
            "active": True,
            "created_at": datetime.utcnow()
        },
        {
            "fact_id": "fact_008",
            "category": "motivation",
            "fact_text": "⚡ Quick fact: Your next breakthrough is just one more attempt away!",
            "icon": "⚡",
            "display_contexts": ["all"],
            "weight": 10,
            "active": True,
            "created_at": datetime.utcnow()
        },
        {
            "fact_id": "fact_009",
            "category": "tech_history",
            "fact_text": "🎮 The first video game programmer was a woman - Ada Lovelace in 1843!",
            "icon": "🎮",
            "display_contexts": ["all"],
            "weight": 7,
            "active": True,
            "created_at": datetime.utcnow()
        },
        {
            "fact_id": "fact_010",
            "category": "career_tips",
            "fact_text": "💪 80% of developers are self-taught. You're on the right path!",
            "icon": "💪",
            "display_contexts": ["all"],
            "weight": 9,
            "active": True,
            "created_at": datetime.utcnow()
        },
        {
            "fact_id": "fact_011",
            "category": "tech_trivia",
            "fact_text": "🌐 The first website ever created is still online at info.cern.ch!",
            "icon": "🌐",
            "display_contexts": ["all"],
            "weight": 6,
            "active": True,
            "created_at": datetime.utcnow()
        },
        {
            "fact_id": "fact_012",
            "category": "productivity",
            "fact_text": "⌨️ Average typing speed of developers: 40-60 WPM. Accuracy matters more than speed!",
            "icon": "⌨️",
            "display_contexts": ["all"],
            "weight": 5,
            "active": True,
            "created_at": datetime.utcnow()
        },
        {
            "fact_id": "fact_013",
            "category": "success_tips",
            "fact_text": "🔥 GitHub shows employers you code. Make at least 1 commit today!",
            "icon": "🔥",
            "display_contexts": ["all"],
            "weight": 8,
            "active": True,
            "created_at": datetime.utcnow()
        },
        {
            "fact_id": "fact_014",
            "category": "industry_insights",
            "fact_text": "💰 Remote developers earn 20-30% more on average. Location flexibility pays!",
            "icon": "💰",
            "display_contexts": ["all"],
            "weight": 7,
            "active": True,
            "created_at": datetime.utcnow()
        },
        {
            "fact_id": "fact_015",
            "category": "motivation",
            "fact_text": "🌟 Every expert was once a beginner. Keep pushing forward!",
            "icon": "🌟",
            "display_contexts": ["all"],
            "weight": 10,
            "active": True,
            "created_at": datetime.utcnow()
        }
    ]
    
    # Insert all facts
    result = facts_collection.insert_many(facts)
    print(f"✅ Inserted {len(result.inserted_ids)} facts successfully!")
    
    return len(result.inserted_ids)


def create_user_responses_collection():
    """Create collection for storing user responses to questions"""
    
    db = get_db()
    responses_collection = db['loading_question_responses']
    
    # Create indexes for better query performance
    responses_collection.create_index([("user_id", 1), ("question_id", 1)])
    responses_collection.create_index([("timestamp", -1)])
    
    print("✅ Created loading_question_responses collection with indexes!")


if __name__ == "__main__":
    print("🚀 Starting MongoDB population for loading questions...")
    print("-" * 60)
    
    try:
        # Populate questions
        print("\n📝 Populating questions...")
        questions_count = populate_loading_questions()
        
        # Populate facts
        print("\n💡 Populating facts...")
        facts_count = populate_loading_facts()
        
        # Create responses collection
        print("\n📊 Setting up responses collection...")
        create_user_responses_collection()
        
        print("\n" + "=" * 60)
        print("✅ SUCCESS! Database populated successfully!")
        print(f"   - {questions_count} questions added")
        print(f"   - {facts_count} facts added")
        print(f"   - User responses collection ready")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
