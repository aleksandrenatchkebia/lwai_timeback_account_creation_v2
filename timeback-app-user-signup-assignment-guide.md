# LwAI TimeBack Platform API Guide (Specifically for Signing Up Users as 'TimeBack' / Homeschool Users, i.e. Non-Alpha Users)

## Overview

This guide provides instructions for automating student signup and learning app / assessment assignment directly through the Timeback platform REST API. This covers:

1. **TimeBack App User Creation**: Creates the core user record in the platform
2. **Learning App / Assessment Assignment**: Assigns default learning apps / assessments to the user (optional)

This is intended for programmatic automation rather than end-user interaction. Additional services like WorkSmart onboarding and permissions setup are not included.

## API Endpoint

### Base URL

The platform API base URL is configured via environment variable `PLATFORM_REST_ENDPOINT`.

### TimeBack App User Creation Endpoint

```
PUT /rostering/1.0/students
```

## Authentication

### Client Credentials

- **Client ID**: Set via `PLATFORM_CLIENT_ID` environment variable
- **Client Secret**: Set via `PLATFORM_CLIENT_SECRET` environment variable

### Token Acquisition

1. **Endpoint**: `/auth/1.0/token`
2. **Method**: `POST`
3. **Headers**:
   - `Authorization: Basic <base64(clientId:clientSecret)>`
   - `Content-Type: application/x-www-form-urlencoded`
4. **Body**:
   ```
   grant_type=client_credentials&scope=https://purl.imsglobal.org/spec/or/v1p2/scope/roster.createput%20https://purl.imsglobal.org/spec/or/v1p2/scope/roster.readonly%20https://purl.imsglobal.org/spec/lti/v1p3/scope/lti.readonly%20https://purl.imsglobal.org/spec/lti/v1p3/scope/lti.createput
   ```

### API Request Headers

```
Authorization: Bearer <access_token>
Content-Type: application/json
```

## Request Format

### Required Student Data Structure

```json
{
  "student": {
    "sourcedId": "string", // Required: Unique identifier (UUID)
    "email": "string", // Required: Student's email
    "username": "string", // Required: Username (same as email)
    "status": "active", // Required: Must be "active"
    "enabledUser": "true", // Required: Must be "true"
    "givenName": "string", // Required: Student's first name
    "familyName": "string", // Required: Student's last name
    "preferredFirstName": "string", // Required: Preferred first name (same as givenName)
    "grades": ["string"], // Required: Array with single grade level
    "primaryOrg": {
      // Required: Timeback organization reference (hardcoded)
      "href": "https://timeback.com/orgs/84105a1c-29e5-44fc-a497-36a7c61860c5",
      "sourcedId": "84105a1c-29e5-44fc-a497-36a7c61860c5",
      "type": "org" // Must be "org"
    },
    "demographics": {
      // Required: Student demographics
      "birthDate": "YYYY-MM-DD" // Required: Birth date
    }
  }
}
```

### Required Fields

- `sourcedId`: Unique identifier (generate using UUID)
- `email`: Student's email address
- `username`: Username (same as email)
- `status`: Must be `"active"`
- `enabledUser`: Must be `"true"`
- `givenName`: Student's first name
- `familyName`: Student's last name
- `preferredFirstName`: Preferred first name (same as givenName)
- `grades`: Array containing single grade level
- `primaryOrg`: Timeback organization reference (use hardcoded values below)
- `demographics`: Object containing birth date

#### Grade Values

Valid grade values for the `grades` array:

- `"PK"` - Pre-Kindergarten
- `"K"` - Kindergarten
- `"1"` through `"12"` - Grades 1-12

## Step 1: Student Creation Example

