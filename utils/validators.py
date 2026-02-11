"""
Input validation utilities for placement prediction API
"""
from typing import Dict, List, Any, Tuple
import re

def validate_prediction_input(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Comprehensive input validation for prediction endpoint
    
    Args:
        data: Dictionary containing student information
        
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    
    if not data:
        return False, ["No data provided"]
    
    # 1. Validate required numeric fields with ranges
    required_fields = {
        'tenthPercentage': (0, 100, "10th percentage"),
        'twelfthPercentage': (0, 100, "12th percentage"),
        'collegeCGPA': (0, 10, "College CGPA")
    }
    
    for field, (min_val, max_val, display_name) in required_fields.items():
        if field not in data:
            errors.append(f"Missing required field: {display_name}")
            continue
        
        try:
            value = float(data[field])
            if not (min_val <= value <= max_val):
                errors.append(f"{display_name} must be between {min_val} and {max_val}, got {value}")
        except (ValueError, TypeError):
            errors.append(f"{display_name} must be a valid number, got {data[field]}")
    
    # 2. Validate optional array fields
    array_fields = {
        'selectedSkills': 'Form selected skills',
        'skills': 'Resume parsed skills',
        'projects': 'Projects'
    }
    
    for field, display_name in array_fields.items():
        if field in data:
            if not isinstance(data[field], list):
                errors.append(f"{display_name} must be an array, got {type(data[field]).__name__}")
            elif field in ['selectedSkills', 'skills']:
                # Validate skills array content
                if not all(isinstance(skill, str) for skill in data[field]):
                    errors.append(f"{display_name} must contain only strings")
                # Check for excessive skills (potential spam)
                if len(data[field]) > 50:
                    errors.append(f"{display_name} cannot exceed 50 skills, got {len(data[field])}")
    
    # 3. Validate optional string fields
    string_fields = {
        'selectedDomainId': 'Domain ID',
        'selectedRoleId': 'Role ID',
        'achievements': 'Achievements',
        'certifications': 'Certifications'
    }
    
    for field, display_name in string_fields.items():
        if field in data and data[field] is not None:
            if not isinstance(data[field], str):
                errors.append(f"{display_name} must be a string, got {type(data[field]).__name__}")
            # Check for excessive length
            elif len(data[field]) > 5000:
                errors.append(f"{display_name} text exceeds maximum length of 5000 characters")
    
    # 4. Validate projects structure if provided
    if 'projects' in data and isinstance(data['projects'], list):
        for idx, project in enumerate(data['projects']):
            if not isinstance(project, dict):
                errors.append(f"Project at index {idx} must be an object")
                continue
            
            # Validate project has title or description
            if 'title' not in project and 'description' not in project:
                errors.append(f"Project at index {idx} must have at least a title or description")
    
    # 5. Validate numeric ranges for optional fields
    optional_numeric = {
        'numInternships': (0, 20, "Number of internships"),
        'numHackathons': (0, 50, "Number of hackathons")
    }
    
    for field, (min_val, max_val, display_name) in optional_numeric.items():
        if field in data and data[field] is not None:
            try:
                value = int(data[field])
                if not (min_val <= value <= max_val):
                    errors.append(f"{display_name} must be between {min_val} and {max_val}, got {value}")
            except (ValueError, TypeError):
                errors.append(f"{display_name} must be a valid integer")
    
    is_valid = len(errors) == 0
    return is_valid, errors


def sanitize_text_input(text: str, max_length: int = 5000) -> str:
    """
    Sanitize text input by removing excessive whitespace and limiting length
    
    Args:
        text: Input text to sanitize
        max_length: Maximum allowed length
        
    Returns:
        Sanitized text
    """
    if not isinstance(text, str):
        return ""
    
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text.strip())
    
    # Limit length
    if len(text) > max_length:
        text = text[:max_length]
    
    return text


def normalize_skill(skill: str) -> str:
    """
    Normalize skill name for consistent matching
    
    Args:
        skill: Skill name to normalize
        
    Returns:
        Normalized skill name
    """
    if not isinstance(skill, str):
        return ""
    
    # Convert to lowercase and remove special characters
    normalized = re.sub(r'[^\w\s-]', '', skill.lower().strip())
    
    # Remove excessive whitespace
    normalized = re.sub(r'\s+', ' ', normalized)
    
    return normalized


def deduplicate_skills(skills: List[str]) -> List[str]:
    """
    Remove duplicate skills after normalization
    
    Args:
        skills: List of skills
        
    Returns:
        Deduplicated list of skills
    """
    if not skills:
        return []
    
    seen = set()
    unique_skills = []
    
    for skill in skills:
        normalized = normalize_skill(skill)
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique_skills.append(skill)  # Keep original case
    
    return unique_skills


def validate_domain_id(domain_id: str) -> bool:
    """
    Validate domain/category ID format
    
    Args:
        domain_id: Domain or category ID
        
    Returns:
        True if valid format
    """
    if not isinstance(domain_id, str):
        return False
    
    # Allow alphanumeric, underscore, hyphen
    return bool(re.match(r'^[a-zA-Z0-9_-]+$', domain_id))
