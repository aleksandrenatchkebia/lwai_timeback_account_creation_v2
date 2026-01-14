"""
Google Chat Notifications Module

This module provides functions to send notifications to Google Chat
using webhook URLs for the TimeBack account creation automation.
"""

import requests
import json
from datetime import datetime
from typing import Dict, List, Optional


def send_google_chat_message(webhook_url: str, message: str, thread_key: Optional[str] = None) -> bool:
    """
    Send a message to Google Chat using a webhook URL.
    
    Args:
        webhook_url (str): The Google Chat webhook URL
        message (str): The message text to send
        thread_key (str, optional): Thread key to reply in the same thread
        
    Returns:
        bool: True if message was sent successfully, False otherwise
    """
    try:
        payload = {
            "text": message
        }
        
        # Add thread key if provided to keep messages in same thread
        if thread_key:
            payload["thread"] = {"name": thread_key}
        
        response = requests.post(
            webhook_url,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=10
        )
        
        response.raise_for_status()
        print(f"✅ Google Chat message sent successfully")
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to send Google Chat message: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error sending Google Chat message: {e}")
        return False


def format_summary_message(
    total_processed: int,
    successful_accounts: int,
    failed_accounts: int,
    success_details: List[Dict],
    failure_details: List[Dict],
    execution_time: Optional[str] = None
) -> str:
    """
    Format a summary message for Google Chat notification.
    
    Args:
        total_processed (int): Total number of students processed
        successful_accounts (int): Number of successful account creations
        failed_accounts (int): Number of failed account creations
        success_details (List[Dict]): List of success details
        failure_details (List[Dict]): List of failure details
        execution_time (str, optional): Total execution time
        
    Returns:
        str: Formatted message for Google Chat
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Calculate success rate
    success_rate = (successful_accounts / total_processed * 100) if total_processed > 0 else 0
    
    # Create the main message
    message = f"""🤖 *TimeBack Account Creation Automation - Summary*
📅 *Completed:* {timestamp}

📊 *Overall Results:*
• Total Processed: {total_processed}
• ✅ Successful: {successful_accounts}
• ❌ Failed: {failed_accounts}
• 📈 Success Rate: {success_rate:.1f}%"""

    if execution_time:
        message += f"\n• ⏱️ Execution Time: {execution_time}"

    # Add success details if any
    if success_details:
        message += f"\n\n✅ *Successful Accounts ({len(success_details)}):*"
        for detail in success_details[:10]:  # Show first 10
            email = detail.get('email', 'Unknown')
            app_name = detail.get('app_name', 'Unknown')
            message += f"\n• {email} → {app_name}"
        
        if len(success_details) > 10:
            message += f"\n• ... and {len(success_details) - 10} more"

    # Add failure details if any
    if failure_details:
        message += f"\n\n❌ *Failed Accounts ({len(failure_details)}):*"
        for detail in failure_details[:10]:  # Show first 10
            email = detail.get('email', 'Unknown')
            reason = detail.get('reason', 'Unknown error')
            message += f"\n• {email}: {reason}"
        
        if len(failure_details) > 10:
            message += f"\n• ... and {len(failure_details) - 10} more"

    # Add footer
    message += f"\n\n🔗 *Repository:* https://github.com/aleksandrenatchkebia/lwai_timeback_account_creation"
    
    return message


def send_automation_summary(
    webhook_url: str,
    total_processed: int,
    successful_accounts: int,
    failed_accounts: int,
    success_details: List[Dict],
    failure_details: List[Dict],
    execution_time: Optional[str] = None,
    thread_key: Optional[str] = None
) -> bool:
    """
    Send a comprehensive summary of the automation run to Google Chat.
    
    Args:
        webhook_url (str): The Google Chat webhook URL
        total_processed (int): Total number of students processed
        successful_accounts (int): Number of successful account creations
        failed_accounts (int): Number of failed account creations
        success_details (List[Dict]): List of success details
        failure_details (List[Dict]): List of failure details
        execution_time (str, optional): Total execution time
        thread_key (str, optional): Thread key to reply in the same thread
        
    Returns:
        bool: True if message was sent successfully, False otherwise
    """
    message = format_summary_message(
        total_processed=total_processed,
        successful_accounts=successful_accounts,
        failed_accounts=failed_accounts,
        success_details=success_details,
        failure_details=failure_details,
        execution_time=execution_time
    )
    
    return send_google_chat_message(webhook_url, message, thread_key)


def send_startup_notification(webhook_url: str, total_students: int, thread_key: Optional[str] = None) -> bool:
    """
    Send a notification when the automation starts.
    
    Args:
        webhook_url (str): The Google Chat webhook URL
        total_students (int): Total number of students to process
        thread_key (str, optional): Thread key to reply in the same thread
        
    Returns:
        bool: True if message was sent successfully, False otherwise
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    message = f"""🚀 *TimeBack Account Creation Automation - Started*
📅 *Started:* {timestamp}
👥 *Students to Process:* {total_students}

⏳ Processing in progress..."""

    return send_google_chat_message(webhook_url, message, thread_key)


