import pandas as pd
from datetime import datetime, timedelta
from google_sheets_functions import authenticate_google_sheets, open_spreadsheet, get_worksheet, read_worksheet_to_dataframe
import config

def filter_leads_without_accounts(df_leads, df_accounts):
    """
    Filter out leads that already have accounts in TimeBack.
    
    A lead is considered to have an account if their email (hs_email or hs_primary_email)
    matches an email in the accounts dataframe (tb_email).
    
    Args:
        df_leads: DataFrame containing leads from HubSpot
        df_accounts: DataFrame containing existing TimeBack accounts
        
    Returns:
        DataFrame containing only leads that don't have existing accounts
    """
    # Get all unique emails from accounts
    account_emails = set(df_accounts['tb_email'].dropna().str.lower().unique())
    
    # Check if lead's email (hs_email or hs_primary_email) exists in accounts
    # Use hs_primary_email if available, otherwise fall back to hs_email
    lead_emails = df_leads['hs_primary_email'].fillna(df_leads['hs_email']).str.lower()
    
    # Filter leads where email is not in accounts
    mask = ~lead_emails.isin(account_emails)
    df_filtered_leads = df_leads[mask].copy()
    
    return df_filtered_leads


def filter_leads_by_date(df_leads, days_threshold=14):
    """
    Filter out leads that are older than the specified number of days.
    
    Uses the 'hs_added_at' field which contains Unix timestamps in milliseconds
    representing when the lead was added to HubSpot.
    
    Args:
        df_leads: DataFrame containing leads from HubSpot
        days_threshold: Number of days threshold (default: 14 for 2 weeks)
        
    Returns:
        DataFrame containing only leads added within the threshold period
    """
    # Calculate cutoff date (days_threshold days ago from today)
    cutoff_date = datetime.now() - timedelta(days=days_threshold)
    cutoff_timestamp = int(cutoff_date.timestamp() * 1000)  # Convert to milliseconds
    
    # Convert hs_added_at to datetime for filtering
    # Filter leads where hs_added_at is greater than or equal to cutoff (i.e., not older than threshold)
    # Also filter out any invalid dates (e.g., dates before 2000 which seem like bad data)
    min_valid_date = datetime(2000, 1, 1).timestamp() * 1000
    mask = (df_leads['hs_added_at'] >= cutoff_timestamp) & (df_leads['hs_added_at'] >= min_valid_date)
    
    df_filtered_leads = df_leads[mask].copy()
    
    return df_filtered_leads


def filter_blacklisted_emails(df_leads):
    """
    Filter out leads whose emails are in the blacklist Google Sheet.
    
    Reads the blacklist worksheet from the Google Sheet defined in config.APP_IDS_GSHEET
    and filters out any leads whose email matches a blacklisted email.
    
    Args:
        df_leads: DataFrame containing leads from HubSpot
        
    Returns:
        DataFrame containing only leads that are not blacklisted
    """
    # Authenticate and get blacklist from Google Sheets
    client = authenticate_google_sheets()
    spreadsheet = open_spreadsheet(client, spreadsheet_id=config.APP_IDS_GSHEET)
    blacklist_worksheet = get_worksheet(spreadsheet, worksheet_name='blacklist')
    df_blacklist = read_worksheet_to_dataframe(blacklist_worksheet)
    
    # Get blacklisted emails - assume first column contains emails
    # Convert to lowercase for case-insensitive matching
    blacklist_emails = set(df_blacklist.iloc[:, 0].dropna().astype(str).str.lower().unique())
    
    # Get lead emails (use hs_primary_email if available, otherwise hs_email)
    lead_emails = df_leads['hs_primary_email'].fillna(df_leads['hs_email']).str.lower()
    
    # Filter leads where email is not in blacklist
    mask = ~lead_emails.isin(blacklist_emails)
    df_filtered_leads = df_leads[mask].copy()
    
    return df_filtered_leads


def filter_leads_by_grade_level(df_leads):
    """
    Filter out leads whose current grade level is not within their segment's acceptable range.
    
    Reads grade level ranges from the main_config worksheet (min_grade and max_grade).
    HubSpot provides last completed grade level, so current grade = last completed + 1.
    Only keeps leads where current grade falls within their specific segment's grade range.
    
    Args:
        df_leads: DataFrame containing leads from HubSpot
        
    Returns:
        DataFrame containing only leads with acceptable grade levels for their segment
    """
    # Authenticate and get grade level ranges from Google Sheets
    client = authenticate_google_sheets()
    spreadsheet = open_spreadsheet(client, spreadsheet_id=config.APP_IDS_GSHEET)
    config_worksheet = get_worksheet(spreadsheet, worksheet_name='main_config')
    df_config = read_worksheet_to_dataframe(config_worksheet, header_row=0)
    
    # Create a dictionary mapping segment to (min_grade, max_grade)
    segment_grade_ranges = {}
    for _, row in df_config.iterrows():
        segment = row.get('segment')
        min_grade = row.get('min_grade')
        max_grade = row.get('max_grade')
        if segment and pd.notna(min_grade) and pd.notna(max_grade):
            segment_grade_ranges[segment] = (int(min_grade), int(max_grade))
    
    # Get last completed grade level from leads (hs_StudentGradeNum)
    # Calculate current grade = last completed + 1
    last_completed_grade = pd.to_numeric(df_leads['hs_StudentGradeNum'], errors='coerce')
    current_grade = last_completed_grade + 1
    
    # Get segment name for each lead
    segment_name = df_leads.get('segment_name', pd.Series([None] * len(df_leads)))
    
    # Create a mask to filter leads where current grade is within their segment's acceptable range
    mask = pd.Series([False] * len(df_leads), index=df_leads.index)
    
    for idx in df_leads.index:
        grade = current_grade.loc[idx] if idx in current_grade.index else None
        seg = segment_name.loc[idx] if idx in segment_name.index else None
        
        if pd.isna(grade) or pd.isna(seg):
            continue
        
        # Look up the segment's grade range
        if seg in segment_grade_ranges:
            min_grade, max_grade = segment_grade_ranges[seg]
            if min_grade <= grade <= max_grade:
                mask.loc[idx] = True
    
    df_filtered_leads = df_leads[mask].copy()
    
    return df_filtered_leads


def filter_leads_by_active_segments(df_leads):
    """
    Filter out leads from segments that are not currently active.
    
    Reads the active column from the main_config worksheet. Only keeps leads
    from segments where active = 1 (or True).
    
    Args:
        df_leads: DataFrame containing leads from HubSpot
        
    Returns:
        DataFrame containing only leads from active segments
    """
    # Authenticate and get active segments from Google Sheets
    client = authenticate_google_sheets()
    spreadsheet = open_spreadsheet(client, spreadsheet_id=config.APP_IDS_GSHEET)
    config_worksheet = get_worksheet(spreadsheet, worksheet_name='main_config')
    df_config = read_worksheet_to_dataframe(config_worksheet, header_row=0)
    
    # Get active segments (where active = 1 or True)
    active_segments = df_config[df_config['active'] == 1.0]['segment'].tolist()
    
    # Filter leads to only keep those from active segments
    mask = df_leads['segment_name'].isin(active_segments)
    df_filtered_leads = df_leads[mask].copy()
    
    return df_filtered_leads