```bash
# 1. Get access token
curl -X POST "${PLATFORM_REST_ENDPOINT}/auth/1.0/token" \
  -H "Authorization: Basic $(echo -n '${CLIENT_ID}:${CLIENT_SECRET}' | base64)" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials&scope=https://purl.imsglobal.org/spec/or/v1p2/scope/roster.createput"

# 2. Create student
curl -X PUT "${PLATFORM_REST_ENDPOINT}/rostering/1.0/students" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "student": {
      "sourcedId": "38c7fd85-4e73-4776-986b-97f29fb3ae3a",
      "email": "edolgov.photo@gmail.com",
      "username": "edolgov.photo@gmail.com",
      "status": "active",
      "enabledUser": "true",
      "givenName": "Eugene",
      "familyName": "Dolgov",
      "preferredFirstName": "Eugene",
      "grades": ["1"],
      "primaryOrg": {
        "href": "https://timeback.com/orgs/84105a1c-29e5-44fc-a497-36a7c61860c5",
        "sourcedId": "84105a1c-29e5-44fc-a497-36a7c61860c5",
        "type": "org"
      },
      "demographics": {
        "birthDate": "2001-06-06"
      }
    }
  }'
```

## Step 2: Discover Available Learning Apps

Before assigning learning apps to a user, you need to discover what applications are available in the platform.

### Applications Endpoint

```
GET /applications/1.0
```

### Query Parameters (Optional)

- `limit`: Number of results per page (default: 50, max: 100)
- `offset`: Number of records to skip for pagination (default: 0)
- `filter`: Filter applications by criteria (e.g., `name='Athena'`)
- `sort`: Sort field
- `orderBy`: Sort direction (`ASC` or `DESC`)

### Applications Response Structure

**Note**: As of recent platform updates, tools have been flattened into applications. Each application now directly represents what was previously a tool, and you access the `sourcedId` directly from the application object.

```json
{
  "applications": [
    {
      "sourcedId": "string", // Application ID for profile assignment (use this directly)
      "status": "active",
      "dateCreated": "2024-01-01T00:00:00Z",
      "dateLastModified": "2024-01-01T00:00:00Z",
      "metadata": {},
      "name": "Application Name", // Display name
      "description": "Application description",
      "logoUrl": "https://example.com/logo.png",
      "coverImageUrl": "https://example.com/cover.png",
      "applicationType": "learning_app", // or "assessment"
      "launchUrl": "https://example.com/launch",
      "isLtiCompliant": true,
      "isLtiV1P3Compliant": true
    }
  ],
  "pagination": {
    "limit": 50,
    "offset": 0,
    "total": 100,
    "hasMore": true
  }
}
```

**Important**: Use `application.sourcedId` directly for profile assignments. The old nested `tools` array structure is no longer used.

### Find Applications Example

```bash
# 1. Get all applications (paginated)
curl -X GET "${PLATFORM_REST_ENDPOINT}/applications/1.0" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json"

# 2. Search for specific application by name
curl -X GET "${PLATFORM_REST_ENDPOINT}/applications/1.0?filter=name='Athena'" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json"

# 3. Get applications with pagination
curl -X GET "${PLATFORM_REST_ENDPOINT}/applications/1.0?limit=25&offset=0" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json"
```

## Step 3: Assign Learning Apps to User

After creating the student and identifying the desired applications, you can assign learning apps by creating user profiles.

### Learning App Assignment Endpoint

```
PUT /rostering/1.0/users/{userId}/profiles/{profileId}
```

### User Profile Request Structure

```json
{
  "profileId": "string", // Required: Unique profile ID (UUID)
  "applicationId": "string", // Required: Application sourcedId from Step 2
  "profileType": "learning_app_profile", // Required: Must be "learning_app_profile"
  "vendorId": "alpha", // Required: Must be "alpha" for TimeBack users
  "description": "string" // Optional: Profile description
}
```

### Required Profile Fields

- `profileId`: Unique identifier for this profile assignment (generate using UUID)
- `applicationId`: The `sourcedId` from the applications response
- `profileType`: Must be `"learning_app_profile"`
- `vendorId`: Must be `"alpha"` for TimeBack platform users
- `description`: Optional description of the assignment

### Complete Learning App Assignment Example

