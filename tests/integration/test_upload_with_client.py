#!/usr/bin/env python3
"""Test upload using the original net/client client."""

import sys
import time
from pathlib import Path

# Add net directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "net"))

from client.client import Client

# Our local server
API_URL = "http://127.0.0.1:8002/api/"
API_KEY = "1"

def test_upload(client, image_path):
    """Test uploading an image."""
    print("=" * 60)
    print(f"Test: Upload image {image_path}")
    print("=" * 60)
    
    if not Path(image_path).exists():
        print(f"❌ Image file not found: {image_path}")
        return None
    
    try:
        result = client.upload(image_path)
        print(f"✅ Upload successful!")
        print(f"   Submission ID: {result.get('subid')}")
        print(f"   Jobs: {result.get('jobs', [])}")
        return result
    except Exception as e:
        print(f"❌ Upload failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def wait_for_job(client, sub_id, timeout=300):
    """Wait for job to complete."""
    print("\n" + "=" * 60)
    print(f"Waiting for job completion (submission {sub_id})...")
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
                    
                    print(f"  Job {job_id} status: {stat}")
                    
                    if stat == 'success':
                        print(f"✅ Job {job_id} completed successfully!")
                        return job_id
                    elif stat == 'failure':
                        print(f"❌ Job {job_id} failed")
                        return None
            else:
                print(f"  No jobs yet, waiting...")
            
            time.sleep(5)
        except Exception as e:
            print(f"  Error checking status: {e}")
            time.sleep(5)
    
    print(f"⏱️  Timeout waiting for job completion")
    return job_id

def main():
    """Run upload test."""
    print(f"Testing upload API at: {API_URL}")
    print(f"Using API key: {API_KEY}\n")
    
    # Login
    client = Client(apiurl=API_URL)
    try:
        client.login(API_KEY)
        print(f"✅ Logged in with session: {client.session}\n")
    except Exception as e:
        print(f"❌ Login failed: {e}")
        return 1
    
    # Find a test image
    test_images = [
        "test.jpg",
        "data/uploads/test.jpg",
    ]
    
    image_path = None
    for path in test_images:
        if Path(path).exists():
            image_path = path
            break
    
    if not image_path:
        print("❌ No test image found. Please provide an image path.")
        print("   Usage: python tests/integration/test_upload_with_client.py <image_path>")
        if len(sys.argv) > 1:
            image_path = sys.argv[1]
        else:
            return 1
    
    # Upload
    upload_result = test_upload(client, image_path)
    if not upload_result:
        return 1
    
    sub_id = upload_result.get('subid')
    if not sub_id:
        print("❌ No submission ID in upload result")
        return 1
    
    # Wait for job
    job_id = wait_for_job(client, sub_id)
    
    if job_id:
        # Get job details
        print("\n" + "=" * 60)
        print(f"Job {job_id} Details")
        print("=" * 60)
        
        try:
            job_info = client.send_request(f'jobs/{job_id}/info', {})
            print(f"✅ Job info:")
            print(f"   Status: {job_info.get('status')}")
            print(f"   Objects in field: {len(job_info.get('objects_in_field', []))}")
            if job_info.get('calibration'):
                cal = job_info['calibration']
                print(f"   RA: {cal.get('ra'):.4f}")
                print(f"   Dec: {cal.get('dec'):.4f}")
                print(f"   Radius: {cal.get('radius'):.4f} deg")
        except Exception as e:
            print(f"⚠️  Error getting job info: {e}")
    
    print("\n" + "=" * 60)
    print("✅ Upload test completed!")
    print("=" * 60)
    return 0

if __name__ == "__main__":
    sys.exit(main())

