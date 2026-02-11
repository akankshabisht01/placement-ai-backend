"""
Centralized Error Handling Utilities
Provides standardized error responses and logging for the API
"""

import logging
import traceback
from functools import wraps
from flask import jsonify, request
from datetime import datetime

# Set up logger
logger = logging.getLogger(__name__)

# ============================================================================
# ERROR CODES
# ============================================================================
class ErrorCode:
    """Standardized error codes for different failure types"""
    
    # Client Errors (400-499)
    VALIDATION_ERROR = 'VALIDATION_ERROR'
    MISSING_FIELD = 'MISSING_FIELD'
    INVALID_FORMAT = 'INVALID_FORMAT'
    INVALID_VALUE = 'INVALID_VALUE'
    FILE_TOO_LARGE = 'FILE_TOO_LARGE'
    UNSUPPORTED_FILE_TYPE = 'UNSUPPORTED_FILE_TYPE'
    AUTHENTICATION_ERROR = 'AUTHENTICATION_ERROR'
    AUTHORIZATION_ERROR = 'AUTHORIZATION_ERROR'
    RESOURCE_NOT_FOUND = 'RESOURCE_NOT_FOUND'
    DUPLICATE_RESOURCE = 'DUPLICATE_RESOURCE'
    RATE_LIMIT_EXCEEDED = 'RATE_LIMIT_EXCEEDED'
    
    # Server Errors (500-599)
    INTERNAL_ERROR = 'INTERNAL_ERROR'
    DATABASE_ERROR = 'DATABASE_ERROR'
    MODEL_ERROR = 'MODEL_ERROR'
    PREDICTION_ERROR = 'PREDICTION_ERROR'
    RESUME_PARSE_ERROR = 'RESUME_PARSE_ERROR'
    EMAIL_ERROR = 'EMAIL_ERROR'
    SERVICE_UNAVAILABLE = 'SERVICE_UNAVAILABLE'
    TIMEOUT_ERROR = 'TIMEOUT_ERROR'

# ============================================================================
# CUSTOM EXCEPTIONS
# ============================================================================

class APIError(Exception):
    """Base exception for API errors"""
    def __init__(self, message, code=ErrorCode.INTERNAL_ERROR, status_code=500, details=None):
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)

class ValidationError(APIError):
    """Validation error"""
    def __init__(self, message, details=None):
        super().__init__(
            message=message,
            code=ErrorCode.VALIDATION_ERROR,
            status_code=400,
            details=details
        )

class DatabaseError(APIError):
    """Database operation error"""
    def __init__(self, message, details=None):
        super().__init__(
            message=message,
            code=ErrorCode.DATABASE_ERROR,
            status_code=500,
            details=details
        )

class ModelError(APIError):
    """ML Model error"""
    def __init__(self, message, details=None):
        super().__init__(
            message=message,
            code=ErrorCode.MODEL_ERROR,
            status_code=500,
            details=details
        )

class ResourceNotFoundError(APIError):
    """Resource not found error"""
    def __init__(self, message, details=None):
        super().__init__(
            message=message,
            code=ErrorCode.RESOURCE_NOT_FOUND,
            status_code=404,
            details=details
        )

# ============================================================================
# ERROR RESPONSE FORMATTER
# ============================================================================

def format_error_response(error, code=None, status_code=None, details=None, request_id=None):
    """
    Format a standardized error response
    
    Args:
        error: Error message or Exception object
        code: Error code (from ErrorCode class)
        status_code: HTTP status code
        details: Additional error details
        request_id: Request tracking ID
    
    Returns:
        Tuple of (response_dict, status_code)
    """
    # Extract error details if it's an APIError
    if isinstance(error, APIError):
        message = error.message
        code = error.code
        status_code = error.status_code
        details = error.details
    elif isinstance(error, Exception):
        message = str(error)
        code = code or ErrorCode.INTERNAL_ERROR
        status_code = status_code or 500
        details = details or {}
    else:
        message = str(error)
        code = code or ErrorCode.INTERNAL_ERROR
        status_code = status_code or 500
        details = details or {}
    
    # Generate request ID if not provided
    if not request_id:
        request_id = generate_request_id()
    
    response = {
        'success': False,
        'error': {
            'message': message,
            'code': code,
            'details': details
        },
        'meta': {
            'timestamp': datetime.now().isoformat(),
            'request_id': request_id
        }
    }
    
    return response, status_code

def format_success_response(data, message=None, meta=None, request_id=None):
    """
    Format a standardized success response
    
    Args:
        data: Response data
        message: Optional success message
        meta: Optional metadata
        request_id: Request tracking ID
    
    Returns:
        Dictionary with standardized success format
    """
    # Generate request ID if not provided
    if not request_id:
        request_id = generate_request_id()
    
    response = {
        'success': True,
        'data': data
    }
    
    if message:
        response['message'] = message
    
    # Add metadata
    response['meta'] = {
        'timestamp': datetime.now().isoformat(),
        'request_id': request_id
    }
    
    if meta:
        response['meta'].update(meta)
    
    return response

