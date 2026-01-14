# TimeBack Automation - Testing Pipeline Onboarding

## Purpose

This automation is designed to onboard users into our testing pipelines. The system streamlines the process of taking leads from HubSpot and setting them up for testing across various segments.

## Overview

Testing pipelines are organized by **segments**, where each segment represents either:
- A different app, or
- A different subject/course on the same app

Some segments are further broken down into **grade levels** for more granular organization.

## Data Flow

### Lead Sources
- **HubSpot**: Testing leads are initially captured in HubSpot
- **S3 Storage**: Leads are stored in S3 for processing and archival

## Automation Workflow

The automation processes leads through the following phases:

### Phase 1: Data Retrieval
1. **Load Leads**: Fetch leads from S3 as a pandas DataFrame
2. **Load Accounts**: Fetch existing TimeBack accounts from S3 as a pandas DataFrame

### Phase 2: Lead Filtering
The automation applies multiple filters sequentially to refine the lead list:

1. **Filter Existing Accounts**: Remove leads that already have TimeBack accounts (matched by email)
2. **Filter by Date**: Remove leads older than 2 weeks (based on `hs_added_at` field)
3. **Filter Blacklisted Emails**: Remove emails present in the `blacklist` worksheet (Google Sheets)
4. **Filter by Grade Level**: 
   - Accept only leads whose current grade level (last completed grade + 1) falls within acceptable ranges
   - Ranges are defined in the `main_config` worksheet (`min_grade` and `max_grade` columns)
5. **Filter by Active Segments**: Remove leads from inactive segments (where `active = 0` in `main_config`)

### Phase 3: Processing (Data Preparation)
This phase prepares all necessary API payloads **without making any API calls**:

1. **Load Configuration Data** (done once for all students):
   - **Segment Configuration**: Loaded from `main_config` worksheet (segment, app, assessments flag, grade ranges)
   - **Assessment IDs**: Loaded from `assessment_ids` worksheet (grade, unit, assessment name, ID, pre/post flags)
   - **Applications Dictionary**: Fetched from TimeBack API (one-time call to get app name → app ID mapping)

2. **Process Each Student**:
   - Generate UUIDs (`sourcedId`, `profileId`) for the student
   - Create **Account Payload**: Format student data (email, name, grade, birth date) for TimeBack account creation
   - Create **App Assignment Payload**: Determine app based on segment, create assignment payload
   - Create **Assessment Assignment Payloads**: Look up assessments for the student's grade level and segment, create assignment payloads for each

3. **Collect Results**: All prepared payloads are collected in a results list

### Phase 4: Execution (API Calls)
This phase makes actual API calls to TimeBack and handles logging:

1. **Create Accounts**: For each student, create a TimeBack account using the prepared payload
2. **Assign Learning Apps**: Assign the appropriate learning app based on segment configuration
3. **Assign Assessments**: Assign all relevant assessments for the student's grade level and segment
4. **Error Handling**: If account creation fails, skip app/assessment assignments for that student
5. **Batch Logging**: Write all success/failure logs to Google Sheets (`success_log` and `fail_log` worksheets) in batch operations

### Phase 5: Tracker Creation
For each successfully created account:

1. **Load Tracker Templates**: Load tracker spreadsheet templates from `program_trackers` worksheet
2. **Create Tracker Copy**: 
   - Copy the appropriate tracker template to the Shared Drive folder (`PROGRAM_TRACKERS_FOLDER`)
   - Rename the copy: Replace `[Student Name]` in the title with the student's email
   - Populate cells:
     - **B2**: Student's email address
     - **B3**: Signup date (from lead data)
3. **Share Tracker**: Share the copied tracker with the student's email address (writer access, no notification)
4. **Log Trackers**: Write tracker details (email, segment, course/grade, tracker_link, added_timestamp) to `all_trackers` worksheet in batch

### Phase 6: HubSpot Integration
1. **Update Contact Properties**: For each successfully created tracker, update the corresponding HubSpot contact
2. **Set Tracker Link**: Update the `tracker_link` property (configurable via `HUBSPOT_TRACKER_PROPERTY` in `config.py`)
3. **Trigger Workflow**: The property update triggers an existing HubSpot workflow that sends the email notification to the lead

### Phase 7: Notifications
Google Chat notifications are sent at key points:
- **Startup**: Notification when automation begins (includes number of leads to process)
- **Completion**: Summary notification with execution statistics and time
- **Errors**: Error notification if the automation fails

