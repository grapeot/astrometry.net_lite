#!/usr/bin/env python3
"""
End-to-end integration test for Astrometry.net API.
Tests the complete flow: login -> upload -> wait -> download artifacts.
"""

import argparse
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

# Add tests/integration to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from client import Client

# Configuration
API_URL = "http://127.0.0.1:8002/api/"
API_KEY = "1"
TEST_IMAGE_URL = "https://www.astrovox.gr/uploads/monthly_2018_11/large.cdd0f09bb000b7fb70d7a928861cfe74.jpg.9c50a409a68626591c33b3fee25ec522.jpg"
TIMEOUT = 300  # 5 minutes


def get_filename_from_url(url: str) -> str:
    """Extract filename from URL."""
    parsed = urllib.parse.urlparse(url)
    filename = Path(parsed.path).name
    # If filename is empty or doesn't have extension, use a default
    if not filename or '.' not in filename:
        return "test_image.jpg"
    return filename


def download_test_image(url: str, output_path: Path) -> bool:
    """Download test image from URL."""
    print("=" * 60)
    print(f"Downloading test image from: {url}")
    print("=" * 60)
    try:
        urllib.request.urlretrieve(url, output_path)
        if output_path.exists() and output_path.stat().st_size > 0:
            print(f"✅ Downloaded test image: {output_path} ({output_path.stat().st_size} bytes)")
            return True
        else:
            print("❌ Downloaded file is empty or doesn't exist")
            return False
    except Exception as e:
        print(f"❌ Failed to download test image: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_login(client: Client, api_key: str) -> bool:
    """Test login and verify session key."""
    print("\n" + "=" * 60)
    print("Test 1: Login")
    print("=" * 60)
    try:
        client.login(api_key)
        if client.session:
            print("✅ Login successful!")
            print(f"   Session key: {client.session}")
            print(f"   Session key length: {len(client.session)}")
            return True
        else:
            print("❌ Login failed: No session key returned")
            return False
    except Exception as e:
        print(f"❌ Login failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_upload(client: Client, image_path: Path) -> dict:
    """Test uploading an image."""
    print("\n" + "=" * 60)
    print(f"Test 2: Upload image {image_path.name}")
    print("=" * 60)
    
    if not image_path.exists():
        print(f"❌ Image file not found: {image_path}")
        return None
    
    try:
        result = client.upload(str(image_path))
        if result.get('status') == 'success':
            print("✅ Upload successful!")
            print(f"   Submission ID: {result.get('subid')}")
            print(f"   Jobs: {result.get('jobs', [])}")
            return result
        else:
            print(f"❌ Upload failed: {result}")
            return None
    except Exception as e:
        print(f"❌ Upload failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_url_upload(client: Client, image_url: str) -> dict:
    """Test uploading an image from URL."""
    print("\n" + "=" * 60)
    print("Test 2: Upload image from URL")
    print("=" * 60)
    print(f"URL: {image_url}")
    print("=" * 60)
    
    try:
        result = client.url_upload(image_url)
        if result.get('status') == 'success':
            print("✅ URL upload successful!")
            print(f"   Submission ID: {result.get('subid')}")
            print(f"   Jobs: {result.get('jobs', [])}")
            return result
        else:
            print(f"❌ URL upload failed: {result}")
            return None
    except Exception as e:
        print(f"❌ URL upload failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def wait_for_job(client: Client, sub_id: int, timeout: int = TIMEOUT) -> int:
    """Wait for job to complete and return job_id."""
    print("\n" + "=" * 60)
    print(f"Test 3: Wait for job completion (submission {sub_id})")
    print("=" * 60)
    
    start_time = time.time()
    job_id = None
    
    while time.time() - start_time < timeout:
        try:
            status = client.sub_status(sub_id, justdict=True)
            jobs = status.get('jobs', [])
            
            if jobs:
                # Find first non-None job
                for j in jobs:
                    if j is not None:
                        job_id = j
                        break
                
                if job_id:
                    job_status = client.job_status(job_id, justdict=True)
                    stat = job_status.get('status')
                    elapsed = time.time() - start_time
                    
                    print(f"  Job {job_id} status: {stat} (elapsed: {elapsed:.1f}s)")
                    
                    if stat == 'success':
                        print(f"✅ Job {job_id} completed successfully!")
                        return job_id
                    elif stat == 'failure':
                        print(f"❌ Job {job_id} failed")
                        return None
            
            time.sleep(5)
        except Exception as e:
            print(f"  Error checking status: {e}")
            time.sleep(5)
    
    print(f"⏱️  Timeout waiting for job completion after {timeout}s")
    return job_id


def test_download_artifacts(client: Client, job_id: int, output_dir: Path) -> bool:
    """Test downloading WCS, FITS, CORR, and annotated image files."""
    print("\n" + "=" * 60)
    print(f"Test 4: Download artifacts for job {job_id}")
    print("=" * 60)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Base URL without /api
    base_url = client.apiurl.replace('/api/', '')
    
    artifacts = {
        "wcs": f"{base_url}/wcs_file/{job_id}",
        "new_fits": f"{base_url}/new_fits_file/{job_id}/",
        "corr": f"{base_url}/corr_file/{job_id}",
        "annotated": f"{base_url}/annotated_display/{job_id}",
    }
    
    success_count = 0
    for name, url in artifacts.items():
        try:
            print(f"  Downloading {name} from {url}...")
            from urllib.request import urlopen, Request
            
            request = Request(url)
            with urlopen(request) as response:
                content = response.read()
                if len(content) > 0:
                    output_path = output_dir / f"job{job_id}_{name}"
                    if name == "wcs":
                        output_path = output_dir / f"job{job_id}_wcs.fits"
                    elif name == "annotated":
                        output_path = output_dir / f"job{job_id}_annotated.jpg"
                    elif name == "new_fits":
                        output_path = output_dir / f"job{job_id}_new.fits"
                    elif name == "corr":
                        output_path = output_dir / f"job{job_id}_corr.txt"
                    
                    output_path.write_bytes(content)
                    print(f"  ✅ {name}: {len(content)} bytes -> {output_path}")
                    success_count += 1
                else:
                    print(f"  ❌ {name}: Empty response")
        except Exception as e:
            print(f"  ❌ {name} failed: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n✅ Downloaded {success_count}/{len(artifacts)} artifacts")
    return success_count > 0


def test_api_endpoints(client: Client, job_id: int) -> bool:
    """Test various API endpoints."""
    print("\n" + "=" * 60)
    print(f"Test 5: Test API endpoints for job {job_id}")
    print("=" * 60)
    
    endpoints = [
        ("calibration", f'jobs/{job_id}/calibration'),
        ("info", f'jobs/{job_id}/info'),
        ("annotations", f'jobs/{job_id}/annotations'),
        ("objects_in_field", f'jobs/{job_id}/objects_in_field'),
        ("tags", f'jobs/{job_id}/tags'),
        ("machine_tags", f'jobs/{job_id}/machine_tags'),
    ]
    
    success_count = 0
    for name, service in endpoints:
        try:
            result = client.send_request(service, {})
            print(f"  ✅ {name}: {str(result)[:100]}...")
            success_count += 1
        except Exception as e:
            print(f"  ❌ {name} failed: {e}")
    
    print(f"\n✅ Tested {success_count}/{len(endpoints)} endpoints")
    return success_count > 0


def main():
    """Run complete end-to-end test."""
    parser = argparse.ArgumentParser(
        description="End-to-end integration test for Astrometry.net API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test file upload (default)
  python test_e2e.py
  
  # Test URL upload
  python test_e2e.py --url-upload
  
  # Test both file and URL upload
  python test_e2e.py --both
  
  # Use custom image URL
  python test_e2e.py --url-upload --image-url "https://example.com/image.jpg"
        """
    )
    parser.add_argument(
        "--url-upload",
        action="store_true",
        help="Test URL upload instead of file upload"
    )
    parser.add_argument(
        "--both",
        action="store_true",
        help="Test both file upload and URL upload"
    )
    parser.add_argument(
        "--image-url",
        type=str,
        default=TEST_IMAGE_URL,
        help=f"Image URL for URL upload test (default: {TEST_IMAGE_URL})"
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default=API_URL,
        help=f"API base URL (default: {API_URL})"
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=API_KEY,
        help=f"API key (default: {API_KEY})"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("End-to-End Integration Test")
    print("=" * 60)
    print(f"API URL: {args.api_url}")
    print(f"API Key: {args.api_key}")
    print(f"Test Image URL: {args.image_url}")
    if args.url_upload:
        print("Mode: URL Upload")
    elif args.both:
        print("Mode: Both File and URL Upload")
    else:
        print("Mode: File Upload (default)")
    print("=" * 60)
    
    output_dir = Path("data/test_runs")
    
    # Step 1: Initialize client and login
    client = Client(apiurl=args.api_url)
    if not test_login(client, args.api_key):
        print("\n❌ Cannot proceed without login")
        return 1
    
    # Determine which tests to run
    test_file_upload = not args.url_upload or args.both
    test_url_upload = args.url_upload or args.both
    
    results = []
    
    # Test file upload if needed
    if test_file_upload:
        # Setup - get filename from URL
        test_image_filename = get_filename_from_url(args.image_url)
        test_image_path = Path(test_image_filename)
        
        # Download test image if needed
        if not test_image_path.exists():
            if not download_test_image(args.image_url, test_image_path):
                print("\n❌ Cannot proceed without test image")
                return 1
        else:
            print(f"\n✅ Test image already exists: {test_image_path}")
        
        # Upload image file
        upload_result = test_upload(client, test_image_path)
        if not upload_result:
            print("\n❌ File upload failed")
            if not args.both:
                return 1
        else:
            sub_id = upload_result.get('subid')
            if sub_id:
                job_id = wait_for_job(client, sub_id)
                if job_id:
                    test_api_endpoints(client, job_id)
                    test_download_artifacts(client, job_id, output_dir)
                    results.append(("file_upload", sub_id, job_id))
    
    # Test URL upload if needed
    if test_url_upload:
        upload_result = test_url_upload(client, args.image_url)
        if not upload_result:
            print("\n❌ URL upload failed")
            if not args.both:
                return 1
        else:
            sub_id = upload_result.get('subid')
            if sub_id:
                job_id = wait_for_job(client, sub_id)
                if job_id:
                    test_api_endpoints(client, job_id)
                    test_download_artifacts(client, job_id, output_dir)
                    results.append(("url_upload", sub_id, job_id))
    
    # Summary
    print("\n" + "=" * 60)
    print("✅ All tests completed successfully!")
    print("=" * 60)
    for test_type, sub_id, job_id in results:
        print(f"{test_type}:")
        print(f"  Job ID: {job_id}")
        print(f"  Submission ID: {sub_id}")
    print(f"Artifacts saved to: {output_dir}")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

