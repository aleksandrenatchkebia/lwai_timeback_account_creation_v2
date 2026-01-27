import pandas as pd
from datetime import datetime
from google_sheets_functions import authenticate_google_sheets, open_spreadsheet, get_worksheet, read_worksheet_to_dataframe, copy_spreadsheet
import config


def load_program_trackers():
    """
    Load program tracker templates from the program_trackers worksheet.
    
    Returns:
        DataFrame with program tracker information (columns likely include segment, tracker_url, etc.)
    """
    client = authenticate_google_sheets()
    spreadsheet = open_spreadsheet(client, spreadsheet_id=config.APP_IDS_GSHEET)
    trackers_worksheet = get_worksheet(spreadsheet, worksheet_name='program_trackers')
    df_trackers = read_worksheet_to_dataframe(trackers_worksheet, header_row=0)
    
    return df_trackers


def extract_spreadsheet_id_from_url(url):
    """
    Extract spreadsheet ID from a Google Sheets URL.
    
    Args:
        url: Google Sheets URL (full URL or just ID)
        
    Returns:
        str: Spreadsheet ID
    """
    # If it's already just an ID, return it
    if len(url) == 44 and url.replace('-', '').replace('_', '').isalnum():
        return url
    
    # Extract ID from URL
    # Format: https://docs.google.com/spreadsheets/d/{ID}/...
    if '/spreadsheets/d/' in url:
        start = url.find('/spreadsheets/d/') + len('/spreadsheets/d/')
        end = url.find('/', start)
        if end == -1:
            end = url.find('?', start)
            if end == -1:
                end = len(url)
        return url[start:end]
    
    # If URL format is different, try to extract
    # Could be: https://docs.google.com/spreadsheets/d/{ID}/edit
    if 'docs.google.com' in url:
        parts = url.split('/')
        for i, part in enumerate(parts):
            if part == 'd' and i + 1 < len(parts):
                return parts[i + 1].split('?')[0].split('#')[0]
    
    return url


