"""
AWS Lambda handler for TimeBack automation.

This handler detects whether it's running in Lambda or locally,
sets up appropriate logging, validates environment variables,
and executes the main automation function.
"""
import os
import sys
import json
import logging
import traceback
from typing import Dict, Any

# Detect if running in Lambda
IS_LAMBDA = bool(os.environ.get('AWS_LAMBDA_FUNCTION_NAME'))


def setup_logging():
    """
    Set up logging based on environment.
    - Lambda: Log to console (CloudWatch)
    - Local: Log to both file and console
    """
    if IS_LAMBDA:
        # Lambda: Use default CloudWatch logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        logger = logging.getLogger()
        logger.info("Running in AWS Lambda environment")
    else:
        # Local: Log to both file and console
        log_dir = 'logs'
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        log_file = os.path.join(log_dir, 'lambda_handler.log')
        
        # Create logger
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        
        # Remove existing handlers
        logger.handlers = []
        
        # File handler
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.INFO)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
        
        logger.info("Running in local environment")
    
    return logger


def validate_required_env_vars():
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
    
    missing_vars = []
    for var_name, description in required_vars.items():
        if not os.getenv(var_name):
            missing_vars.append(f"{var_name} ({description})")
    
    if missing_vars:
        raise ValueError(
            f"Missing required environment variables:\n" + 
            "\n".join(f"  - {var}" for var in missing_vars)
        )


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda handler function.
    
    Args:
        event: Lambda event data (not used for scheduled invocations)
        context: Lambda context object
        
    Returns:
        dict: Lambda response with statusCode, headers, and body
    """
    logger = setup_logging()
    
    try:
        logger.info("=" * 60)
        logger.info("TimeBack Automation Lambda Handler Started")
        logger.info("=" * 60)
        
        # Validate environment variables
        logger.info("Validating environment variables...")
        validate_required_env_vars()
        logger.info("✓ All required environment variables present")
        
        # Import and run main automation
        logger.info("Importing main automation module...")
        from main import main
        
        logger.info("Starting automation execution...")
        main()
        
        logger.info("=" * 60)
        logger.info("TimeBack Automation Completed Successfully")
        logger.info("=" * 60)
        
        # Return success response
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json'
            },
            'body': json.dumps({
                'status': 'success',
                'message': 'Automation completed successfully'
            })
        }
    
    except ValueError as e:
        # Environment variable validation error
        error_msg = f"Configuration error: {str(e)}"
        logger.error(error_msg)
        
        return {
            'statusCode': 400,
            'headers': {
                'Content-Type': 'application/json'
            },
            'body': json.dumps({
                'status': 'error',
                'error_type': 'ConfigurationError',
                'message': error_msg
            })
        }
    
    except Exception as e:
        # Unexpected error - log full traceback
        error_msg = f"Unexpected error: {str(e)}"
        full_traceback = traceback.format_exc()
        
        logger.error("=" * 60)
        logger.error("ERROR: Automation failed with exception")
        logger.error("=" * 60)
        logger.error(f"Error message: {error_msg}")
        logger.error(f"Full traceback:\n{full_traceback}")
        logger.error("=" * 60)
        
        # Return error response
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json'
            },
            'body': json.dumps({
                'status': 'error',
                'error_type': type(e).__name__,
                'message': error_msg,
                'traceback': full_traceback if not IS_LAMBDA else 'Check CloudWatch logs for full traceback'
            })
        }


def local_test():
    """
    Local testing function with mock context.
    """
    print("Running local test of Lambda handler...")
    
    # Mock event and context
    mock_event = {
        'source': 'aws.events',
        'detail-type': 'Scheduled Event'
    }
    
    class MockContext:
        function_name = 'timeback-automation-local-test'
        function_version = '$LATEST'
        invoked_function_arn = 'arn:aws:lambda:us-east-1:123456789012:function:timeback-automation-local-test'
        memory_limit_in_mb = 1024
        aws_request_id = 'test-request-id'
        log_group_name = '/aws/lambda/timeback-automation-local-test'
        log_stream_name = 'test-stream'
    
    mock_context = MockContext()
    
    # Run handler
    response = lambda_handler(mock_event, mock_context)
    
    print("\n" + "=" * 60)
    print("Lambda Handler Response:")
    print("=" * 60)
    print(json.dumps(response, indent=2))
    print("=" * 60)
    
    return response


if __name__ == '__main__':
    # Allow local testing
    local_test()
