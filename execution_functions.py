import requests
import os
import base64
from google_sheets_functions import authenticate_google_sheets, open_spreadsheet, get_worksheet, read_worksheet_to_dataframe, write_dataframe_to_worksheet
import config
import pandas as pd
from datetime import datetime
from utils import retry_with_backoff, rate_limit_delay

def get_timeback_access_token():
    """
    Get access token from TimeBack API using client credentials.
    
    Returns:
        str: Access token
    """
    endpoint = os.getenv('TIMEBACK_PLATFORM_REST_ENDPOINT')
    client_id = os.getenv('TIMEBACK_PLATFORM_CLIENT_ID')
    client_secret = os.getenv('TIMEBACK_PLATFORM_CLIENT_SECRET')
    
    if not all([endpoint, client_id, client_secret]):
        raise ValueError("Missing TimeBack platform credentials in environment variables")
    
    credentials = f"{client_id}:{client_secret}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()
    
    token_url = f"{endpoint}/auth/1.0/token"
    headers = {
        "Authorization": f"Basic {encoded_credentials}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = "grant_type=client_credentials&scope=https://purl.imsglobal.org/spec/or/v1p2/scope/roster.createput%20https://purl.imsglobal.org/spec/or/v1p2/scope/roster.readonly%20https://purl.imsglobal.org/spec/lti/v1p3/scope/lti.readonly%20https://purl.imsglobal.org/spec/lti/v1p3/scope/lti.createput"
    
    response = requests.post(token_url, headers=headers, data=data)
    response.raise_for_status()
    
    return response.json()['access_token']


def post_student_account(account_payload, access_token):
    """
    Create a student account in TimeBack with retry logic.
    
    Args:
        account_payload: Account creation payload dictionary
        access_token: TimeBack API access token
        
    Returns:
        tuple: (success: bool, user_id: str, error_message: str)
    """
    endpoint = os.getenv('TIMEBACK_PLATFORM_REST_ENDPOINT')
    url = f"{endpoint}/rostering/1.0/students"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    def _make_request():
        try:
            response = requests.put(url, headers=headers, json=account_payload, timeout=30)
            
            if response.status_code in [200, 201]:
                # Account created successfully
                # Extract user_id from response (may be different from payload if account already existed)
                response_data = response.json()
                user_id = response_data.get('student', {}).get('sourcedId') or account_payload['student']['sourcedId']
                return True, user_id, None
            elif response.status_code == 409:
                # Account already exists - this is actually a success case
                # The API might return the existing user_id in the response
                try:
                    response_data = response.json()
                    user_id = response_data.get('student', {}).get('sourcedId') or account_payload['student']['sourcedId']
                    return True, user_id, None
                except:
                    # If we can't extract user_id, use the one from payload
                    return True, account_payload['student']['sourcedId'], None
            else:
                # Account creation failed
                error_msg = f"HTTP {response.status_code}: {response.text}"
                return False, None, error_msg
        
        except Exception as e:
            return False, None, str(e)
    
    # Apply retry logic with exponential backoff
    result, error = retry_with_backoff(_make_request, max_retries=3, initial_delay=1.0)
    
    if result is not None:
        return True, result, None
    else:
        return False, None, error


def post_profile_assignment(user_id, profile_payload, access_token):
    """
    Assign a profile (app or assessment) to a user with retry logic.
    
    Args:
        user_id: User sourcedId
        profile_payload: Profile assignment payload dictionary
        access_token: TimeBack API access token
        
    Returns:
        tuple: (success: bool, error_message: str)
    """
    endpoint = os.getenv('TIMEBACK_PLATFORM_REST_ENDPOINT')
    profile_id = profile_payload['profileId']
    url = f"{endpoint}/rostering/1.0/users/{user_id}/profiles/{profile_id}"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    def _make_request():
        try:
            response = requests.put(url, headers=headers, json=profile_payload, timeout=30)
            
            if response.status_code in [200, 201]:
                return True, True, None  # success=True, result=True (placeholder), error=None
            else:
                error_msg = f"HTTP {response.status_code}: {response.text}"
                return False, None, error_msg
        
        except Exception as e:
            return False, None, str(e)
    
    # Apply retry logic with exponential backoff
    result, error = retry_with_backoff(_make_request, max_retries=3, initial_delay=1.0)
    
    if error is None:
        return True, None
    else:
        return False, error


def execute_api_calls(all_results):
    """
    Execute API calls to create accounts and assignments for all students.
    Processes students sequentially (one at a time).
    
    Args:
        all_results: List of result dictionaries from processing phase
        
    Returns:
        tuple: (success_logs: list, fail_logs: list, summary: dict)
    """
    access_token = get_timeback_access_token()
    endpoint = os.getenv('TIMEBACK_PLATFORM_REST_ENDPOINT')
    
    success_logs = []
    fail_logs = []
    
    # Summary statistics
    summary = {
        'accounts_created': 0,
        'accounts_failed': 0,
        'apps_assigned': 0,
        'apps_failed': 0,
        'assessments_assigned': 0,
        'assessments_failed': 0
    }
    
    for result in all_results:
        email = result.get('email', 'Unknown')
        segment = result.get('segment', 'Unknown')
        grade = result.get('grade', 'Unknown')
        
        # Step 1: Create Account
        account_payload = result.get('account_payload')
        if not account_payload:
            error_msg = "No account payload available"
            fail_logs.append({
                'timestamp': datetime.now().isoformat(),
                'email': email,
                'segment': segment,
                'grade': grade,
                'step': 'account_creation',
                'error': error_msg
            })
            summary['accounts_failed'] += 1
            continue
        
        # Rate limiting: Add delay before API call
        rate_limit_delay(0.5)
        
        success, user_id, error_msg = post_student_account(account_payload, access_token)
        
        if not success:
            # Account creation failed - log and skip this student
            fail_logs.append({
                'timestamp': datetime.now().isoformat(),
                'email': email,
                'segment': segment,
                'grade': grade,
                'step': 'account_creation',
                'error': error_msg
            })
            summary['accounts_failed'] += 1
            continue
        
        # Account created successfully
        summary['accounts_created'] += 1
        
        # Update user_id in all assignment payloads (in case API returned different ID)
        if user_id != account_payload['student']['sourcedId']:
            # Update app assignment payload if it exists
            if result.get('app_assignment'):
                # Note: The profile assignment uses the user_id in the URL, not in the payload
                pass  # user_id is used in URL, not payload
        
        # Step 2: Assign Learning App
        app_assignment = result.get('app_assignment')
        app_name = result.get('app_name', 'Unknown')
        
        if app_assignment:
            # Rate limiting: Add delay before API call
            rate_limit_delay(0.5)
            
            success, error_msg = post_profile_assignment(user_id, app_assignment, access_token)
            
            if success:
                summary['apps_assigned'] += 1
            else:
                summary['apps_failed'] += 1
                fail_logs.append({
                    'timestamp': datetime.now().isoformat(),
                    'email': email,
                    'segment': segment,
                    'grade': grade,
                    'step': 'app_assignment',
                    'app_name': app_name,
                    'error': error_msg
                })
        
        # Step 3: Assign Assessments
        assessment_assignments = result.get('assessment_assignments', [])
        
        for assessment_payload in assessment_assignments:
            # Rate limiting: Add delay before API call
            rate_limit_delay(0.5)
            
            assessment_name = assessment_payload.get('description', 'Unknown Assessment')
            success, error_msg = post_profile_assignment(user_id, assessment_payload, access_token)
            
            if success:
                summary['assessments_assigned'] += 1
            else:
                summary['assessments_failed'] += 1
                fail_logs.append({
                    'timestamp': datetime.now().isoformat(),
                    'email': email,
                    'segment': segment,
                    'grade': grade,
                    'step': 'assessment_assignment',
                    'assessment_name': assessment_name,
                    'error': error_msg
                })
        
        # Log success (only if account was created)
        success_logs.append({
            'timestamp': datetime.now().isoformat(),
            'email': email,
            'segment': segment,
            'grade': grade,
            'app_name': app_name,
            'user_id': user_id,
            'apps_assigned': 1 if app_assignment else 0,
            'assessments_assigned': len(assessment_assignments)
        })
    
    return success_logs, fail_logs, summary


def flush_logs(success_logs, fail_logs):
    """
    Write all logs to Google Sheets in batch (2 API calls total).
    
    Args:
        success_logs: List of success log dictionaries
        fail_logs: List of failure log dictionaries
    """
    client = authenticate_google_sheets()
    spreadsheet = open_spreadsheet(client, spreadsheet_id=config.APP_IDS_GSHEET)
    
    # Write success logs
    if success_logs:
        success_worksheet = get_worksheet(spreadsheet, worksheet_name='success_log')
        
        # Read existing data
        try:
            existing_success = read_worksheet_to_dataframe(success_worksheet, header_row=0)
        except:
            existing_success = pd.DataFrame()
        
        # Convert new logs to DataFrame
        new_success_df = pd.DataFrame(success_logs)
        
        # Append new logs to existing
        if not existing_success.empty:
            combined_success = pd.concat([existing_success, new_success_df], ignore_index=True)
        else:
            combined_success = new_success_df
        
        # Write back to Google Sheets
        write_dataframe_to_worksheet(success_worksheet, combined_success, row=1, col=1, 
                                     include_index=False, include_column_header=True, resize=True)
    
    # Write failure logs
    if fail_logs:
        fail_worksheet = get_worksheet(spreadsheet, worksheet_name='fail_log')
        
        # Read existing data
        try:
            existing_fail = read_worksheet_to_dataframe(fail_worksheet, header_row=0)
        except:
            existing_fail = pd.DataFrame()
        
        # Convert new logs to DataFrame
        new_fail_df = pd.DataFrame(fail_logs)
        
        # Append new logs to existing
        if not existing_fail.empty:
            combined_fail = pd.concat([existing_fail, new_fail_df], ignore_index=True)
        else:
            combined_fail = new_fail_df
        
        # Write back to Google Sheets
        write_dataframe_to_worksheet(fail_worksheet, combined_fail, row=1, col=1, 
                                    include_index=False, include_column_header=True, resize=True)


def execute_and_log(all_results, skip_account_creation=False):
    """
    Main function to execute API calls and flush logs.
    
    Args:
        all_results: List of result dictionaries from processing phase
        skip_account_creation: If True, skip TimeBack account creation but still create trackers
        
    Returns:
        tuple: (summary: dict, success_logs: list, fail_logs: list, tracker_results: list, student_data_dict: dict)
    """
    if skip_account_creation:
        print("TESTING MODE: Skipping TimeBack account creation...")
        # Create mock success_logs from all_results for tracker creation
        success_logs = []
        for result in all_results:
            if result.get('account_payload'):  # Only include if payload was prepared
                success_logs.append({
                    'timestamp': datetime.now().isoformat(),
                    'email': result.get('email', 'Unknown'),
                    'segment': result.get('segment', 'Unknown'),
                    'grade': result.get('grade', 'Unknown'),
                    'app_name': result.get('app_name', 'Unknown'),
                    'user_id': 'test-mode-no-account-created',
                    'apps_assigned': 1 if result.get('app_assignment') else 0,
                    'assessments_assigned': len(result.get('assessment_assignments', []))
                })
        fail_logs = []
        summary = {
            'accounts_created': 0,
            'accounts_failed': 0,
            'apps_assigned': 0,
            'apps_failed': 0,
            'assessments_assigned': 0,
            'assessments_failed': 0
        }
        print(f"  Mocked {len(success_logs)} successful account creations for testing")
    else:
        print("Executing API calls...")
        success_logs, fail_logs, summary = execute_api_calls(all_results)
    
    if not skip_account_creation:
        print(f"\nExecution Summary:")
        print(f"  Accounts created: {summary['accounts_created']}")
        print(f"  Accounts failed: {summary['accounts_failed']}")
        print(f"  Apps assigned: {summary['apps_assigned']}")
        print(f"  Apps failed: {summary['apps_failed']}")
        print(f"  Assessments assigned: {summary['assessments_assigned']}")
        print(f"  Assessments failed: {summary['assessments_failed']}")
        
        print("\nFlushing logs to Google Sheets...")
        flush_logs(success_logs, fail_logs)
        print(f"  Success logs written: {len(success_logs)}")
        print(f"  Failure logs written: {len(fail_logs)}")
    else:
        print("\nTESTING MODE: Skipping log writes to Google Sheets")
    
    # Create tracker spreadsheets for successfully created accounts
    print("\nCreating tracker spreadsheets...")
    from tracker_functions import create_trackers_for_students, write_trackers_to_sheet
    from google_sheets_functions import authenticate_google_sheets, open_spreadsheet, get_worksheet, read_worksheet_to_dataframe
    
    # Load config_df for tracker creation (to map segment to app)
    client = authenticate_google_sheets()
    spreadsheet = open_spreadsheet(client, spreadsheet_id=config.APP_IDS_GSHEET)
    main_config_worksheet = get_worksheet(spreadsheet, worksheet_name='main_config')
    config_df = read_worksheet_to_dataframe(main_config_worksheet, header_row=0)
    
    # Build student_data_dict from all_results (for signup dates, grades, and names)
    student_data_dict = {}
    for result in all_results:
        email = result.get('email')
        if email:
            signup_date = result.get('signup_date')
            if not signup_date:
                signup_date = datetime.now()  # Fallback to current date
            
            student_data_dict[email] = {
                'signup_date': signup_date,
                'segment': result.get('segment'),
                'grade': result.get('grade'),
                'name': result.get('name'),  # For email personalization
                'first_name': result.get('first_name')  # Fallback for name
            }
    
    tracker_results = create_trackers_for_students(success_logs, student_data_dict, config_df)
    
    successful_trackers = sum(1 for tr in tracker_results if tr['success'])
    failed_trackers = sum(1 for tr in tracker_results if not tr['success'])
    
    print(f"  Trackers created: {successful_trackers}")
    print(f"  Trackers failed: {failed_trackers}")
    
    if failed_trackers > 0:
        print("\n  Tracker creation errors:")
        for tr in tracker_results:
            if not tr['success']:
                print(f"    - {tr.get('email', 'Unknown')}: {tr.get('error', 'Unknown error')}")
    
    # Write trackers to all_trackers worksheet in batch
    if successful_trackers > 0:
        print("\nWriting trackers to all_trackers worksheet...")
        write_trackers_to_sheet(tracker_results)
        print(f"  {successful_trackers} trackers written to all_trackers worksheet")
    
    return summary, success_logs, fail_logs, tracker_results, student_data_dict


def prepare_summary_data(execution_summary, success_logs, fail_logs, total_processed):
    """
    Prepare summary data for notifications.
    
    Args:
        execution_summary: Summary dictionary from execution
        success_logs: List of success log dictionaries
        fail_logs: List of failure log dictionaries
        total_processed: Total number of students processed
        
    Returns:
        dict: Prepared summary data with success_details and failure_details
    """
    # Prepare success details for notification
    success_details = []
    for log in success_logs:
        success_details.append({
            'email': log.get('email', 'Unknown'),
            'app_name': log.get('app_name', 'Unknown'),
            'segment': log.get('segment', 'Unknown')
        })
    
    # Prepare failure details for notification (only account creation failures)
    failure_details = []
    for log in fail_logs:
        if log.get('step') == 'account_creation':
            failure_details.append({
                'email': log.get('email', 'Unknown'),
                'reason': log.get('error', 'Unknown error')
            })
    
    return {
        'total_processed': total_processed,
        'successful_accounts': execution_summary['accounts_created'],
        'failed_accounts': execution_summary['accounts_failed'],
        'success_details': success_details,
        'failure_details': failure_details
    }
