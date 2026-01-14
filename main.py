import pandas as pd
import time
from datetime import timedelta
from s3_functions import get_leads, get_accounts
from filter_functions import filter_leads_without_accounts, filter_leads_by_date, filter_blacklisted_emails, filter_leads_by_grade_level, filter_leads_by_active_segments
from processing_functions import process_all_students
from execution_functions import execute_and_log, prepare_summary_data
from google_chat_notifications import notify_automation_start, notify_automation_complete, notify_automation_error
from hubspot_functions import update_hubspot_contacts_batch
from utils import validate_environment_variables
import config

def main():
    start_time = time.time()
    webhook_url = config.GOOGLE_CHAT_WEBHOOK_URL
    
    try:
        # Validate environment variables before starting
        print("Validating environment variables...")
        validate_environment_variables()
        print("✓ Environment variables validated")
        
        # Get leads and accounts as dataframes
        df_leads = get_leads()
        df_accounts = get_accounts()
        
        # Filter out leads that already have accounts
        df_filtered_leads = filter_leads_without_accounts(df_leads, df_accounts)
        
        # Filter out leads older than 2 weeks
        df_filtered_leads = filter_leads_by_date(df_filtered_leads, days_threshold=14)
        
        # Filter out blacklisted emails
        df_filtered_leads = filter_blacklisted_emails(df_filtered_leads)
        
        # Filter out leads with unacceptable grade levels
        df_filtered_leads = filter_leads_by_grade_level(df_filtered_leads)
        
        # Filter out leads from inactive segments
        df_filtered_leads = filter_leads_by_active_segments(df_filtered_leads)
        
        # TESTING: Random selector to limit number of leads for testing
        # Comment out this block for production
        TEST_LIMIT = 1
        if len(df_filtered_leads) > TEST_LIMIT:
            df_filtered_leads = df_filtered_leads.sample(n=TEST_LIMIT, random_state=123)
            print(f"TESTING MODE: Limited to {TEST_LIMIT} leads for testing")
        
        # Empty data handling: Check if we have any leads to process
        total_students = len(df_filtered_leads)
        print(f"Leads to process: {total_students}")
        
        if total_students == 0:
            print("No leads to process after filtering. Exiting gracefully.")
            # Send notification that automation completed with no leads
            notify_automation_complete(webhook_url, {
                'total_leads': 0,
                'accounts_created': 0,
                'accounts_failed': 0,
                'apps_assigned': 0,
                'apps_failed': 0,
                'assessments_assigned': 0,
                'assessments_failed': 0,
                'success_details': [],
                'failure_details': []
            }, "0:00:00")
            return
        
        # Send startup notification
        notify_automation_start(webhook_url, total_students)
        
        # Process all filtered students (prepare payloads, no API calls)
        all_results = process_all_students(df_filtered_leads)
        
        # Empty data handling: Check if processing returned any results
        if not all_results or len(all_results) == 0:
            print("No results from processing phase. Exiting gracefully.")
            execution_time_seconds = time.time() - start_time
            execution_time = str(timedelta(seconds=int(execution_time_seconds)))
            notify_automation_complete(webhook_url, {
                'total_leads': total_students,
                'accounts_created': 0,
                'accounts_failed': 0,
                'apps_assigned': 0,
                'apps_failed': 0,
                'assessments_assigned': 0,
                'assessments_failed': 0,
                'success_details': [],
                'failure_details': []
            }, execution_time)
            return
        
        # TESTING MODE: Set to True to skip TimeBack account creation but still test trackers and HubSpot
        # This allows testing tracker creation and HubSpot updates without creating real accounts
        SKIP_ACCOUNT_CREATION = True  # Set to False for production
        
        # Execute API calls to create accounts and assignments
        execution_summary, success_logs, fail_logs, tracker_results, student_data_dict = execute_and_log(
            all_results, 
            skip_account_creation=SKIP_ACCOUNT_CREATION
        )
        
        # Update HubSpot contacts with tracker links (triggers workflow email)
        hubspot_summary = update_hubspot_contacts_batch(tracker_results)
        
        # Calculate execution time
        execution_time_seconds = time.time() - start_time
        execution_time = str(timedelta(seconds=int(execution_time_seconds)))
        
        # Prepare summary data
        summary_data = prepare_summary_data(execution_summary, success_logs, fail_logs, total_students)
        
        # Send summary notification
        notify_automation_complete(webhook_url, summary_data, execution_time)
    
    except Exception as e:
        error_message = f"An error occurred during automation execution:\n{str(e)}"
        print(f"❌ Error: {error_message}")
        
        # Send error notification
        notify_automation_error(webhook_url, error_message)
        
        raise

if __name__ == '__main__':
    main()