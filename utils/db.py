"""MongoDB helpers for saving parsed resumes.

Environment variables:
  - MONGODB_URI: your Atlas connection string
  - MONGODB_DB: database name (default: placement_db)
"""
from __future__ import annotations
import os
import time
from datetime import datetime
from typing import Any, Dict, Optional

from pymongo import MongoClient, ReturnDocument
from pymongo.errors import ServerSelectionTimeoutError, ConnectionFailure
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_client: Optional[MongoClient] = None
_connection_attempts = 0
_max_retries = 3
_retry_delay = 1  # seconds


def get_db():
    """
    Get database connection with retry logic and connection validation
    """
    global _client, _connection_attempts
    
    # Check if existing client is still connected
    if _client is not None:
        try:
            # Ping to verify connection is alive
            _client.admin.command('ismaster')
            dbname = os.environ.get("MONGODB_DB", "placement_db")
            return _client[dbname]
        except Exception:
            logger.warning("Existing MongoDB connection is stale, reconnecting...")
            _client = None
    
    # Attempt to establish new connection with retries
    uri = os.environ.get("MONGODB_URI")
    if not uri:
        # Use local MongoDB as fallback
        uri = "mongodb://localhost:27017"
        logger.info("Using local MongoDB at localhost:27017")
    
    for attempt in range(_max_retries):
        try:
            _connection_attempts = attempt + 1
            logger.info(f"Attempting MongoDB connection (attempt {_connection_attempts}/{_max_retries})...")
            
            _client = MongoClient(
                uri,
                serverSelectionTimeoutMS=5000,  # 5 second timeout
                connectTimeoutMS=10000,  # 10 second connection timeout
                socketTimeoutMS=10000,  # 10 second socket timeout
                maxPoolSize=50,  # Connection pool size
                minPoolSize=10,
                retryWrites=True
            )
            
            # Verify connection works
            _client.admin.command('ismaster')
            
            dbname = os.environ.get("MONGODB_DB", "placement_db")
            logger.info(f"✅ Successfully connected to MongoDB database: {dbname}")
            
            return _client[dbname]
            
        except (ServerSelectionTimeoutError, ConnectionFailure) as e:
            logger.error(f"MongoDB connection attempt {_connection_attempts} failed: {str(e)}")
            
            if attempt < _max_retries - 1:
                wait_time = _retry_delay * (attempt + 1)  # Exponential backoff
                logger.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                logger.error(f"Failed to connect to MongoDB after {_max_retries} attempts")
                raise RuntimeError(
                    f"Failed to connect to MongoDB after {_max_retries} attempts. "
                    f"Please check your MONGODB_URI environment variable and network connection."
                )
        except Exception as e:
            logger.error(f"Unexpected error connecting to MongoDB: {str(e)}")
            raise RuntimeError(f"Failed to connect to MongoDB: {str(e)}")
    
    raise RuntimeError("Failed to establish MongoDB connection")


def get_collection(name: str):
    return get_db()[name]


