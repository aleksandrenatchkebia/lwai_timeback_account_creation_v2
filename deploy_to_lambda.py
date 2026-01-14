"""
Deployment script for TimeBack automation Lambda function.

This script packages all Python source files and dependencies,
creates a deployment ZIP, and uploads it to S3.
"""
import os
import sys
import shutil
import zipfile
import subprocess
import tempfile
from pathlib import Path

# S3 Configuration
S3_BUCKET = 'lwaiexpdata'
S3_KEY = 'lambda-deployments/lambda_timeback_deployment_with_layers_live_v2.zip'
ZIP_FILENAME = 'lambda_timeback_deployment_with_layers_live_v2.zip'

# Python source files to include
PYTHON_FILES = [
    'lambda_handler.py',
    'main.py',
    's3_functions.py',
    'filter_functions.py',
    'processing_functions.py',
    'execution_functions.py',
    'tracker_functions.py',
    'hubspot_functions.py',
    'google_sheets_functions.py',
    'google_chat_notifications.py',
    'utils.py',
    'config.py',
]

# Dependencies to install (excluding pandas/numpy - these come from Lambda Layers)
DEPENDENCIES = [
    'boto3',
    'requests',
    'gspread',
    'gspread-dataframe',
    'python-dotenv',
    'google-auth',
    'google-auth-oauthlib',
    'google-auth-httplib2',
    'google-api-python-client',
]


def print_step(message: str):
    """Print a formatted step message."""
    print("\n" + "=" * 60)
    print(f"  {message}")
    print("=" * 60)


def check_requirements():
    """Check if required tools are available."""
    print_step("Checking Requirements")
    
    # Check Python version
    python_version = sys.version_info
    if python_version.major != 3 or python_version.minor < 7:
        raise RuntimeError(f"Python 3.7+ required, found {python_version.major}.{python_version.minor}")
    print(f"✓ Python {python_version.major}.{python_version.minor}.{python_version.micro}")
    
    # Check if pip is available
    try:
        subprocess.run(['pip', '--version'], check=True, capture_output=True)
        print("✓ pip available")
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise RuntimeError("pip not found. Please install pip.")
    
    # Check if AWS CLI is available (for S3 upload)
    try:
        subprocess.run(['aws', '--version'], check=True, capture_output=True)
        print("✓ AWS CLI available")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("⚠ AWS CLI not found. You'll need to upload the ZIP manually.")
    
    # Check if source files exist
    missing_files = []
    for file in PYTHON_FILES:
        if not os.path.exists(file):
            missing_files.append(file)
    
    if missing_files:
        raise RuntimeError(f"Missing source files: {', '.join(missing_files)}")
    print(f"✓ All {len(PYTHON_FILES)} source files found")


def create_deployment_package():
    """Create the deployment ZIP package."""
    print_step("Creating Deployment Package")
    
    # Create temporary directory for packaging
    temp_dir = tempfile.mkdtemp(prefix='lambda_deploy_')
    print(f"Using temporary directory: {temp_dir}")
    
    try:
        # Copy Python source files
        print("\nCopying Python source files...")
        for file in PYTHON_FILES:
            if os.path.exists(file):
                dest_path = os.path.join(temp_dir, file)
                shutil.copy2(file, dest_path)
                print(f"  ✓ {file}")
            else:
                print(f"  ⚠ {file} not found (skipping)")
        
        # Install dependencies
        print("\nInstalling dependencies...")
        requirements_file = os.path.join(temp_dir, 'requirements.txt')
        with open(requirements_file, 'w') as f:
            f.write('\n'.join(DEPENDENCIES))
        
        print(f"  Installing {len(DEPENDENCIES)} packages...")
        install_cmd = [
            sys.executable, '-m', 'pip', 'install',
            '-r', requirements_file,
            '-t', temp_dir,
            '--quiet',
            '--upgrade'
        ]
        
        try:
            result = subprocess.run(
                install_cmd,
                check=True,
                capture_output=True,
                text=True
            )
            print("  ✓ Dependencies installed")
        except subprocess.CalledProcessError as e:
            print(f"  ⚠ Warning: Some dependencies may have failed to install")
            print(f"    Error: {e.stderr}")
            print(f"    Continuing with available packages...")
        
        # Create ZIP file
        print(f"\nCreating ZIP file: {ZIP_FILENAME}")
        zip_path = os.path.join(os.getcwd(), ZIP_FILENAME)
        
        # Remove existing ZIP if it exists
        if os.path.exists(zip_path):
            os.remove(zip_path)
            print(f"  Removed existing {ZIP_FILENAME}")
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Add all files from temp directory
            for root, dirs, files in os.walk(temp_dir):
                # Skip __pycache__ and .pyc files
                dirs[:] = [d for d in dirs if d != '__pycache__']
                files = [f for f in files if not f.endswith('.pyc')]
                
                for file in files:
                    file_path = os.path.join(root, file)
                    arc_name = os.path.relpath(file_path, temp_dir)
                    zipf.write(file_path, arc_name)
                    print(f"  ✓ Added: {arc_name}")
        
        zip_size = os.path.getsize(zip_path) / (1024 * 1024)  # Size in MB
        print(f"\n✓ ZIP file created: {ZIP_FILENAME} ({zip_size:.2f} MB)")
        
        return zip_path
    
    finally:
        # Clean up temporary directory
        print(f"\nCleaning up temporary directory...")
        shutil.rmtree(temp_dir, ignore_errors=True)
        print("✓ Cleanup complete")