def create_tracker_copy_by_app(student_email, app_name, signup_date, df_trackers, client, segment=None, current_grade=None):
    """
    Create a copy of the tracker spreadsheet for a student.
    
    Args:
        student_email: Student's email address
        app_name: App name (e.g., "Athena", "TrashCat")
        signup_date: Date when lead signed up (datetime object or string)
        df_trackers: DataFrame with program tracker information
        client: gspread Client object
        segment: Optional segment name to match against 'Segment' column
        current_grade: Optional current grade (last completed + 1) to match against 'Grade' column
        
    Returns:
        tuple: (success: bool, tracker_url: str, error_message: str)
    """
    try:
        # Start with all trackers for this app
        app_trackers = df_trackers[df_trackers['App'] == app_name]
        
        if app_trackers.empty:
            return False, None, f"No tracker template found for app '{app_name}'"
        
        # Multi-level matching with fallback:
        # 1. Try App + Segment + Grade (if all available)
        # 2. Try App + Segment (if Segment available)
        # 3. Try App only (fallback)
        
        tracker_row = None
        
        # Check if Segment and Grade columns exist
        has_segment_col = 'Segment' in df_trackers.columns
        has_grade_col = 'Grade' in df_trackers.columns
        
        # Level 1: Try App + Segment + Grade match
        if has_segment_col and has_grade_col and segment is not None and current_grade is not None:
            # Filter by Segment and Grade
            segment_match = app_trackers['Segment'].fillna('').astype(str).str.strip() == str(segment).strip()
            grade_match = pd.to_numeric(app_trackers['Grade'], errors='coerce') == current_grade
            
            # Only match rows where Segment and Grade are both specified (not NaN/empty)
            segment_specified = app_trackers['Segment'].notna() & (app_trackers['Segment'].astype(str).str.strip() != '')
            grade_specified = app_trackers['Grade'].notna()
            
            # Match where Segment and Grade match AND are specified
            exact_match = segment_match & grade_match & segment_specified & grade_specified
            
            if exact_match.any():
                matching_trackers = app_trackers[exact_match]
                # Get first match with non-empty tracker URL
                for idx, row in matching_trackers.iterrows():
                    tracker_url = row.get('Tracker') or row.get('tracker') or row.get('tracker_url')
                    if tracker_url and pd.notna(tracker_url) and str(tracker_url).strip():
                        tracker_row = row
                        break
        
        # Level 2: Try App + Segment match (if Level 1 didn't find anything)
        if tracker_row is None and has_segment_col and segment is not None:
            segment_match = app_trackers['Segment'].fillna('').astype(str).str.strip() == str(segment).strip()
            segment_specified = app_trackers['Segment'].notna() & (app_trackers['Segment'].astype(str).str.strip() != '')
            
            # Match where Segment matches AND is specified (Grade can be NaN/empty)
            segment_only_match = segment_match & segment_specified
            
            if segment_only_match.any():
                matching_trackers = app_trackers[segment_only_match]
                # Get first match with non-empty tracker URL
                for idx, row in matching_trackers.iterrows():
                    tracker_url = row.get('Tracker') or row.get('tracker') or row.get('tracker_url')
                    if tracker_url and pd.notna(tracker_url) and str(tracker_url).strip():
                        tracker_row = row
                        break
        
        # Level 3: Fallback to App only (if previous levels didn't find anything)
        if tracker_row is None:
            # Get the first non-empty tracker URL for this app (ignoring Segment/Grade)
            for idx, row in app_trackers.iterrows():
                tracker_url = row.get('Tracker') or row.get('tracker') or row.get('tracker_url')
                if tracker_url and pd.notna(tracker_url) and str(tracker_url).strip():
                    tracker_row = row
                    break
        
        if tracker_row is None:
            return False, None, f"No tracker URL found for app '{app_name}'"
        
        tracker_url = tracker_row.get('Tracker') or tracker_row.get('tracker') or tracker_row.get('tracker_url')
        
        # Extract spreadsheet ID from URL
        source_spreadsheet_id = extract_spreadsheet_id_from_url(str(tracker_url))
        
        # Get the actual title of the source spreadsheet
        source_spreadsheet = client.open_by_key(source_spreadsheet_id)
        original_title = source_spreadsheet.title
        
        # Format signup date
        if isinstance(signup_date, datetime):
            signup_date_str = signup_date.strftime('%Y-%m-%d')
        else:
            signup_date_str = str(signup_date)
        
        # Create new title replacing [Student Name] with email
        if '[Student Name]' in original_title:
            new_title = original_title.replace('[Student Name]', student_email)
        else:
            # If no [Student Name] placeholder, append email to title
            new_title = f"{original_title} - {student_email}"
        
        # Copy the spreadsheet
        destination_folder_id = config.PROGRAM_TRACKERS_FOLDER
        copied_spreadsheet = copy_spreadsheet(
            client=client,
            source_spreadsheet_id=source_spreadsheet_id,
            new_title=new_title,
            destination_folder_id=destination_folder_id
        )
        
        # Fill in cells B2 (email) and B3 (signup date)
        # Get the first worksheet (or a specific one if needed)
        worksheet = copied_spreadsheet.get_worksheet(0)
        
        # Update B2 with email (using update_acell for single cell updates)
        worksheet.update_acell('B2', student_email)
        
        # Update B3 with signup date
        worksheet.update_acell('B3', signup_date_str)
        
        # Share the spreadsheet with the student's email (without notification)
        try:
            from googleapiclient.discovery import build
            from google.oauth2.service_account import Credentials
            import os
            import json
            from dotenv import load_dotenv
            
            load_dotenv()
            gcp_cred_json = os.getenv('GCP_CRED')
            if gcp_cred_json:
                creds_info = json.loads(gcp_cred_json)
                creds = Credentials.from_service_account_info(creds_info)
                # Build Drive API service - discovery documents should be cached in google-api-python-client
                drive_service = build('drive', 'v3', credentials=creds)
                
                # Create permission for the student's email
                permission = {
                    'type': 'user',
                    'role': 'writer',  # Give them edit access
                    'emailAddress': student_email
                }
                
                # Share without sending notification email
                drive_service.permissions().create(
                    fileId=copied_spreadsheet.id,
                    body=permission,
                    sendNotificationEmail=False,
                    supportsAllDrives=True
                ).execute()
        except Exception as e:
            # Log but don't fail - sharing is best effort
            print(f"Warning: Could not share tracker with {student_email}: {e}")
        
        # Get the URL of the copied spreadsheet
        tracker_url = f"https://docs.google.com/spreadsheets/d/{copied_spreadsheet.id}"
        
        return True, tracker_url, None
    
    except Exception as e:
        return False, None, str(e)


