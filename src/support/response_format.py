from typing import Any, Dict

def format_success(data: Any, message: str = "Success") -> Dict:
    """Format success response."""
    return {
        'success': True,
        'message': message,
        'data': data
    }

def format_error(message: str, details: Any = None) -> Dict:
    """Format error response."""
    response = {
        'success': False,
        'message': message
    }
    
    if details:
        response['error'] = details
    
    return response

def format_validation_error(errors: Dict) -> Dict:
    """Format validation error response."""
    return {
        'success': False,
        'message': 'Validation failed',
        'errors': errors
    }