def upload_to_s3(zip_path: str):
    """Upload the deployment package to S3."""
    print_step("Uploading to S3")
    
    s3_uri = f"s3://{S3_BUCKET}/{S3_KEY}"
    print(f"Uploading to: {s3_uri}")
    
    try:
        # Use AWS CLI to upload
        upload_cmd = [
            'aws', 's3', 'cp',
            zip_path,
            s3_uri
        ]
        
        result = subprocess.run(
            upload_cmd,
            check=True,
            capture_output=True,
            text=True
        )
        
        print(f"✓ Upload successful!")
        print(f"  S3 URI: {s3_uri}")
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Upload failed!")
        print(f"  Error: {e.stderr}")
        print(f"\n  Manual upload command:")
        print(f"  aws s3 cp {zip_path} {s3_uri}")
        raise
    except FileNotFoundError:
        print("⚠ AWS CLI not found. Skipping upload.")
        print(f"\n  Please upload manually:")
        print(f"  aws s3 cp {zip_path} {s3_uri}")
        print(f"\n  Or use the AWS Console to upload:")
        print(f"  Bucket: {S3_BUCKET}")
        print(f"  Key: {S3_KEY}")


def print_deployment_instructions():
    """Print instructions for Lambda configuration."""
    print_step("Lambda Configuration Instructions")
    
    instructions = f"""
1. Handler Configuration:
   Handler: lambda_handler.lambda_handler
   Runtime: Python 3.9 or Python 3.10
   Timeout: 15 minutes (900 seconds)
   Memory: 1024 MB

2. Environment Variables:
   Set the following in Lambda configuration:
   - TIMEBACK_PLATFORM_REST_ENDPOINT
   - TIMEBACK_PLATFORM_CLIENT_ID
   - TIMEBACK_PLATFORM_CLIENT_SECRET
   - GCP_CRED (full JSON string)
   - HUBSPOT_ACCESS_TOKEN (or HUBSPOT_CLIENT + HUBSPOT_SECRET)
   - GOOGLE_CHAT_WEBHOOK_URL (optional, from config.py)
   - APP_IDS_GSHEET (optional, from config.py)
   - PROGRAM_TRACKERS_FOLDER (optional, from config.py)
   - HUBSPOT_TRACKER_PROPERTY (optional, from config.py)

3. Lambda Layers:
   Add a Lambda Layer with pandas and numpy:
   - ARN: Use a public layer or create your own
   - Example: arn:aws:lambda:us-east-1:336392948345:layer:AWSSDKPandas-Python39:1
   - Or use: https://github.com/keithrozario/Klayers

4. IAM Permissions:
   Ensure Lambda execution role has:
   - s3:GetObject on bucket 'lwaiexpdata'
   - logs:CreateLogGroup, logs:CreateLogStream, logs:PutLogEvents

5. S3 Deployment Package:
   Location: s3://{S3_BUCKET}/{S3_KEY}
   Use this S3 location when creating/updating the Lambda function.

6. Testing:
   Test locally: python lambda_handler.py
   Test in Lambda: Use a test event (empty JSON: {{}})
"""
    
    print(instructions)


def main():
    """Main deployment function."""
    print("\n" + "=" * 60)
    print("  TimeBack Automation Lambda Deployment")
    print("=" * 60)
    
    try:
        # Check requirements
        check_requirements()
        
        # Create deployment package
        zip_path = create_deployment_package()
        
        # Upload to S3
        try:
            upload_to_s3(zip_path)
        except Exception as e:
            print(f"\n⚠ Upload failed, but ZIP file is ready: {zip_path}")
            print("  You can upload it manually.")
        
        # Print instructions
        print_deployment_instructions()
        
        print("\n" + "=" * 60)
        print("  Deployment Package Ready!")
        print("=" * 60)
        print(f"\nZIP file: {zip_path}")
        print(f"S3 location: s3://{S3_BUCKET}/{S3_KEY}")
        print("\n✓ Deployment script completed successfully!")
        
    except Exception as e:
        print("\n" + "=" * 60)
        print("  ❌ Deployment Failed!")
        print("=" * 60)
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