## Testing Mode

The automation includes testing features for safe development:

1. **Lead Limiting**: `TEST_LIMIT` variable in `main.py` limits the number of leads processed (default: 1 for testing)
2. **Skip Account Creation**: `SKIP_ACCOUNT_CREATION` flag allows testing tracker creation and HubSpot updates without creating TimeBack accounts

**Note**: Both testing flags should be disabled/commented out for production runs.

## Implementation Status

### ✅ Fully Implemented

- **Data Retrieval**: S3 integration for leads and accounts
- **Lead Filtering Pipeline**: All 5 filter functions implemented
- **Processing Phase**: Payload preparation without API calls
- **Execution Phase**: TimeBack API integration (account creation, app/assessment assignment)
- **Batch Logging**: Success and failure logs written to Google Sheets
- **Tracker Creation**: Copy, rename, populate, and share tracker spreadsheets
- **HubSpot Integration**: Contact property updates to trigger workflow emails
- **Google Chat Notifications**: Startup, completion, and error notifications
- **Google Sheets Integration**: Configuration reading, logging, tracker management
- **Error Handling**: Comprehensive error handling throughout the pipeline

## Files

### Core Scripts
- **`main.py`**: Main entry point orchestrating all phases
- **`s3_functions.py`**: Functions for retrieving data from S3
- **`filter_functions.py`**: Lead filtering functions (accounts, date, blacklist, grade level, active segments)
- **`processing_functions.py`**: Data preparation and payload creation (no API calls)
- **`execution_functions.py`**: TimeBack API execution, logging, and summary preparation
- **`tracker_functions.py`**: Tracker spreadsheet creation, population, sharing, and logging
- **`hubspot_functions.py`**: HubSpot API integration for contact property updates
- **`google_sheets_functions.py`**: Google Sheets and Drive API integration functions
- **`google_chat_notifications.py`**: Google Chat webhook notification functions
- **`config.py`**: Configuration settings (Google Sheet IDs, folder IDs, property names)

### Configuration Files
- **`.env`**: Environment variables for API credentials and secrets
- **Google Sheets (Automation Support Sheet)**: Contains:
  - `main_config`: Segment configuration (app, grade ranges, active status)
  - `assessment_ids`: Assessment ID mappings
  - `blacklist`: Blacklisted email addresses
  - `program_trackers`: Tracker template spreadsheet URLs
  - `success_log`: Log of successful account creations
  - `fail_log`: Log of failed account creations
  - `all_trackers`: Log of all created trackers with metadata

## Configuration

### Environment Variables (`.env`)
- `TIMEBACK_PLATFORM_REST_ENDPOINT`: TimeBack API endpoint
- `TIMEBACK_PLATFORM_CLIENT_ID`: TimeBack OAuth client ID
- `TIMEBACK_PLATFORM_CLIENT_SECRET`: TimeBack OAuth client secret
- `GCP_CRED`: Google Cloud service account credentials (JSON string)
- `HUBSPOT_ACCESS_TOKEN`: HubSpot Private App access token (recommended)
- `HUBSPOT_CLIENT`: HubSpot OAuth client ID (alternative to access token)
- `HUBSPOT_SECRET`: HubSpot OAuth client secret (alternative to access token)
- `GOOGLE_CHAT_WEBHOOK_URL`: Google Chat webhook URL for notifications

### Configuration File (`config.py`)
- `APP_IDS_GSHEET`: Google Sheet ID for automation support sheet
- `GOOGLE_CHAT_WEBHOOK_URL`: Google Chat webhook URL
- `PROGRAM_TRACKERS_FOLDER`: Google Drive folder ID for storing tracker copies (Shared Drive)
- `HUBSPOT_TRACKER_PROPERTY`: HubSpot property name for tracker links (default: `tracker_link`)

## Key Features

- **Modular Design**: Each phase is separated into dedicated scripts for maintainability
- **Batch Operations**: Logging and tracker writes use batch operations to minimize API calls
- **Error Resilience**: Comprehensive error handling ensures partial failures don't break the entire run
- **Testing Support**: Built-in testing modes for safe development
- **Shared Drive Support**: Trackers stored in Shared Drive to manage quota
- **Workflow Integration**: HubSpot property updates trigger existing email workflows

---

*Last updated: Jan 2026*