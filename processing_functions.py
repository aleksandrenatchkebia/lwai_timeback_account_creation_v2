import pandas as pd
import uuid
from datetime import datetime
from google_sheets_functions import authenticate_google_sheets, open_spreadsheet, get_worksheet, read_worksheet_to_dataframe
import config
import os
import requests
import base64
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# TimeBack organization constants
TIMEBACK_ORG_HREF = "https://timeback.com/orgs/84105a1c-29e5-44fc-a497-36a7c61860c5"
TIMEBACK_ORG_SOURCED_ID = "84105a1c-29e5-44fc-a497-36a7c61860c5"

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
    
    # Create Basic Auth header
    credentials = f"{client_id}:{client_secret}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()
    
    # Request token
    token_url = f"{endpoint}/auth/1.0/token"
    headers = {
        "Authorization": f"Basic {encoded_credentials}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = "grant_type=client_credentials&scope=https://purl.imsglobal.org/spec/or/v1p2/scope/roster.createput%20https://purl.imsglobal.org/spec/or/v1p2/scope/roster.readonly%20https://purl.imsglobal.org/spec/lti/v1p3/scope/lti.readonly%20https://purl.imsglobal.org/spec/lti/v1p3/scope/lti.createput"
    
    response = requests.post(token_url, headers=headers, data=data)
    response.raise_for_status()
    
    return response.json()['access_token']


def load_configuration_data():
    """
    Load all configuration data ONCE (optimization to avoid redundant API calls).
    
    Returns:
        tuple: (config_df, assessments_df, apps_dict)
            - config_df: Segment configuration from main_config worksheet
            - assessments_df: Assessment IDs from assessment_ids worksheet
            - apps_dict: Dictionary mapping app name → app ID from TimeBack API
    """
    # Load segment configuration from Google Sheets
    client = authenticate_google_sheets()
    spreadsheet = open_spreadsheet(client, spreadsheet_id=config.APP_IDS_GSHEET)
    
    # Load main_config worksheet
    main_config_worksheet = get_worksheet(spreadsheet, worksheet_name='main_config')
    config_df = read_worksheet_to_dataframe(main_config_worksheet, header_row=0)
    
    # Load assessment_ids worksheet
    assessments_worksheet = get_worksheet(spreadsheet, worksheet_name='assessment_ids')
    assessments_df = read_worksheet_to_dataframe(assessments_worksheet, header_row=0)
    
    # Fetch applications from TimeBack API
    access_token = get_timeback_access_token()
    endpoint = os.getenv('TIMEBACK_PLATFORM_REST_ENDPOINT')
    apps_url = f"{endpoint}/applications/1.0"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    apps_dict = {}
    offset = 0
    limit = 100
    
    # First, try paginated fetch
    while True:
        response = requests.get(f"{apps_url}?limit={limit}&offset={offset}", headers=headers)
        response.raise_for_status()
        data = response.json()
        
        for app in data.get('applications', []):
            app_name = app.get('name', '')
            app_id = app.get('sourcedId', '')
            if app_name and app_id:
                apps_dict[app_name] = app_id
        
        pagination = data.get('pagination', {})
        if not pagination.get('hasMore', False):
            break
        
        offset += limit
    
    # If we need specific apps that weren't found, search for them by name
    # This handles cases where pagination doesn't return all apps
    # Get list of apps we need from config
    needed_apps = set(config_df['app'].dropna().unique())
    missing_apps = needed_apps - set(apps_dict.keys())
    
    if missing_apps:
        import urllib.parse
        for app_name in missing_apps:
            # Search for the app by exact name
            filter_value = f"name='{app_name}'"
            encoded_filter = urllib.parse.quote(filter_value, safe="=")
            search_url = f"{apps_url}?filter={encoded_filter}"
            
            try:
                search_response = requests.get(search_url, headers=headers, timeout=10)
                search_response.raise_for_status()
                search_data = search_response.json()
                
                for app in search_data.get('applications', []):
                    found_name = app.get('name', '')
                    found_id = app.get('sourcedId', '')
                    if found_name == app_name and found_id:
                        apps_dict[found_name] = found_id
                        print(f"  Found missing app via search: {found_name}")
            except Exception as e:
                print(f"  Warning: Could not search for app '{app_name}': {e}")
    
    return config_df, assessments_df, apps_dict


def convert_grade_to_string(grade_num):
    """
    Convert numeric grade to TimeBack API format string.
    
    Args:
        grade_num: Numeric grade (current grade = last completed + 1)
        
    Returns:
        str: Grade string ("PK", "K", "1" through "12")
    """
    if pd.isna(grade_num):
        return None
    
    grade_int = int(grade_num)
    
    if grade_int < 0:
        return "PK"
    elif grade_int == 0:
        return "K"
    else:
        return str(grade_int)


def format_birth_date(birth_date_str):
    """
    Convert birth date from HubSpot format (MM-DD-YYYY) to TimeBack format (YYYY-MM-DD).
    
    Args:
        birth_date_str: Birth date string in MM-DD-YYYY format
        
    Returns:
        str: Birth date in YYYY-MM-DD format
    """
    if pd.isna(birth_date_str) or not birth_date_str:
        return None
    
    try:
        # Parse MM-DD-YYYY format
        date_obj = datetime.strptime(str(birth_date_str), "%m-%d-%Y")
        return date_obj.strftime("%Y-%m-%d")
    except ValueError:
        # Try other formats if needed
        try:
            date_obj = datetime.strptime(str(birth_date_str), "%Y-%m-%d")
            return date_obj.strftime("%Y-%m-%d")
        except ValueError:
            return None


def create_account_payload(student_row):
    """
    Create account creation payload for TimeBack API.
    
    Args:
        student_row: pandas Series with student data
        
    Returns:
        dict: Account creation payload
    """
    # Get email (use primary email if available, otherwise email)
    email = student_row.get('hs_primary_email') or student_row.get('hs_email')
    
    # Generate UUID for sourcedId
    sourced_id = str(uuid.uuid4())
    
    # Get names
    given_name = student_row.get('hs_firstname', '')
    family_name = student_row.get('hs_lastname', '')
    
    # Get grade (current grade = last completed + 1)
    last_completed_grade = pd.to_numeric(student_row.get('hs_StudentGradeNum'), errors='coerce')
    current_grade = last_completed_grade + 1 if not pd.isna(last_completed_grade) else None
    grade_str = convert_grade_to_string(current_grade)
    
    # Get birth date
    birth_date = format_birth_date(student_row.get('hs_students_birthdate'))
    
    payload = {
        "student": {
            "sourcedId": sourced_id,
            "email": email,
            "username": email,
            "status": "active",
            "enabledUser": "true",
            "givenName": given_name,
            "familyName": family_name,
            "preferredFirstName": given_name,
            "grades": [grade_str] if grade_str else [],
            "primaryOrg": {
                "href": TIMEBACK_ORG_HREF,
                "sourcedId": TIMEBACK_ORG_SOURCED_ID,
                "type": "org"
            },
            "demographics": {
                "birthDate": birth_date
            } if birth_date else {}
        }
    }
    
    return payload


def create_app_assignment_payload(user_id, app_id, app_name):
    """
    Create app assignment payload for TimeBack API.
    
    Args:
        user_id: User sourcedId (from account creation)
        app_id: Application sourcedId
        app_name: Application name
        
    Returns:
        dict: App assignment payload
    """
    profile_id = str(uuid.uuid4())
    
    payload = {
        "profileId": profile_id,
        "applicationId": app_id,
        "profileType": "learning_app_profile",
        "vendorId": "alpha",
        "description": f"Automated assignment via TimeBack Platform API - {app_name}"
    }
    
    return payload


def create_assessment_assignment_payload(user_id, assessment_id, assessment_name):
    """
    Create assessment assignment payload for TimeBack API.
    
    Args:
        user_id: User sourcedId (from account creation)
        assessment_id: Assessment sourcedId
        assessment_name: Assessment name
        
    Returns:
        dict: Assessment assignment payload
    """
    profile_id = str(uuid.uuid4())
    
    payload = {
        "profileId": profile_id,
        "applicationId": assessment_id,
        "profileType": "learning_app_profile",
        "vendorId": "alpha",
        "description": f"Automated assessment assignment - {assessment_name}"
    }
    
    return payload


def process_student(student_row, config_df, assessments_df, apps_dict):
    """
    Process a single student to prepare all payloads (no API calls).
    
    Args:
        student_row: pandas Series with student data
        config_df: Segment configuration DataFrame
        assessments_df: Assessment IDs DataFrame
        apps_dict: Dictionary mapping app name → app ID
        
    Returns:
        dict: Result dictionary containing:
            - account_payload: Account creation payload
            - app_assignment: App assignment payload (or None)
            - app_name: Name of app to assign
            - app_id: ID of app to assign
            - assessment_assignments: List of assessment assignment payloads
            - email: Student email
            - segment: Segment name
            - grade: Current grade
            - errors: List of any errors encountered
    """
    result = {
        "account_payload": None,
        "app_assignment": None,
        "app_name": None,
        "app_id": None,
        "assessment_assignments": [],
        "email": None,
        "segment": None,
        "grade": None,
        "signup_date": None,  # Add signup date for tracker creation
        "errors": []
    }
    
    try:
        # Get student info
        email = student_row.get('hs_primary_email') or student_row.get('hs_email')
        segment_name = student_row.get('segment_name')
        last_completed_grade = pd.to_numeric(student_row.get('hs_StudentGradeNum'), errors='coerce')
        current_grade = last_completed_grade + 1 if not pd.isna(last_completed_grade) else None
        
        # Get signup date (hs_added_at is Unix timestamp in milliseconds)
        signup_timestamp = student_row.get('hs_added_at')
        if signup_timestamp and not pd.isna(signup_timestamp):
            signup_date = datetime.fromtimestamp(signup_timestamp / 1000)
        else:
            signup_date = datetime.now()
        
        # Get student name
        first_name = student_row.get('hs_firstname', '')
        last_name = student_row.get('hs_lastname', '')
        full_name = f"{first_name} {last_name}".strip() if first_name or last_name else ''
        
        result["email"] = email
        result["segment"] = segment_name
        result["grade"] = current_grade
        result["signup_date"] = signup_date
        result["name"] = full_name
        result["first_name"] = first_name
        
        # Create account payload
        account_payload = create_account_payload(student_row)
        result["account_payload"] = account_payload
        user_id = account_payload["student"]["sourcedId"]
        
        # Look up segment in config to get app name
        segment_config = config_df[config_df['segment'] == segment_name]
        if segment_config.empty:
            result["errors"].append(f"Segment '{segment_name}' not found in config")
            return result
        
        segment_row = segment_config.iloc[0]
        app_name = segment_row.get('app')
        assessments_enabled = segment_row.get('assessments', 0) == 1.0
        
        if not app_name:
            result["errors"].append(f"No app specified for segment '{segment_name}'")
            return result
        
        # Get app ID from apps_dict
        app_id = apps_dict.get(app_name)
        if not app_id:
            result["errors"].append(f"App '{app_name}' not found in TimeBack applications")
            return result
        
        result["app_name"] = app_name
        result["app_id"] = app_id
        
        # Create app assignment payload
        app_assignment = create_app_assignment_payload(user_id, app_id, app_name)
        result["app_assignment"] = app_assignment
        
        # Create assessment assignment payloads if assessments are enabled
        if assessments_enabled:
            # Filter assessments for this segment and grade
            # Empty grade (NaN) means all students in that segment get the assessment regardless of grade
            # If assessment grade is NaN, assign it regardless of student grade
            # Otherwise, only assign if assessment grade matches student's current grade
            if current_grade is not None:
                grade_filter = assessments_df['grade'].isna() | (assessments_df['grade'] == current_grade)
            else:
                # If student grade is unknown, only assign assessments with empty grade (NaN)
                grade_filter = assessments_df['grade'].isna()
            
            # Filter by segment if segment column exists
            if 'segment' in assessments_df.columns:
                segment_filter = assessments_df['segment'] == segment_name
                matching_assessments = assessments_df[grade_filter & segment_filter]
            else:
                # If no segment column, use grade filter only
                matching_assessments = assessments_df[grade_filter]
            
            for _, assessment_row in matching_assessments.iterrows():
                # Use the actual column names from the sheet, with fallbacks for backward compatibility
                assessment_id = (
                    assessment_row.get('initial_assessment_id')
                    or assessment_row.get('ID')
                    or assessment_row.get('id')
                )
                assessment_name = (
                    assessment_row.get('assessment_name', '')
                    or assessment_row.get('assessment', '')
                    or assessment_row.get('name', '')
                )
                
                # Skip if assessment ID is missing
                if not assessment_id or pd.isna(assessment_id):
                    result["errors"].append(f"Assessment '{assessment_name}' missing ID, skipping")
                    continue
                
                assessment_payload = create_assessment_assignment_payload(
                    user_id, 
                    str(assessment_id), 
                    assessment_name
                )
                result["assessment_assignments"].append(assessment_payload)
    
    except Exception as e:
        result["errors"].append(f"Error processing student: {str(e)}")
    
    return result


def process_all_students(df_filtered_leads):
    """
    Process all filtered students to prepare payloads (no API calls).
    
    Args:
        df_filtered_leads: DataFrame with filtered leads ready for processing
        
    Returns:
        list: List of result dictionaries, one per student
    """
    # Load configuration data ONCE
    print("Loading configuration data...")
    config_df, assessments_df, apps_dict = load_configuration_data()
    print(f"Loaded {len(config_df)} segment configurations")
    print(f"Loaded {len(assessments_df)} assessment configurations")
    print(f"Loaded {len(apps_dict)} applications from TimeBack API")
    
    # Process each student
    all_results = []
    for idx, student_row in df_filtered_leads.iterrows():
        result = process_student(student_row, config_df, assessments_df, apps_dict)
        all_results.append(result)
    
    # Print summary
    total_accounts = len([r for r in all_results if r["account_payload"]])
    total_app_assignments = len([r for r in all_results if r["app_assignment"]])
    total_assessment_assignments = sum(len(r["assessment_assignments"]) for r in all_results)
    total_errors = sum(len(r["errors"]) for r in all_results)
    
    print(f"\nProcessing Summary:")
    print(f"  Account payloads prepared: {total_accounts}")
    print(f"  App assignments prepared: {total_app_assignments}")
    print(f"  Assessment assignments prepared: {total_assessment_assignments}")
    print(f"  Total errors: {total_errors}")
    
    return all_results
