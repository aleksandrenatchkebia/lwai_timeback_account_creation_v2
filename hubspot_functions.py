import requests
import os
import config
from dotenv import load_dotenv
from utils import retry_with_backoff, rate_limit_delay

load_dotenv()


def get_hubspot_access_token():
    """
    Get HubSpot access token.
    Supports both Private App access token (direct) and OAuth client credentials.
    
    Returns:
        str: HubSpot access token
    """
    # First, try Private App access token (most common for server-to-server)
    access_token = os.getenv('HUBSPOT_ACCESS_TOKEN') or os.getenv('HUBSPOT_API_KEY')
    
    if access_token:
        return access_token
    
    # If no direct token, try OAuth client credentials
    client_id = os.getenv('HUBSPOT_CLIENT')
    client_secret = os.getenv('HUBSPOT_SECRET')
    
    if not client_id or not client_secret:
        raise ValueError(
            "HubSpot authentication not configured. "
            "Provide either HUBSPOT_ACCESS_TOKEN (for Private App) or "
            "HUBSPOT_CLIENT and HUBSPOT_SECRET (for OAuth)"
        )
    
    # HubSpot OAuth token endpoint (may not support client_credentials)
    token_url = "https://api.hubapi.com/oauth/v1/token"
    
    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret
    }
    
    response = requests.post(token_url, data=data)
    response.raise_for_status()
    
    return response.json()['access_token']


def find_contact_by_email(email, access_token):
    """
    Find HubSpot contact by email address with retry logic.
    
    Args:
        email: Contact email address
        access_token: HubSpot access token
        
    Returns:
        tuple: (contact_id: str or None, success: bool, error: str)
    """
    url = f"https://api.hubapi.com/contacts/v1/contact/email/{email}/profile"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    def _make_request():
        try:
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                contact_data = response.json()
                contact_id = contact_data.get('vid') or contact_data.get('id')
                return True, contact_id, None
            elif response.status_code == 404:
                return False, None, "Contact not found"
            else:
                return False, None, f"HTTP {response.status_code}: {response.text}"
        
        except Exception as e:
            return False, None, str(e)
    
    # Apply retry logic with exponential backoff
    result, error = retry_with_backoff(_make_request, max_retries=3, initial_delay=1.0)
    
    if result is not None:
        return result, True, None
    else:
        return None, False, error


def update_contact_property(contact_id, property_name, property_value, access_token):
    """
    Update a single property on a HubSpot contact with retry logic.
    
    Args:
        contact_id: HubSpot contact ID (vid)
        property_name: Name of the property to update
        property_value: Value to set
        access_token: HubSpot access token
        
    Returns:
        tuple: (success: bool, error: str)
    """
    url = f"https://api.hubapi.com/contacts/v1/contact/vid/{contact_id}/profile"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    data = {
        "properties": [
            {
                "property": property_name,
                "value": property_value
            }
        ]
    }
    
    def _make_request():
        try:
            response = requests.post(url, headers=headers, json=data, timeout=30)
            
            if response.status_code in [200, 204]:
                return True, True, None  # success=True, result=True (placeholder), error=None
            else:
                return False, None, f"HTTP {response.status_code}: {response.text}"
        
        except Exception as e:
            return False, None, str(e)
    
    # Apply retry logic with exponential backoff
    result, error = retry_with_backoff(_make_request, max_retries=3, initial_delay=1.0)
    
    if error is None:
        return True, None
    else:
        return False, error


def update_contact_tracker_link(email, tracker_link, access_token=None):
    """
    Update HubSpot contact with tracker link property.
    
    Args:
        email: Contact email address
        tracker_link: URL to the tracker spreadsheet
        access_token: HubSpot access token (optional, will get from env if not provided)
        
    Returns:
        tuple: (success: bool, error: str)
    """
    if not access_token:
        access_token = get_hubspot_access_token()
    
    # Find contact by email
    contact_id, found, error = find_contact_by_email(email, access_token)
    
    if not found:
        return False, error or "Contact not found"
    
    # Update tracker link property
    # Property name should match your HubSpot custom property
    property_name = config.HUBSPOT_TRACKER_PROPERTY
    
    success, error = update_contact_property(contact_id, property_name, tracker_link, access_token)
    
    return success, error


def update_hubspot_contacts_with_trackers(tracker_results):
    """
    Update HubSpot contacts with tracker links for all successful trackers.
    
    Args:
        tracker_results: List of tracker result dictionaries with:
            - email: str
            - tracker_link: str
            - success: bool
        
    Returns:
        list: List of update results
            Format: [{'email': str, 'success': bool, 'error': str}, ...]
    """
    access_token = get_hubspot_access_token()
    update_results = []
    
    # Filter to only successful trackers
    successful_trackers = [tr for tr in tracker_results if tr.get('success', False)]
    
    for tracker in successful_trackers:
        email = tracker.get('email')
        tracker_link = tracker.get('tracker_link')
        
        if not email or not tracker_link:
            update_results.append({
                'email': email or 'Unknown',
                'success': False,
                'error': 'Missing email or tracker link'
            })
            continue
        
        # Rate limiting: Add delay before API call
        rate_limit_delay(0.5)
        
        # Update HubSpot contact
        success, error = update_contact_tracker_link(email, tracker_link, access_token)
        
        update_results.append({
            'email': email,
            'success': success,
            'error': error
        })
    
    return update_results


def update_hubspot_contacts_batch(tracker_results):
    """
    Main function to update HubSpot contacts with tracker links.
    Called from main.py after trackers are created.
    
    Args:
        tracker_results: List of tracker result dictionaries from tracker creation
        
    Returns:
        dict: Summary of update results
    """
    print("\nUpdating HubSpot contacts with tracker links...")
    
    update_results = update_hubspot_contacts_with_trackers(tracker_results)
    
    successful_updates = sum(1 for ur in update_results if ur['success'])
    failed_updates = sum(1 for ur in update_results if not ur['success'])
    
    print(f"  Contacts updated: {successful_updates}")
    print(f"  Contacts failed: {failed_updates}")
    
    if failed_updates > 0:
        print("\n  Failed updates:")
        for ur in update_results:
            if not ur['success']:
                print(f"    - {ur['email']}: {ur['error']}")
    
    return {
        'total': len(update_results),
        'successful': successful_updates,
        'failed': failed_updates,
        'results': update_results
    }