# ============================================================================
# REQUEST ID GENERATION
# ============================================================================

def generate_request_id():
    """Generate a unique request ID for tracking"""
    import uuid
    return f"req_{uuid.uuid4().hex[:12]}"

# ============================================================================
# ERROR LOGGING
# ============================================================================

def log_error(error, request_obj=None, request_id=None, severity='ERROR'):
    """
    Log error with contextual information
    
    Args:
        error: Error or exception to log
        request_obj: Flask request object
        request_id: Request tracking ID
        severity: Log severity level
    """
    # Get request details if available
    request_details = {}
    if request_obj:
        request_details = {
            'method': request_obj.method,
            'path': request_obj.path,
            'remote_addr': request_obj.remote_addr,
            'user_agent': request_obj.headers.get('User-Agent', 'Unknown')
        }
    
    # Build log message
    log_data = {
        'request_id': request_id or generate_request_id(),
        'error_message': str(error),
        'error_type': type(error).__name__,
        'request': request_details
    }
    
    # Include stack trace for exceptions
    if isinstance(error, Exception):
        log_data['stack_trace'] = traceback.format_exc()
    
    # Log based on severity
    if severity == 'CRITICAL':
        logger.critical(f"CRITICAL ERROR: {log_data}")
    elif severity == 'ERROR':
        logger.error(f"ERROR: {log_data}")
    elif severity == 'WARNING':
        logger.warning(f"WARNING: {log_data}")
    else:
        logger.info(f"INFO: {log_data}")

# ============================================================================
# DECORATOR FOR ERROR HANDLING
# ============================================================================

def handle_errors(f):
    """
    Decorator to wrap route handlers with standardized error handling
    
    Usage:
        @app.route('/api/endpoint')
        @handle_errors
        def endpoint():
            # Your code here
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        request_id = generate_request_id()
        
        try:
            # Execute the wrapped function
            result = f(*args, **kwargs)
            
            # If result is already a Response object, return it
            if hasattr(result, 'status_code'):
                return result
            
            # If result is a tuple (data, status_code), handle it
            if isinstance(result, tuple):
                return result
            
            # Otherwise, wrap in success response
            return jsonify(format_success_response(result, request_id=request_id))
            
        except APIError as e:
            # Handle custom API errors
            log_error(e, request_obj=request, request_id=request_id, severity='WARNING')
            response, status_code = format_error_response(e, request_id=request_id)
            return jsonify(response), status_code
            
        except ValueError as e:
            # Handle value errors (typically validation)
            log_error(e, request_obj=request, request_id=request_id, severity='WARNING')
            response, status_code = format_error_response(
                error=str(e),
                code=ErrorCode.INVALID_VALUE,
                status_code=400,
                request_id=request_id
            )
            return jsonify(response), status_code
            
        except KeyError as e:
            # Handle missing key errors
            log_error(e, request_obj=request, request_id=request_id, severity='WARNING')
            response, status_code = format_error_response(
                error=f"Missing required field: {str(e)}",
                code=ErrorCode.MISSING_FIELD,
                status_code=400,
                request_id=request_id
            )
            return jsonify(response), status_code
            
        except Exception as e:
            # Handle all other exceptions
            log_error(e, request_obj=request, request_id=request_id, severity='ERROR')
            response, status_code = format_error_response(
                error="An unexpected error occurred. Please try again later.",
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
                details={'original_error': str(e)} if app.debug else {},
                request_id=request_id
            )
            return jsonify(response), status_code
    
    return decorated_function

# ============================================================================
# VALIDATION HELPER
# ============================================================================

def validate_required_fields(data, required_fields):
    """
    Validate that all required fields are present in the data
    
    Args:
        data: Dictionary to validate
        required_fields: List of required field names
    
    Raises:
        ValidationError: If any required field is missing
    """
    missing_fields = []
    
    for field in required_fields:
        if field not in data or data[field] is None or data[field] == '':
            missing_fields.append(field)
    
    if missing_fields:
        raise ValidationError(
            message=f"Missing required fields: {', '.join(missing_fields)}",
            details={'missing_fields': missing_fields}
        )

def validate_numeric_range(value, field_name, min_val, max_val):
    """
    Validate that a numeric value is within a specified range
    
    Args:
        value: Value to validate
        field_name: Name of the field (for error messages)
        min_val: Minimum allowed value
        max_val: Maximum allowed value
    
    Raises:
        ValidationError: If value is out of range
    """
    try:
        num_value = float(value)
        if not (min_val <= num_value <= max_val):
            raise ValidationError(
                message=f"{field_name} must be between {min_val} and {max_val}, got {num_value}",
                details={'field': field_name, 'value': num_value, 'min': min_val, 'max': max_val}
            )
    except (ValueError, TypeError):
        raise ValidationError(
            message=f"{field_name} must be a valid number",
            details={'field': field_name, 'value': str(value)}
        )

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def is_production():
    """Check if running in production environment"""
    import os
    return os.getenv('FLASK_ENV', 'development') == 'production'

# Import app only when needed to avoid circular imports
app = None
try:
    from flask import current_app as app
except:
    pass
