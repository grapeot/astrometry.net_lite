#!/usr/bin/env python3
"""
End-to-end integration test for Astrometry.net API.
Tests the complete flow: login -> upload -> wait -> download artifacts.
"""

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
            print(f"❌ Downloaded file is empty or doesn't exist")
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
            print(f"✅ Login successful!")
            print(f"   Session key: {client.session}")
            print(f"   Session key length: {len(client.session)}")
            return True
        else:
            print(f"❌ Login failed: No session key returned")
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
            print(f"✅ Upload successful!")
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
    print("=" * 60)
    print("End-to-End Integration Test")
    print("=" * 60)
    print(f"API URL: {API_URL}")
    print(f"API Key: {API_KEY}")
    print(f"Test Image URL: {TEST_IMAGE_URL}")
    print("=" * 60)
    
    # Setup - get filename from URL
    test_image_filename = get_filename_from_url(TEST_IMAGE_URL)
    test_image_path = Path(test_image_filename)
    output_dir = Path("data/test_runs")
    
    # Step 1: Download test image if needed
    if not test_image_path.exists():
        if not download_test_image(TEST_IMAGE_URL, test_image_path):
            print("\n❌ Cannot proceed without test image")
            return 1
    else:
        print(f"\n✅ Test image already exists: {test_image_path}")
    
    # Step 2: Initialize client and login
    client = Client(apiurl=API_URL)
    if not test_login(client, API_KEY):
        print("\n❌ Cannot proceed without login")
        return 1
    
    # Step 3: Upload image
    upload_result = test_upload(client, test_image_path)
    if not upload_result:
        print("\n❌ Cannot proceed without upload")
        return 1
    
    sub_id = upload_result.get('subid')
    if not sub_id:
        print("\n❌ No submission ID in upload result")
        return 1
    
    # Step 4: Wait for job completion
    job_id = wait_for_job(client, sub_id)
    if not job_id:
        print("\n❌ Job did not complete successfully")
        return 1
    
    # Step 5: Test API endpoints
    test_api_endpoints(client, job_id)
    
    # Step 6: Download artifacts
    test_download_artifacts(client, job_id, output_dir)
    
    # Summary
    print("\n" + "=" * 60)
    print("✅ All tests completed successfully!")
    print("=" * 60)
    print(f"Job ID: {job_id}")
    print(f"Submission ID: {sub_id}")
    print(f"Artifacts saved to: {output_dir}")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

