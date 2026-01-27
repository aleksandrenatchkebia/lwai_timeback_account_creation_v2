#!/usr/bin/env python3
"""
Deploy TimeBack Lambda function with dependencies split into a Layer.
This script creates a Lambda Layer for Google dependencies and a smaller main package.

Usage:
    python3 deploy_to_lambda.py

The script will:
1. Create a Lambda Layer ZIP with Google dependencies (upload separately to Lambda)
2. Create a smaller deployment package with source files and lightweight dependencies
3. Upload main package to S3
4. Provide instructions for creating the layer and deploying
"""

import os
import sys
import zipfile
import subprocess
import shutil
from pathlib import Path

def create_google_layer():
    """Create Lambda Layer with Google dependencies."""
    print("📦 Creating Google dependencies Lambda Layer...")
    print("="*60)
    
    # Google authentication dependencies + gspread (all Google-related packages)
    # Note: Using --no-deps, so we must explicitly list all transitive dependencies
    google_deps = [
        'google-auth',
        'google-auth-oauthlib', 
        'google-auth-httplib2',
        'google-api-python-client',
        'google-api-core',
        'googleapis-common-protos',
        'proto-plus',
        'protobuf',
        'pyparsing',  # Required by protobuf
        'uritemplate',
        'cryptography',
        'cffi',
        'pycparser',  # Required by cffi
        'cachetools',  # Required by google-auth
        'pyasn1',  # Required by pyasn1-modules
        'pyasn1-modules',  # Required by google-auth
        'rsa',  # Required by google-auth
        'urllib3',  # Required by requests and other packages
        'requests_oauthlib',  # Required by google-auth-oauthlib
        'oauthlib',  # Required by requests_oauthlib
        'httplib2',  # Required by google-auth-httplib2
        'six',  # Required by many packages
        'requests',  # Required by google-api-core (needed in layer, not main package)
        'certifi',  # Required by requests
        'charset-normalizer',  # Required by requests
        'idna',  # Required by urllib3/requests
        'packaging',  # Often required by various packages
        'gspread',  # Depends on google-auth, so put in layer
        'gspread-dataframe'  # Depends on gspread
    ]
    
    layer_name = 'lambda_timeback_google_layer.zip'
    temp_layer_dir = 'temp_layer'
    python_dir = os.path.join(temp_layer_dir, 'python', 'lib', 'python3.10', 'site-packages')
    
    # Clean up any existing temp directory
    if os.path.exists(temp_layer_dir):
        shutil.rmtree(temp_layer_dir)
    
    os.makedirs(python_dir, exist_ok=True)
    
    try:
        # Install Google packages together to ensure namespace packages work correctly
        print("   Installing Google packages...")
        install_cmd = [
            sys.executable, '-m', 'pip', 'install', 
            '--target', python_dir, 
            '--platform', 'manylinux2014_x86_64',
            '--python-version', '310',
            '--only-binary=:all:',
            '--no-deps'
        ] + google_deps
        
        try:
            subprocess.run(install_cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            print(f"      ❌ Failed to install Google packages, trying fallback...")
            fallback_cmd = [
                sys.executable, '-m', 'pip', 'install',
                '--target', python_dir,
                '--platform', 'manylinux2014_x86_64',
                '--python-version', '310',
                '--no-deps'
            ] + google_deps
            subprocess.run(fallback_cmd, check=True, capture_output=True, text=True)
        
        # Verify critical packages
        print("\n🔍 Verifying packages in layer...")
        critical_checks = {
            'google-api-core': os.path.join(python_dir, 'google', 'api_core'),
            'google-auth': os.path.join(python_dir, 'google', 'auth'),
            'googleapiclient': os.path.join(python_dir, 'googleapiclient'),
            'gspread': os.path.join(python_dir, 'gspread'),
            'certifi': os.path.join(python_dir, 'certifi'),
        }
        for pkg_name, check_path in critical_checks.items():
            if os.path.exists(check_path):
                print(f"   ✅ {pkg_name} found")
                # Special check for certifi - verify cacert.pem exists
                if pkg_name == 'certifi':
                    cert_file = os.path.join(check_path, 'cacert.pem')
                    if os.path.exists(cert_file):
                        print(f"      ✅ certifi/cacert.pem found ({os.path.getsize(cert_file) / 1024:.1f} KB)")
                    else:
                        print(f"      ⚠️  certifi/cacert.pem NOT found!")
            else:
                print(f"   ⚠️  {pkg_name} not found at {check_path}")
        
        # Create layer ZIP (optimized - exclude unnecessary files but include data files)
        print("\n📦 Creating optimized layer ZIP...")
        # Exclude patterns - but be careful not to exclude actual package modules
        # Don't exclude directories that are part of package names (like pyparsing/testing)
        excluded_patterns = [
            '__pycache__',
            '.dist-info',
            '.egg-info',
            '/tests/',  # Only exclude /tests/ directories, not "testing" modules
            '/test/',   # Only exclude /test/ directories
            '/docs/',   # Only exclude /docs/ directories, not "documents"
            '/doc/',    # Only exclude /doc/ directories, not "documents"
            '.txt',  # Exclude README, LICENSE, etc. (but keep .py files)
            '.md',
            '.rst',
            '.yml',
            '.yaml',
            '.toml',
            '.cfg',
            '.ini',
            'PKG-INFO',
            'METADATA',
            'RECORD',
            'SOURCES.txt',
            'top_level.txt',
            'WHEEL',
            'INSTALLER'
        ]
        
        # Essential file types to include
        included_extensions = ['.py', '.so', '.pyi', '.pem', '.json']  # Added .pem for certifi, .json for discovery cache
        
        # Critical data files/directories that must be included
        critical_paths = [
            'certifi/cacert.pem',  # Certificate bundle for SSL
            'googleapiclient/discovery_cache',  # API discovery documents (needed for build('drive', 'v3'))
        ]
        
        with zipfile.ZipFile(layer_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(temp_layer_dir):
                # Skip excluded directories
                dirs[:] = [d for d in dirs if not any(pattern in d for pattern in excluded_patterns)]
                
                for file in files:
                    file_path = os.path.join(root, file)
                    arc_path = os.path.relpath(file_path, temp_layer_dir)
                    
                    # Skip if path contains excluded patterns
                    if any(pattern in arc_path for pattern in excluded_patterns):
                        continue
                    
                    # Skip cache files
                    if file.endswith('.pyc') or file.endswith('.pyo'):
                        continue
                    
                    # Always include critical files (like certifi's certificate bundle and discovery cache)
                    is_critical = any(critical in arc_path for critical in critical_paths)
                    
                    # Check file extension
                    file_ext = os.path.splitext(file)[1]
                    
                    # Include only necessary discovery cache JSON files (Drive API v3 only)
                    # We only need drive.v3.json, not all 569 API discovery documents
                    is_discovery_cache_json = 'discovery_cache' in arc_path and file_ext == '.json'
                    is_drive_v3 = 'drive.v3.json' in file or 'drive.v3' in arc_path
                    
                    # Exclude discovery cache JSON files that aren't Drive v3
                    if is_discovery_cache_json and not is_drive_v3:
                        continue  # Skip all other discovery cache JSON files
                    
                    # Include if:
                    # 1. It's a critical file (like certifi certificate or discovery cache)
                    # 2. It has an included extension (.py, .so, .pyi, .pem, .json)
                    # 3. It's __init__.py (no extension but essential)
                    # 4. It's the Drive API v3 discovery cache JSON file (only this one)
                    if is_discovery_cache_json and is_drive_v3:
                        # Only include Drive API v3 discovery document
                        zipf.write(file_path, arc_path)
                    elif is_critical or file_ext in included_extensions or file == '__init__.py':
                        # For files without extension that aren't __init__.py, check if they're data files
                        if not file_ext and file != '__init__.py':
                            # Include if it's in certifi directory (might be data files)
                            if 'certifi' in arc_path.lower():
                                zipf.write(file_path, arc_path)
                            else:
                                # For other files without extension, check if binary/data
                                try:
                                    with open(file_path, 'rb') as f:
                                        first_bytes = f.read(512)
                                        # If it's mostly text (printable ASCII), skip it
                                        if first_bytes and all(b in b'\n\r\t' + bytes(range(32, 127)) for b in first_bytes[:100]):
                                            continue
                                        # Otherwise include (might be binary data file)
                                        zipf.write(file_path, arc_path)
                                except:
                                    # If we can't read it, include it to be safe
                                    zipf.write(file_path, arc_path)
                        else:
                            zipf.write(file_path, arc_path)
        
        layer_size = os.path.getsize(layer_name) / (1024 * 1024)  # MB
        print(f"✅ Layer created: {layer_name}")
        print(f"📊 Layer size: {layer_size:.1f} MB")
        
        # Verify critical imports work (test that modules can be imported)
        print("\n🔍 Testing critical imports...")
        test_imports = [
            'google.api_core',
            'google.auth',
            'certifi',
            'pyparsing',  # Test that pyparsing and its submodules are available
        ]
        
        # Temporarily add python_dir to path for testing
        original_path = sys.path[:]
        sys.path.insert(0, python_dir)
        
        failed_imports = []
        try:
            for module_name in test_imports:
                try:
                    __import__(module_name)
                    print(f"   ✅ {module_name}")
                except ImportError as e:
                    print(f"   ❌ {module_name}: {e}")
                    failed_imports.append(module_name)
            
            # Test pyparsing.testing specifically (this was previously excluded)
            try:
                import pyparsing.testing
                print(f"   ✅ pyparsing.testing")
            except ImportError as e:
                print(f"   ❌ pyparsing.testing: {e}")
                failed_imports.append('pyparsing.testing')
            
            # Test gspread (may fail on macOS due to Linux binaries, but that's OK)
            try:
                import gspread
                print(f"   ✅ gspread")
            except Exception as e:
                # On macOS, this may fail due to Linux .so files, but will work in Lambda
                if 'mach-o' in str(e).lower() or 'slice' in str(e).lower():
                    print(f"   ⚠️  gspread (expected macOS/Linux mismatch, will work in Lambda)")
                else:
                    print(f"   ❌ gspread: {e}")
                    failed_imports.append('gspread')
        finally:
            # Restore original path
            sys.path[:] = original_path
        
        if failed_imports:
            print(f"\n⚠️  Warning: {len(failed_imports)} imports failed. Layer may not work correctly.")
        else:
            print(f"\n✅ All critical imports successful!")
        
        return layer_name
    
    finally:
        # Clean up temp directory
        if os.path.exists(temp_layer_dir):
            shutil.rmtree(temp_layer_dir)


def deploy_to_lambda():
    """Create Lambda layer and deployment package."""
    
    print("🚀 Creating TimeBack Lambda deployment package with Layer...")
    print("="*60)
    
    # Step 1: Create Google dependencies layer
    print("\n" + "="*60)
    layer_name = create_google_layer()
    
    # Step 2: Create main deployment package (without Google deps)
    print("\n" + "="*60)
    
    # Source files to include
    source_files = [
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
    
    # Lightweight dependencies (boto3 and requests are in Layer, only minimal deps here)
    lightweight_deps = [
        'python-dotenv'  # boto3 is already available in Lambda runtime, requests is in Google layer
    ]
    
    # Create deployment package
    package_name = 'lambda_timeback_deployment_with_layers_live_v2.zip'
    
    with zipfile.ZipFile(package_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Add source files
        print("📁 Adding source files...")
        for file_path in source_files:
            if Path(file_path).exists():
                print(f"   ✅ {file_path}")
                zipf.write(file_path, file_path)
            else:
                print(f"   ⚠️  {file_path} (not found)")
        
        # Install dependencies to temp directory
        print("\n📦 Installing dependencies...")
        temp_dir = 'temp_deps'
        os.makedirs(temp_dir, exist_ok=True)
        
        try:
            # Install lightweight deps only (Google deps are in the Layer)
            print("   Installing lightweight dependencies...")
            for dep in lightweight_deps:
                print(f"   📦 {dep}...")
                install_cmd = [
                    sys.executable, '-m', 'pip', 'install', 
                    '--target', temp_dir, 
                    '--platform', 'manylinux2014_x86_64',
                    '--python-version', '310',
                    '--only-binary=:all:',
                    '--no-deps',
                    dep
                ]
                try:
                    subprocess.run(install_cmd, check=True, capture_output=True, text=True)
                except subprocess.CalledProcessError as e:
                    print(f"      ❌ Failed to install {dep}, trying fallback...")
                    fallback_cmd = [
                        sys.executable, '-m', 'pip', 'install',
                        '--target', temp_dir,
                        '--platform', 'manylinux2014_x86_64',
                        '--python-version', '310',
                        '--no-deps',
                        dep
                    ]
                    subprocess.run(fallback_cmd, check=True, capture_output=True, text=True)
            
            # Add dependencies to zip (include all necessary files, preserve package structure)
            print("\n📦 Adding dependencies to package...")
            for root, dirs, files in os.walk(temp_dir):
                # Skip numpy and pandas directories
                dirs[:] = [d for d in dirs if d not in ['numpy', 'pandas', 'numpy.libs', 'pandas.libs', '__pycache__']]
                
                for file in files:
                    file_path = os.path.join(root, file)
                    arc_path = os.path.relpath(file_path, temp_dir)
                    
                    # Skip numpy and pandas files
                    if 'numpy' in arc_path.lower() or 'pandas' in arc_path.lower():
                        continue
                    
                    # Skip cache files
                    if file.endswith('.pyc') or file.endswith('.pyo'):
                        continue
                    
                    # Skip .dist-info and .egg-info directories
                    if '.dist-info' in arc_path or '.egg-info' in arc_path:
                        continue
                    
                    # Include all other files (.py, .so, .pyi, data files, etc.)
                    zipf.write(file_path, arc_path)
        
        finally:
            # Clean up temp directory
            import shutil
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
    
    # Get package size
    package_size = os.path.getsize(package_name) / (1024 * 1024)  # MB
    
    print(f"\n✅ Deployment package created: {package_name}")
    print(f"📊 Package size: {package_size:.1f} MB")
    
    if package_size > 250:  # Lambda limit is ~250MB
        print(f"⚠️  Package size is close to Lambda limits")
    else:
        print(f"✅ Package size is within Lambda limits")
    
    # Upload main package to S3
    print(f"\n☁️  Uploading main package to S3...")
    s3_key = "lambda-deployments/lambda_timeback_deployment_with_layers_live_v2.zip"
    
    try:
        import boto3
        s3_client = boto3.client('s3')
        s3_client.upload_file(package_name, 'lwaiexpdata', s3_key)
        print(f"✅ Uploaded to s3://lwaiexpdata/{s3_key}")
    except Exception as e:
        print(f"❌ S3 upload failed: {e}")
        print(f"📁 Package is ready locally: {package_name}")
        return False
    
    # Upload layer to S3
    print(f"\n☁️  Uploading layer to S3...")
    layer_s3_key = "lambda-deployments/lambda_timeback_google_layer.zip"
    
    try:
        s3_client.upload_file(layer_name, 'lwaiexpdata', layer_s3_key)
        print(f"✅ Layer uploaded to s3://lwaiexpdata/{layer_s3_key}")
    except Exception as e:
        print(f"❌ Layer upload failed: {e}")
        print(f"📁 Layer is ready locally: {layer_name}")
        return False
    
    # Clean up local packages
    os.remove(package_name)
    os.remove(layer_name)
    print(f"🧹 Cleaned up local packages")
    
    print(f"\n🎉 Deployment complete!")
    print(f"="*60)
    print(f"📝 Next steps:")
    print(f"\n1️⃣  CREATE THE LAYER FIRST:")
    print(f"   1. Go to AWS Lambda Console → Layers")
    print(f"   2. Click 'Create layer'")
    print(f"   3. Name: timeback-google-dependencies")
    print(f"   4. Upload from S3: s3://lwaiexpdata/{layer_s3_key}")
    print(f"   5. Compatible runtimes: Python 3.10")
    print(f"   6. Click 'Create'")
    print(f"   7. Copy the Layer ARN (you'll need it)")
    print(f"\n2️⃣  UPDATE YOUR LAMBDA FUNCTION:")
    print(f"   1. Go to Lambda Console → Functions → timeback-account-creation-automation")
    print(f"   2. Scroll to 'Layers' section")
    print(f"   3. Click 'Add a layer'")
    print(f"   4. Select 'Custom layers'")
    print(f"   5. Choose 'timeback-google-dependencies'")
    print(f"   6. Version: Latest")
    print(f"   7. Click 'Add'")
    print(f"   8. Also ensure pandas/numpy layer is attached")
    print(f"\n3️⃣  UPDATE FUNCTION CODE:")
    print(f"   1. Go to 'Code' tab")
    print(f"   2. Click 'Upload from' → 'Amazon S3 location'")
    print(f"   3. Enter: s3://lwaiexpdata/{s3_key}")
    print(f"   4. Click 'Save'")
    print(f"   5. Test the function")
    print(f"\n📋 Lambda Configuration:")
    print(f"   - Handler: lambda_handler.lambda_handler")
    print(f"   - Runtime: Python 3.10")
    print(f"   - Timeout: 15 minutes")
    print(f"   - Memory: 1024 MB")
    print(f"   - Layers: timeback-google-dependencies + pandas/numpy layer")
    
    return True

if __name__ == "__main__":
    success = deploy_to_lambda()
    sys.exit(0 if success else 1)
