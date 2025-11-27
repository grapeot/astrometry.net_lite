#!/usr/bin/env python3
"""Test our API using the original net/client client."""

import sys
from pathlib import Path

# Add net directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "net"))

from client.client import Client

# Our local server
API_URL = "http://127.0.0.1:8002/api/"
API_KEY = "1"

def test_login():
    """Test login."""
    print("=" * 60)
    print("Test 1: Login")
    print("=" * 60)
    client = Client(apiurl=API_URL)
    try:
        client.login(API_KEY)
        print(f"✅ Login successful! Session: {client.session}")
        return client
    except Exception as e:
        print(f"❌ Login failed: {e}")
        return None

def test_myjobs(client):
    """Test myjobs."""
    print("\n" + "=" * 60)
    print("Test 2: Get my jobs")
    print("=" * 60)
    try:
        jobs = client.myjobs()
        print(f"✅ Got {len(jobs)} jobs")
        if jobs:
            print(f"   First few job IDs: {jobs[:5]}")
        return jobs
    except Exception as e:
        print(f"❌ myjobs failed: {e}")
        import traceback
        traceback.print_exc()
        return []

def test_job_status(client, job_id):
    """Test job status."""
    print("\n" + "=" * 60)
    print(f"Test 3: Get job {job_id} status")
    print("=" * 60)
    try:
        result = client.job_status(job_id, justdict=True)
        print(f"✅ Job status: {result.get('status')}")
        print(f"   Full result: {result}")
        return result
    except Exception as e:
        print(f"❌ job_status failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_submission_status(client, sub_id):
    """Test submission status."""
    print("\n" + "=" * 60)
    print(f"Test 4: Get submission {sub_id} status")
    print("=" * 60)
    try:
        result = client.sub_status(sub_id, justdict=True)
        print(f"✅ Submission status: {result.get('status')}")
        print(f"   Jobs: {result.get('jobs', [])}")
        return result
    except Exception as e:
        print(f"❌ sub_status failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_job_calibration(client, job_id):
    """Test job calibration."""
    print("\n" + "=" * 60)
    print(f"Test 5: Get job {job_id} calibration")
    print("=" * 60)
    try:
        result = client.send_request(f'jobs/{job_id}/calibration', {})
        print(f"✅ Calibration data retrieved")
        print(f"   Result: {result}")
        return result
    except Exception as e:
        print(f"❌ calibration failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_job_info(client, job_id):
    """Test job info."""
    print("\n" + "=" * 60)
    print(f"Test 6: Get job {job_id} info")
    print("=" * 60)
    try:
        result = client.send_request(f'jobs/{job_id}/info', {})
        print(f"✅ Job info retrieved")
        print(f"   Status: {result.get('status')}")
        print(f"   Objects in field: {len(result.get('objects_in_field', []))}")
        return result
    except Exception as e:
        print(f"❌ job_info failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    """Run all tests."""
    print(f"Testing API at: {API_URL}")
    print(f"Using API key: {API_KEY}\n")
    
    # Test 1: Login
    client = test_login()
    if not client:
        print("\n❌ Cannot proceed without login")
        return 1
    
    # Test 2: Get my jobs
    jobs = test_myjobs(client)
    
    # Test 3-6: Test with a specific job if available
    if jobs:
        job_id = jobs[0]
        test_job_status(client, job_id)
        test_job_calibration(client, job_id)
        test_job_info(client, job_id)
        
        # Get submission ID from job
        job_status = client.job_status(job_id, justdict=True)
        # Note: We'd need to track submission_id differently in our system
        # For now, just test job endpoints
    else:
        print("\n⚠️  No jobs found, skipping job-specific tests")
        print("   You can upload an image first to create a job")
    
    print("\n" + "=" * 60)
    print("✅ All tests completed!")
    print("=" * 60)
    return 0

if __name__ == "__main__":
    sys.exit(main())