def create_trackers_for_students(success_logs, student_data_dict, config_df=None):
    """
    Create tracker spreadsheets for all students who successfully got accounts.
    
    Args:
        success_logs: List of success log dictionaries from execution
        student_data_dict: Dictionary mapping email to student data (for signup date and grade)
            Format: {email: {'signup_date': datetime, 'segment': str, 'grade': int, ...}}
        config_df: Optional DataFrame with segment configuration (to map segment to app name)
        
    Returns:
        list: List of dictionaries with tracker creation results
            Format: [{'email': str, 'segment': str, 'course_grade': str, 'tracker_link': str, 'success': bool, 'error': str}, ...]
    """
    client = authenticate_google_sheets()
    df_trackers = load_program_trackers()
    
    # Load config if not provided (to map segment to app)
    if config_df is None:
        spreadsheet = open_spreadsheet(client, spreadsheet_id=config.APP_IDS_GSHEET)
        main_config_worksheet = get_worksheet(spreadsheet, worksheet_name='main_config')
        config_df = read_worksheet_to_dataframe(main_config_worksheet, header_row=0)
    
    tracker_results = []
    
    for log in success_logs:
        email = log.get('email')
        segment = log.get('segment')
        grade = log.get('grade')
        
        if not email or not segment:
            tracker_results.append({
                'email': email or 'Unknown',
                'segment': segment or 'Unknown',
                'course_grade': None,
                'tracker_link': None,
                'success': False,
                'error': 'Missing email or segment in log'
            })
            continue
        
        # Get app name from segment using config_df
        segment_config = config_df[config_df['segment'] == segment]
        if segment_config.empty:
            tracker_results.append({
                'email': email,
                'segment': segment,
                'course_grade': None,
                'tracker_link': None,
                'success': False,
                'error': f"Segment '{segment}' not found in config"
            })
            continue
        
        app_name = segment_config.iloc[0].get('app')
        
        # Get signup date from student_data_dict
        student_data = student_data_dict.get(email, {})
        signup_date = student_data.get('signup_date')
        
        if not signup_date:
            signup_date = datetime.now()  # Fallback to current date
        
        # Format course/grade
        if grade is not None:
            course_grade = f"Grade {int(grade)}"
        else:
            course_grade = "Unknown"
        
        # Create tracker copy using app name, segment, and current grade to find tracker
        # Note: grade here is already current_grade (last_completed + 1) from processing phase
        success, tracker_url, error = create_tracker_copy_by_app(
            student_email=email,
            app_name=app_name,
            signup_date=signup_date,
            df_trackers=df_trackers,
            client=client,
            segment=segment,
            current_grade=int(grade) if grade is not None else None
        )
        
        tracker_results.append({
            'email': email,
            'segment': segment,
            'course_grade': course_grade,
            'tracker_link': tracker_url if success else None,
            'success': success,
            'error': error
        })
    
    return tracker_results


def write_trackers_to_sheet(tracker_results):
    """
    Write tracker results to the all_trackers worksheet in batch.
    
    Args:
        tracker_results: List of tracker result dictionaries with:
            - email: str
            - segment: str
            - course_grade: str
            - tracker_link: str
            - success: bool
    """
    from google_sheets_functions import open_spreadsheet, get_worksheet, read_worksheet_to_dataframe, write_dataframe_to_worksheet
    
    client = authenticate_google_sheets()
    spreadsheet = open_spreadsheet(client, spreadsheet_id=config.APP_IDS_GSHEET)
    
    # Get all_trackers worksheet
    trackers_worksheet = get_worksheet(spreadsheet, worksheet_name='all_trackers')
    
    # Read existing data
    try:
        existing_trackers = read_worksheet_to_dataframe(trackers_worksheet, header_row=0)
    except:
        existing_trackers = pd.DataFrame()
    
    # Filter to only successful trackers for writing
    successful_trackers = [tr for tr in tracker_results if tr.get('success', False)]
    
    if not successful_trackers:
        return
    
    # Create DataFrame from successful trackers
    current_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    new_trackers_data = []
    for tr in successful_trackers:
        new_trackers_data.append({
            'email': tr.get('email'),
            'segment': tr.get('segment'),
            'course_grade': tr.get('course_grade'),
            'tracker_link': tr.get('tracker_link'),
            'added_timestamp': current_timestamp
        })
    
    new_trackers_df = pd.DataFrame(new_trackers_data)
    
    # Append new trackers to existing
    if not existing_trackers.empty:
        combined_trackers = pd.concat([existing_trackers, new_trackers_df], ignore_index=True)
    else:
        combined_trackers = new_trackers_df
    
    # Write back to Google Sheets
    write_dataframe_to_worksheet(trackers_worksheet, combined_trackers, row=1, col=1, 
                                 include_index=False, include_column_header=True, resize=True)