def send_error_notification(webhook_url: str, error_message: str, thread_key: Optional[str] = None) -> bool:
    """
    Send an error notification to Google Chat.
    
    Args:
        webhook_url (str): The Google Chat webhook URL
        error_message (str): The error message to send
        thread_key (str, optional): Thread key to reply in the same thread
        
    Returns:
        bool: True if message was sent successfully, False otherwise
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    message = f"""🚨 *TimeBack Account Creation Automation - ERROR*
📅 *Time:* {timestamp}

❌ *Error Details:*
{error_message}

🔗 *Repository:* https://github.com/aleksandrenatchkebia/lwai_timeback_account_creation"""

    return send_google_chat_message(webhook_url, message, thread_key)


def notify_automation_start(webhook_url: str, total_students: int, thread_key: Optional[str] = None) -> bool:
    """
    Send startup notification for automation.
    
    Args:
        webhook_url (str): The Google Chat webhook URL
        total_students (int): Total number of students to process
        thread_key (str, optional): Thread key to reply in the same thread
        
    Returns:
        bool: True if message was sent successfully, False otherwise
    """
    if not webhook_url:
        return False
    return send_startup_notification(webhook_url, total_students, thread_key)


def notify_automation_complete(
    webhook_url: str,
    summary_data: dict,
    execution_time: Optional[str] = None,
    thread_key: Optional[str] = None
) -> bool:
    """
    Send completion notification with summary data.
    
    Args:
        webhook_url (str): The Google Chat webhook URL
        summary_data (dict): Summary data dictionary with:
            - total_processed (int)
            - successful_accounts (int)
            - failed_accounts (int)
            - success_details (List[Dict])
            - failure_details (List[Dict])
        execution_time (str, optional): Total execution time
        thread_key (str, optional): Thread key to reply in the same thread
        
    Returns:
        bool: True if message was sent successfully, False otherwise
    """
    if not webhook_url:
        return False
    
    return send_automation_summary(
        webhook_url=webhook_url,
        total_processed=summary_data['total_processed'],
        successful_accounts=summary_data['successful_accounts'],
        failed_accounts=summary_data['failed_accounts'],
        success_details=summary_data['success_details'],
        failure_details=summary_data['failure_details'],
        execution_time=execution_time,
        thread_key=thread_key
    )


def notify_automation_error(webhook_url: str, error_message: str, thread_key: Optional[str] = None) -> bool:
    """
    Send error notification for automation.
    
    Args:
        webhook_url (str): The Google Chat webhook URL
        error_message (str): The error message to send
        thread_key (str, optional): Thread key to reply in the same thread
        
    Returns:
        bool: True if message was sent successfully, False otherwise
    """
    if not webhook_url:
        return False
    return send_error_notification(webhook_url, error_message, thread_key)


# Example usage and testing
if __name__ == "__main__":
    # Test the notification system
    from config import GOOGLE_CHAT_WEBHOOK_URL
    
    # Test basic message
    print("Testing Google Chat notification...")
    success = send_google_chat_message(
        GOOGLE_CHAT_WEBHOOK_URL,
        "🧪 Test message from TimeBack automation system"
    )
    
    if success:
        print("✅ Test message sent successfully!")
    else:
        print("❌ Test message failed to send")
