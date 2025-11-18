from functools import wraps
from utils.logger import Logger

logger = Logger.setup()

def handle_error(func):
    """Decorator for error handling."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {str(e)}")
            return None
    return wrapper

def handle_api_error(func):
    """Decorator for API error handling."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"API Error in {func.__name__}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }, 500
    return wrapper
