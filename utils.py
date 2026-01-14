"""
Utility functions for validation, retry logic, and rate limiting.
"""
import os
import time
import requests
from typing import Callable, Tuple, Any, Optional
from dotenv import load_dotenv

load_dotenv()


def validate_environment_variables():
    """
    Validate that all required environment variables are set.
    
    Raises:
        ValueError: If any required environment variable is missing
    """
    required_vars = {
        'TIMEBACK_PLATFORM_REST_ENDPOINT': 'TimeBack API endpoint',
        'TIMEBACK_PLATFORM_CLIENT_ID': 'TimeBack OAuth client ID',
        'TIMEBACK_PLATFORM_CLIENT_SECRET': 'TimeBack OAuth client secret',
        'GCP_CRED': 'Google Cloud service account credentials',
    }
    
    # HubSpot: Either access token OR OAuth credentials
    hubspot_token = os.getenv('HUBSPOT_ACCESS_TOKEN') or os.getenv('HUBSPOT_API_KEY')
    hubspot_client = os.getenv('HUBSPOT_CLIENT')
    hubspot_secret = os.getenv('HUBSPOT_SECRET')
    
    if not hubspot_token and not (hubspot_client and hubspot_secret):
        raise ValueError(
            "HubSpot authentication not configured. "
            "Provide either HUBSPOT_ACCESS_TOKEN (for Private App) or "
            "both HUBSPOT_CLIENT and HUBSPOT_SECRET (for OAuth)"
        )
    
    missing_vars = []
    for var_name, description in required_vars.items():
        if not os.getenv(var_name):
            missing_vars.append(f"{var_name} ({description})")
    
    if missing_vars:
        raise ValueError(
            f"Missing required environment variables:\n" + 
            "\n".join(f"  - {var}" for var in missing_vars)
        )


def retry_with_backoff(
    func: Callable,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    max_delay: float = 60.0,
    retryable_status_codes: set = None,
    retryable_exceptions: tuple = None
) -> Tuple[Any, Optional[str]]:
    """
    Retry a function with exponential backoff.
    
    Args:
        func: Function to retry (should return a tuple of (success: bool, result: Any, error: str))
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        backoff_factor: Multiplier for delay after each retry
        max_delay: Maximum delay in seconds
        retryable_status_codes: HTTP status codes that should trigger a retry (default: 429, 500, 502, 503, 504)
        retryable_exceptions: Exception types that should trigger a retry (default: requests exceptions)
        
    Returns:
        tuple: (result: Any, error: str or None)
    """
    if retryable_status_codes is None:
        retryable_status_codes = {429, 500, 502, 503, 504}
    
    if retryable_exceptions is None:
        retryable_exceptions = (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.RequestException
        )
    
    delay = initial_delay
    last_error = None
    
    for attempt in range(max_retries + 1):
        try:
            success, result, error = func()
            
            if success:
                return result, None
            
            # Check if error is retryable
            is_retryable = False
            
            # Check for HTTP status codes in error message
            if error:
                error_str = str(error) if not isinstance(error, str) else error
                for code in retryable_status_codes:
                    if f"HTTP {code}" in error_str:
                        is_retryable = True
                        break
                
                # Also check if error is a retryable exception type
                if isinstance(error, retryable_exceptions):
                    is_retryable = True
            
            # If not retryable or last attempt, return error
            if not is_retryable or attempt == max_retries:
                return result, error
            
            last_error = error
            
        except retryable_exceptions as e:
            last_error = str(e)
            if attempt == max_retries:
                return None, str(e)
        
        except Exception as e:
            # Non-retryable exception
            return None, str(e)
        
        # Wait before retrying (except on last attempt)
        if attempt < max_retries:
            time.sleep(min(delay, max_delay))
            delay *= backoff_factor
    
    return None, last_error or "Max retries exceeded"


def rate_limit_delay(delay_seconds: float = 0.5):
    """
    Add a delay between API calls to respect rate limits.
    
    Args:
        delay_seconds: Number of seconds to delay (default: 0.5)
    """
    time.sleep(delay_seconds)