```bash
# 1. First, get applications to find the desired app ID
curl -X GET "${PLATFORM_REST_ENDPOINT}/applications/1.0?filter=name='Athena'" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json"

# 2. Extract the sourcedId from the response and assign to variables
USER_ID="38c7fd85-4e73-4776-986b-97f29fb3ae3a"  # From Step 1 user creation
PROFILE_ID=$(uuidgen)  # Generate new UUID for this assignment
APPLICATION_ID="extracted-from-applications-response"  # From applications API

# 3. Assign the learning app to the user
curl -X PUT "${PLATFORM_REST_ENDPOINT}/rostering/1.0/users/${USER_ID}/profiles/${PROFILE_ID}" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "profileId": "'${PROFILE_ID}'",
    "applicationId": "'${APPLICATION_ID}'",
    "profileType": "learning_app_profile",
    "vendorId": "alpha",
    "description": "Automated assignment via TimeBack Platform API"
  }'
```

### Assign Multiple Learning Apps

To assign multiple learning apps to the same user, repeat the profile assignment with different `profileId` and `applicationId` values:

```bash
# Assign second learning app
PROFILE_ID_2=$(uuidgen)  # Generate new UUID for second assignment
APPLICATION_ID_2="second-app-id-from-applications-response"

curl -X PUT "${PLATFORM_REST_ENDPOINT}/rostering/1.0/users/${USER_ID}/profiles/${PROFILE_ID_2}" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "profileId": "'${PROFILE_ID_2}'",
    "applicationId": "'${APPLICATION_ID_2}'",
    "profileType": "learning_app_profile",
    "vendorId": "alpha",
    "description": "Second learning app assignment"
  }'
```

## Step 4: Verification and Utility Endpoints

### Verify User Creation

```bash
# Get all users (paginated)
curl -X GET "${PLATFORM_REST_ENDPOINT}/rostering/1.0/users" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json"

# Get specific user by ID
curl -X GET "${PLATFORM_REST_ENDPOINT}/rostering/1.0/users/${USER_ID}" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json"
```

### Get Organizations

```bash
# View available organizations
curl -X GET "${PLATFORM_REST_ENDPOINT}/rostering/1.0/orgs" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json"
```

### Platform Health Check

```bash
# Verify platform connectivity
curl -X GET "${PLATFORM_REST_ENDPOINT}/ping" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json"
```

## Environment Configuration

### Environment Variables Required

```bash
# Staging Environment
PLATFORM_REST_ENDPOINT=https://3ztk7lpq21.execute-api.us-east-1.amazonaws.com/api
PLATFORM_CLIENT_ID=90ac761pdufgp3gmqret1cmd7
PLATFORM_CLIENT_SECRET=1m9mkinif1h337e5qcbpnsv7qmqjrjhcnq8croglp8jrmbjdfk9g

# Production Environment
# PLATFORM_REST_ENDPOINT=https://jherbpzmm0.execute-api.us-east-1.amazonaws.com/api
# PLATFORM_CLIENT_ID=2sic7g9kk90256ethv2q8v7dfj
# PLATFORM_CLIENT_SECRET=a843tcgjnaiis9q36699lt0de130jd2v3f34922po53ve36572q
```

### Hardcoded Values

#### TimeBack Organization Reference

Use these exact values for the `primaryOrg` field in student creation:

```json
{
  "href": "https://timeback.com/orgs/84105a1c-29e5-44fc-a497-36a7c61860c5",
  "sourcedId": "84105a1c-29e5-44fc-a497-36a7c61860c5",
  "type": "org"
}
```

#### Profile Assignment Constants

- `profileType`: Always `"learning_app_profile"`
- `vendorId`: Always `"alpha"` for TimeBack users

## Error Handling

### Common Response Codes

- **200 OK**: Successful request
- **201 Created**: Resource created successfully
- **400 Bad Request**: Invalid request data
- **401 Unauthorized**: Invalid or expired access token
- **403 Forbidden**: Insufficient permissions
- **404 Not Found**: Resource not found
- **409 Conflict**: Resource already exists (duplicate)
- **500 Internal Server Error**: Platform error

### Token Expiration

Access tokens expire after a certain period. If you receive a 401 error, re-authenticate using Step 1.

## Complete Workflow Summary

1. **Authenticate**: Get access token using client credentials
2. **Discover Apps**: Query applications endpoint to find desired learning apps
3. **Create User**: Create student record with required fields
4. **Assign Apps**: Create user profiles to assign learning apps
5. **Verify**: Use utility endpoints to confirm successful creation and assignments
