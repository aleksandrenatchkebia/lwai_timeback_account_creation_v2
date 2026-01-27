import gspread
from gspread_dataframe import get_as_dataframe, set_with_dataframe
import pandas as pd
from google.oauth2.service_account import Credentials
import json
import os
from dotenv import load_dotenv

def authenticate_google_sheets():
    """
    Authenticate with Google Sheets API using service account credentials from .env file.
    
    Returns:
        gspread Client object
    """
    load_dotenv()
    
    scope = ['https://spreadsheets.google.com/feeds',
             'https://www.googleapis.com/auth/drive']
    
    # Get credentials from .env file
    gcp_cred_json = os.getenv('GCP_CRED')
    if not gcp_cred_json:
        raise ValueError("GCP_CRED not found in .env file")
    
    # Parse the JSON string and create credentials
    creds_info = json.loads(gcp_cred_json)
    creds = Credentials.from_service_account_info(creds_info, scopes=scope)
    client = gspread.authorize(creds)
    
    return client


def open_spreadsheet(client, spreadsheet_id=None, spreadsheet_name=None):
    """
    Open a Google Spreadsheet by ID or name.
    
    Args:
        client: gspread Client object
        spreadsheet_id: Google Spreadsheet ID (takes precedence)
        spreadsheet_name: Name of the spreadsheet
        
    Returns:
        gspread Spreadsheet object
    """
    if spreadsheet_id:
        return client.open_by_key(spreadsheet_id)
    elif spreadsheet_name:
        return client.open(spreadsheet_name)
    else:
        raise ValueError("Either spreadsheet_id or spreadsheet_name must be provided")


def get_worksheet(spreadsheet, worksheet_name=None, worksheet_index=0):
    """
    Get a worksheet from a spreadsheet.
    
    Args:
        spreadsheet: gspread Spreadsheet object
        worksheet_name: Name of the worksheet (takes precedence)
        worksheet_index: Index of the worksheet (default: 0 for first sheet)
        
    Returns:
        gspread Worksheet object
    """
    if worksheet_name:
        return spreadsheet.worksheet(worksheet_name)
    else:
        return spreadsheet.get_worksheet(worksheet_index)


def read_worksheet_to_dataframe(worksheet, header_row=1, evaluate_formulas=True):
    """
    Read a Google Sheet worksheet into a pandas DataFrame.
    
    Args:
        worksheet: gspread Worksheet object
        header_row: Row number to use as header (1-indexed, default: 1)
        evaluate_formulas: Whether to evaluate formulas (default: True)
        
    Returns:
        pandas DataFrame
    """
    df = get_as_dataframe(worksheet, header=header_row, evaluate_formulas=evaluate_formulas)
    # Remove completely empty rows
    df = df.dropna(how='all')
    return df


def write_dataframe_to_worksheet(worksheet, df, row=1, col=1, include_index=False, include_column_header=True, resize=True):
    """
    Write a pandas DataFrame to a Google Sheet worksheet.
    
    Args:
        worksheet: gspread Worksheet object
        df: pandas DataFrame to write
        row: Starting row (1-indexed, default: 1)
        col: Starting column (1-indexed, default: 1)
        include_index: Whether to include DataFrame index (default: False)
        include_column_header: Whether to include column headers (default: True)
        resize: Whether to resize the worksheet to fit the data (default: True)
        
    Returns:
        gspread Worksheet object
    """
    set_with_dataframe(worksheet, df, row=row, col=col, 
                      include_index=include_index, 
                      include_column_header=include_column_header,
                      resize=resize)
    return worksheet


def create_worksheet(spreadsheet, worksheet_name, rows=1000, cols=26):
    """
    Create a new worksheet in a spreadsheet.
    
    Args:
        spreadsheet: gspread Spreadsheet object
        worksheet_name: Name for the new worksheet
        rows: Number of rows (default: 1000)
        cols: Number of columns (default: 26)
        
    Returns:
        gspread Worksheet object
    """
    worksheet = spreadsheet.add_worksheet(title=worksheet_name, rows=rows, cols=cols)
    return worksheet


def clear_worksheet(worksheet):
    """
    Clear all data from a worksheet.
    
    Args:
        worksheet: gspread Worksheet object
        
    Returns:
        gspread Worksheet object
    """
    worksheet.clear()
    return worksheet


def copy_spreadsheet(client, source_spreadsheet_id, new_title, destination_folder_id=None):
    """
    Create a copy of a Google Spreadsheet.
    
    Args:
        client: gspread Client object
        source_spreadsheet_id: ID of the source spreadsheet to copy
        new_title: Title for the new copied spreadsheet
        destination_folder_id: Optional folder ID to copy the spreadsheet into
        
    Returns:
        gspread Spreadsheet object (the copy)
    """
    # Use Google Drive API to copy the file
    from googleapiclient.discovery import build
    from google.oauth2.service_account import Credentials
    import os
    import json
    from dotenv import load_dotenv
    
    load_dotenv()
    
    # Get credentials
    gcp_cred_json = os.getenv('GCP_CRED')
    if not gcp_cred_json:
        raise ValueError("GCP_CRED not found in .env file")
    
    creds_info = json.loads(gcp_cred_json)
    creds = Credentials.from_service_account_info(creds_info)
    
    # Build Drive API service
    # Note: For Shared Drives, files created by service accounts use the Shared Drive's quota
    # No domain-wide delegation or ownership transfer needed
    # Build Drive API service - discovery documents should be cached in google-api-python-client
    drive_service = build('drive', 'v3', credentials=creds)
    
    # Copy the file
    copied_file = {'name': new_title}
    if destination_folder_id:
        copied_file['parents'] = [destination_folder_id]
    
    # Copy the file - use supportsAllDrives for Shared Drive support
    file_copy = drive_service.files().copy(
        fileId=source_spreadsheet_id,
        body=copied_file,
        supportsAllDrives=True
    ).execute()
    
    copied_spreadsheet_id = file_copy['id']
    
    # Note: If using a Shared Drive, files are owned by the Shared Drive
    # and use the Shared Drive's storage quota, not individual user quotas
    # No ownership transfer needed for Shared Drives
    
    # Open the copied spreadsheet with gspread
    copied_spreadsheet = client.open_by_key(copied_spreadsheet_id)
    
    return copied_spreadsheet
