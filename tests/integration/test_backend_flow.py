#!/usr/bin/env python3
"""Smoke-test the FastAPI backend by mimicking the legacy client flow."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx

DEFAULT_API_BASE = os.environ.get("TEST_API_BASE", "http://127.0.0.1:8002/api")
DEFAULT_API_KEY = os.environ.get("TEST_API_KEY", "1jcrmadfnxngxscd")
DEFAULT_IMAGE = os.environ.get("TEST_IMAGE", "test.jpg")


class BackendTester:
    def __init__(self, api_base: str, apikey: str, image_path: Path, poll_interval: float = 3.0):
        self.api_base = api_base.rstrip("/")
        self.image_path = image_path
        self.apikey = apikey
        self.poll_interval = poll_interval
        self.session = httpx.Client(timeout=60)
        self.session_token = None
        self.job_id = None
        self.submission_id = None

    def login(self) -> None:
        resp = self.session.post(f"{self.api_base}/login", json={"apikey": self.apikey})
        data = resp.json()
        if data.get("status") != "success":
            raise RuntimeError(f"Login failed: {data}")
        self.session_token = data["session"]
        print(f"[login] session={self.session_token}")

    def upload(self) -> None:
        if not self.session_token:
            raise RuntimeError("No session token; call login first")
        payload = {"session": self.session_token}
        data = {"request-json": json.dumps(payload)}
        with self.image_path.open("rb") as fh:
            files = [("file", (self.image_path.name, fh, "application/octet-stream"))]
            resp = self.session.post(f"{self.api_base}/upload", data=data, files=files)
        data = resp.json()
        if data.get("status") != "success":
            raise RuntimeError(f"Upload failed: {data}")
        self.submission_id = data.get("subid")
        self.job_id = data.get("job_id")
        print(f"[upload] subid={self.submission_id} job_id={self.job_id}")

    def poll_job(self) -> None:
        if not self.job_id:
            raise RuntimeError("Missing job id")
        while True:
            resp = self.session.get(f"{self.api_base}/jobs/{self.job_id}")
            data = resp.json()
            status = data.get("status")
            print(f"[poll] job={self.job_id} status={status}")
            if status in {"success", "failure"}:
                if status != "success":
                    raise RuntimeError(f"Job failed: {data}")
                break
            time.sleep(self.poll_interval)

    def fetch_details(self) -> None:
        assert self.job_id is not None
        cal = self.session.get(f"{self.api_base}/jobs/{self.job_id}/calibration").json()
        info = self.session.get(f"{self.api_base}/jobs/{self.job_id}/info").json()
        print("[calibration]", cal)
        print("[info]", info)

    def download_artifacts(self, out_dir: Path) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        assert self.job_id is not None
        endpoints = {
            "wcs": f"/wcs_file/{self.job_id}",
            "newfits": f"/new_fits_file/{self.job_id}/",
            "corr": f"/corr_file/{self.job_id}",
            "annotated": f"/annotated_display/{self.job_id}",
        }
        for name, path in endpoints.items():
            url = f"{self.api_base.replace('/api', '')}{path}"
            resp = self.session.get(url)
            if resp.status_code != 200:
                print(f"[warn] unable to download {name}: {resp.status_code}")
                continue
            target = out_dir / f"job{self.job_id}_{name}"
            target.write_bytes(resp.content)
            print(f"[download] saved {target}")

    def run(self) -> None:
        if not self.image_path.exists():
            raise FileNotFoundError(self.image_path)
        self.login()
        self.upload()
        self.poll_job()
        self.fetch_details()
        self.download_artifacts(Path("data/test_runs"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Test the Astrometry Lite backend")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--apikey", default=DEFAULT_API_KEY)
    parser.add_argument("--file", default=DEFAULT_IMAGE)
    parser.add_argument("--poll", type=float, default=3.0, help="poll interval seconds")
    args = parser.parse_args()

    tester = BackendTester(
        api_base=args.api_base,
        apikey=args.apikey,
        image_path=Path(args.file),
        poll_interval=args.poll,
    )
    tester.run()


if __name__ == "__main__":
    sys.exit(main())