def get_next_sequence(seq_name: str) -> int:
    col = get_collection("counters")
    doc = col.find_one_and_update(
        {"_id": seq_name},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return int(doc.get("seq", 1))


def normalize_phone(value: Any) -> str:
    if value is None:
        return ""
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if not digits:
        return ""
    # Keep last up to 15 digits to avoid overwhelming _id size; typical phone is 10-13 digits
    if len(digits) > 15:
        digits = digits[-15:]
    return digits


def format_phone_id(digits: str) -> str:
    """Return a display-friendly ID string.

    For Indian numbers, format as "+91 0123456789" using the last 10 digits.
    If fewer than 10 digits are available, return the digits unchanged.
    """
    if not digits:
        return ""
    if len(digits) >= 10:
        last10 = digits[-10:]
        return f"+91 {last10}"
    return digits


def save_parsed_resume(parsed: Dict[str, Any], source_filename: Optional[str] = None) -> Dict[str, Any]:
    """Save parsed resume to MongoDB.

    Uses phone (normalized digits) as _id when present; otherwise assigns an auto-increment integer _id.
    Upserts on _id to avoid duplicates.
    Returns {"_id": <id>, "upserted": bool}.
    """
    # Choose collection from env (case-sensitive). Defaults to 'resumes' for backward compatibility.
    col_name = os.environ.get("MONGODB_COLLECTION", "resumes")
    col = get_collection(col_name)

    phone_raw = parsed.get("phone") or parsed.get("mobile") or ""
    phone_digits = normalize_phone(phone_raw)

    # Build document
    doc = {
        "name": parsed.get("name"),
        "email": parsed.get("email"),
    # Store formatted phone (matches _id format) for readability
    "phone": format_phone_id(phone_digits) or None,
        "skills": parsed.get("skills", []),
        "projects": parsed.get("projects", []),
        "internships": parsed.get("internships", []),
        "certifications": parsed.get("certifications") or parsed.get("certs") or [],
        "tenthPercentage": parsed.get("tenthPercentage"),
        "twelfthPercentage": parsed.get("twelfthPercentage"),
        "cgpa": parsed.get("cgpa") or parsed.get("collegeCGPA"),
        "university": parsed.get("university") or parsed.get("college"),
        "degree": parsed.get("degree"),
        "sourceFilename": source_filename,
        "uploadedAt": datetime.utcnow(),
    }

    # Determine _id
    if phone_digits:
        _id: Any = format_phone_id(phone_digits)
    else:
        _id = get_next_sequence("resume_seq")

    # Upsert by _id
    res = col.update_one({"_id": _id}, {"$set": {**doc, "_id": _id}}, upsert=True)
    upserted = bool(res.upserted_id is not None)
    return {"_id": _id, "upserted": upserted}


def save_candidate_prediction(payload: Dict[str, Any], prediction: Dict[str, Any]) -> Dict[str, Any]:
    """Persist final candidate submission AFTER prediction.

    Fields captured:
      - Personal: name, email, phone
      - Education: tenthPercentage, twelfthPercentage, collegeCGPA / cgpa, degree, college/university
      - Domain / Role: selectedDomainId, selectedCategoryId, customDomain, customJobRole, resolved names
      - Skills, projects, internships, certifications
      - Job Role Skills and Job Selection structures
      - User Profile information
      - Prediction results (entire dict)
    Uses same _id strategy (phone formatted) or auto-increment sequence.
    """
    print(f"[DB] 📥 save_candidate_prediction called")
    print(f"[DB] 📝 Payload keys: {list(payload.keys())}")
    print(f"[DB] 📞 Mobile: {payload.get('mobile')}, Name: {payload.get('name')}")
    
    col_name = os.environ.get("MONGODB_COLLECTION", "resumes")
    col = get_collection(col_name)
    
    print(f"[DB] 📊 Collection name: {col_name}")

    phone_raw = payload.get("mobile") or payload.get("phone") or ""
    phone_digits = normalize_phone(phone_raw)
    phone_formatted = format_phone_id(phone_digits) if phone_digits else None

    # Resolve domain / category names if provided in payload (frontend may not send names)
    domain_name = payload.get("domainName") or payload.get("selectedDomainName") or payload.get("customDomain")
    role_name = payload.get("jobRoleName") or payload.get("selectedCategoryName") or payload.get("customJobRole")

    # Get current timestamp
    current_time = datetime.utcnow()
    current_iso = current_time.isoformat()

    # Prepare job role skills structure if domain and skills are provided
    job_role_skills = None
    job_selection = None
    
    selected_skills = payload.get("selectedSkills", [])
    unselected_skills = payload.get("unselectedSkills", [])
    selected_domain_id = payload.get("selectedDomainId")
    selected_role_id = payload.get("selectedRoleId")
    
    if selected_domain_id and selected_skills:
        # Create jobRoleSkills structure
        job_role_skills = {
            "current": selected_skills,
            "skillsToLearn": unselected_skills,
            "domain": selected_domain_id,
            "role": selected_role_id or "unspecified",
            "lastUpdated": current_iso
        }
        
        # Create jobSelection structure
        role_description = f"Skills you possess for {selected_role_id or 'selected'} role in {domain_name or selected_domain_id}"
        job_selection = {
            "selectedSkills": selected_skills,
            "unselectedSkills": unselected_skills,
            "jobDomain": selected_domain_id,
            "jobRole": selected_role_id or "unspecified",
            "updatedAt": current_iso,
            "skillsCount": len(selected_skills),
            "unselectedSkillsCount": len(unselected_skills),
            "description": role_description,
            "isActive": True
        }

    # Create user profile structure
    user_profile = {
        "name": payload.get("name", ""),
        "email": payload.get("email", ""),
        "mobile": phone_digits,
        "linkedAt": current_iso,
        "profileComplete": True
    }

    # Prepare certifications - handle both string and array formats
    certifications_raw = payload.get("certifications", [])
    if isinstance(certifications_raw, str):
        # Handle comma-separated string format
        certifications = [cert.strip().strip('"') for cert in certifications_raw.split(',') if cert.strip()]
    else:
        certifications = certifications_raw or []

    doc = {
        "name": payload.get("name"),
        "email": payload.get("email"),
        "phone": phone_formatted,
        "tenthPercentage": payload.get("tenthPercentage"),
        "twelfthPercentage": payload.get("twelfthPercentage"),
        "cgpa": payload.get("collegeCGPA") or payload.get("cgpa"),
        "college": payload.get("college"),
        "degree": payload.get("degree"),
        "currentSem": payload.get("currentSem", ""),
        # Master's degree information
        "hasMasters": payload.get("hasMasters", False),
        "mastersDegree": payload.get("mastersDegree", ""),
        "mastersCollege": payload.get("mastersCollege", ""),
        "mastersCGPA": payload.get("mastersCGPA", ""),
        "mastersCurrentSem": payload.get("mastersCurrentSem", ""),
        # Domain and role selection
        "selectedDomainId": selected_domain_id,
        "selectedCategoryId": payload.get("selectedCategoryId"),
        "customDomain": payload.get("customDomain", ""),
        "customJobRole": payload.get("customJobRole", ""),
        "domainName": domain_name or "",
        "jobRoleName": role_name or "",
        # Skills and experience
        "skills": selected_skills,
        "projects": payload.get("projects", []),
        "internships": payload.get("internships", []),
        "certifications": certifications,
        # Prediction results
        "prediction": prediction,
        # Job role and selection structures
        "jobRoleSkills": job_role_skills,
        "jobSelection": job_selection,
        # User profile
        "userProfile": user_profile,
        # Timestamps
        "submittedAt": current_time,
        "lastUpdated": current_iso,
    }

    # Remove None values to keep document clean
    doc = {k: v for k, v in doc.items() if v is not None}

    if phone_digits:
        _id: Any = format_phone_id(phone_digits)
        print(f"[DB] 📞 Using phone as ID: {_id}")
    else:
        _id = get_next_sequence("resume_seq")
        print(f"[DB] 🔢 Using sequence ID: {_id}")

    print(f"[DB] 💾 Attempting to save to MongoDB collection '{col_name}'...")
    print(f"[DB] 📄 Document keys: {list(doc.keys())}")
    
    res = col.update_one({"_id": _id}, {"$set": {**doc, "_id": _id}}, upsert=True)
    upserted = bool(res.upserted_id is not None)
    
    print(f"[DB] ✅ Save successful! ID: {_id}, Upserted: {upserted}, Modified: {res.modified_count}")
    
    return {"_id": _id, "upserted": upserted}


def save_user_registration(registration_data):
    """
    Save user registration data to the Registration collection in MongoDB
    Uses username as the _id field for direct lookup
    
    Args:
        registration_data (dict): User registration information
        
    Returns:
        dict: Result with _id and success status
    """
    from datetime import datetime
    import hashlib
    
    try:
        # Get the Registration collection
        registration_col = get_collection("Registration")
        
        # Use username as the _id field
        username = registration_data.get("username", "")
        if not username:
            return {
                "success": False,
                "message": "Username is required"
            }
        
        # Hash the password for security
        password = registration_data.get("password", "")
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        # Prepare the registration document with username as _id
        registration_doc = {
            "_id": username,  # Use username as the primary key
            "firstName": registration_data.get("firstName", ""),
            "lastName": registration_data.get("lastName", ""),
            "passwordHash": password_hash,
            "dateOfBirth": registration_data.get("dateOfBirth", ""),
            "mobileNumber": registration_data.get("mobileNumber", ""),
            "email": registration_data.get("email", ""),
            "domain": registration_data.get("domain", ""),
            "role": registration_data.get("role", ""),
            "timeFrame": registration_data.get("timeFrame", ""),
            "verified": True,  # User has completed OTP verification
            "registrationDate": datetime.now(),
            "lastUpdated": datetime.now(),
            "status": "active"
        }
        
        # Insert the registration document
        result = registration_col.insert_one(registration_doc)
        
        return {
            "_id": username,
            "success": True,
            "message": "Registration saved successfully",
            "inserted_id": str(result.inserted_id)
        }
        
    except Exception as e:
        print(f"Error saving registration: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to save registration: {str(e)}"
        }


def verify_user_password(email_or_username, password):
    """
    Verify user password for sign-in
    
    Args:
        email_or_username (str): User's email address or username
        password (str): User's password
        
    Returns:
        dict: Result with verification status and user data
    """
    import hashlib
    
    try:
        # Get the Registration collection
        registration_col = get_collection("Registration")
        
        # Determine if input is email or username and find user accordingly
        input_value = email_or_username.strip()
        
        # Check if input looks like an email (contains @ symbol)
        if '@' in input_value:
            # Search by email
            user = registration_col.find_one({"email": input_value.lower()})
        else:
            # Search by username (which is stored as _id)
            user = registration_col.find_one({"_id": input_value})
        
        if not user:
            return {
                "success": False,
                "message": "User not found"
            }
        
        # Hash the provided password and compare
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        if user.get("passwordHash") == password_hash:
            return {
                "success": True,
                "message": "Password verified successfully",
                "user": {
                    "firstName": user.get("firstName", ""),
                    "lastName": user.get("lastName", ""),
                    "username": user.get("_id", ""),  # Username is now stored as _id
                    "email": user.get("email", ""),
                    "mobile": user.get("mobileNumber", ""),
                    "registrationDate": user.get("registrationDate")
                }
            }
        else:
            return {
                "success": False,
                "message": "Invalid password"
            }
            
    except Exception as e:
        print(f"Error verifying password: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to verify password: {str(e)}"
        }


def update_user_password(email, new_password):
    """
    Update user's password in the database
    
    Args:
        email (str): User's email address
        new_password (str): New password to set
        
    Returns:
        dict: Result with success status and message
    """
    import hashlib
    
    try:
        # Get the Registration collection
        registration_col = get_collection("Registration")
        
        # Find user by email
        user = registration_col.find_one({"email": email.strip().lower()})
        
        if not user:
            return {
                "success": False,
                "message": "User not found"
            }
        
        # Hash the new password
        password_hash = hashlib.sha256(new_password.encode()).hexdigest()
        
        # Update the password
        result = registration_col.update_one(
            {"email": email.strip().lower()},
            {"$set": {"passwordHash": password_hash}}
        )
        
        if result.modified_count > 0:
            return {
                "success": True,
                "message": "Password updated successfully"
            }
        else:
            return {
                "success": False,
                "message": "Failed to update password"
            }
            
    except Exception as e:
        print(f"Error updating password: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to update password: {str(e)}"
        }


def get_roadmap_collection():
    """Get the roadmaps collection"""
    return get_collection("roadmaps")


def save_job_role_skills_roadmap(mobile: str, job_domain: str, job_role: str, selected_skills: list, learning_path: dict = None) -> dict:
    """
    Save job role skills to the roadmaps collection with a dedicated section for job-specific skills.
    
    Args:
        mobile: User's mobile number (unique identifier)
        job_domain: The job domain (e.g., 'Data Science')
        job_role: The specific job role (e.g., 'Data Analyst')
        selected_skills: List of skills user possesses for this job role
        learning_path: Optional learning path recommendations
    
    Returns:
        dict: Result of the save operation
    """
    try:
        roadmap_col = get_roadmap_collection()
        
        # Create roadmap document structure
        roadmap_data = {
            "mobile": normalize_phone(mobile),
            "jobDomain": job_domain,
            "jobRole": job_role,
            "jobRoleSkills": {
                "selectedSkills": selected_skills,
                "skillsCount": len(selected_skills),
                "description": f"Skills you possess for {job_role} role in {job_domain}",
                "updatedAt": datetime.now().isoformat()
            },
            "learningPath": learning_path or {
                "recommendedSkills": [],
                "skillGaps": [],
                "courseSuggestions": [],
                "timelineWeeks": 0
            },
            "createdAt": datetime.now().isoformat(),
            "updatedAt": datetime.now().isoformat(),
            "isActive": True
        }
        
        # Update existing roadmap or create new one
        result = roadmap_col.update_one(
            {"mobile": normalize_phone(mobile), "jobDomain": job_domain, "jobRole": job_role},
            {"$set": roadmap_data},
            upsert=True
        )
        
        return {
            "success": True,
            "message": f"Job role skills roadmap saved successfully for {job_role}",
            "data": {
                "mobile": normalize_phone(mobile),
                "jobDomain": job_domain,
                "jobRole": job_role,
                "skillsCount": len(selected_skills),
                "selectedSkills": selected_skills,
                "isNew": result.upserted_id is not None
            }
        }
        
    except Exception as e:
        print(f"Error saving job role skills roadmap: {str(e)}")
        return {
            "success": False,
            "message": f"Error saving roadmap: {str(e)}"
        }


def get_job_role_skills_roadmap(mobile: str, job_domain: str = None, job_role: str = None) -> dict:
    """
    Retrieve job role skills roadmap from the roadmaps collection.
    
    Args:
        mobile: User's mobile number
        job_domain: Optional job domain filter
        job_role: Optional job role filter
    
    Returns:
        dict: Roadmap data or error message
    """
    try:
        roadmap_col = get_roadmap_collection()
        
        # Build query
        query = {"mobile": normalize_phone(mobile), "isActive": True}
        if job_domain:
            query["jobDomain"] = job_domain
        if job_role:
            query["jobRole"] = job_role
        
        # Get roadmaps
        roadmaps = list(roadmap_col.find(query).sort("updatedAt", -1))
        
        if not roadmaps:
            return {
                "success": False,
                "message": "No roadmaps found for the specified criteria"
            }
        
        # Convert ObjectId to string for JSON serialization
        for roadmap in roadmaps:
            roadmap["_id"] = str(roadmap["_id"])
        
        return {
            "success": True,
            "message": f"Found {len(roadmaps)} roadmap(s)",
            "data": {
                "roadmaps": roadmaps,
                "count": len(roadmaps)
            }
        }
        
    except Exception as e:
        print(f"Error retrieving job role skills roadmap: {str(e)}")
        return {
            "success": False,
            "message": f"Error retrieving roadmap: {str(e)}"
        }


def get_all_job_roadmaps(mobile: str) -> dict:
    """
    Get all roadmaps for a user across different job roles.
    
    Args:
        mobile: User's mobile number
    
    Returns:
        dict: All roadmaps for the user
    """
    try:
        roadmap_col = get_roadmap_collection()
        
        # Get all active roadmaps for user
        roadmaps = list(roadmap_col.find({
            "mobile": normalize_phone(mobile),
            "isActive": True
        }).sort("updatedAt", -1))
        
        if not roadmaps:
            return {
                "success": False,
                "message": "No roadmaps found for this user"
            }
        
        # Convert ObjectId to string and organize by job domain
        roadmaps_by_domain = {}
        for roadmap in roadmaps:
            roadmap["_id"] = str(roadmap["_id"])
            domain = roadmap["jobDomain"]
            if domain not in roadmaps_by_domain:
                roadmaps_by_domain[domain] = []
            roadmaps_by_domain[domain].append(roadmap)
        
        return {
            "success": True,
            "message": f"Found {len(roadmaps)} roadmap(s) across {len(roadmaps_by_domain)} domain(s)",
            "data": {
                "roadmapsByDomain": roadmaps_by_domain,
                "totalRoadmaps": len(roadmaps),
                "totalDomains": len(roadmaps_by_domain)
            }
        }
        
    except Exception as e:
        print(f"Error retrieving all job roadmaps: {str(e)}")
        return {
            "success": False,
            "message": f"Error retrieving roadmaps: {str(e)}"
        }
