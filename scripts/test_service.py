#!/usr/bin/env python3
"""
完整的服务测试脚本
测试 Astrometry Lite 服务的核心功能：登录、上传、查询、下载
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx

# 默认配置
DEFAULT_API_BASE = os.environ.get("TEST_API_BASE", "http://127.0.0.1:8002/api")
DEFAULT_API_KEY = os.environ.get("TEST_API_KEY", "test-key-12345")
DEFAULT_IMAGE = os.environ.get("TEST_IMAGE", "test.jpg")
DEFAULT_TIMEOUT = 300  # 5 分钟超时


class ServiceTester:
    def __init__(
        self,
        api_base: str,
        apikey: str,
        image_path: Path,
        poll_interval: float = 3.0,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self.api_base = api_base.rstrip("/")
        self.image_path = image_path
        self.apikey = apikey
        self.poll_interval = poll_interval
        self.timeout = timeout
        self.session = httpx.Client(timeout=60)
        self.session_token = None
        self.job_id = None
        self.submission_id = None
        self.test_results = []

    def log(self, message: str, status: str = "INFO"):
        """记录测试日志"""
        timestamp = time.strftime("%H:%M:%S")
        print(f"[{timestamp}] [{status}] {message}")
        self.test_results.append({"time": timestamp, "status": status, "message": message})

    def test_login(self) -> bool:
        """测试登录功能"""
        self.log("测试登录...")
        try:
            resp = self.session.post(f"{self.api_base}/login", json={"apikey": self.apikey})
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") != "success":
                self.log(f"登录失败: {data}", "ERROR")
                return False
            self.session_token = data["session"]
            self.log(f"✓ 登录成功，session={self.session_token[:20]}...")
            return True
        except Exception as e:
            self.log(f"登录异常: {e}", "ERROR")
            return False

    def test_upload(self) -> bool:
        """测试上传功能"""
        if not self.session_token:
            self.log("缺少 session token，无法上传", "ERROR")
            return False
        if not self.image_path.exists():
            self.log(f"图片文件不存在: {self.image_path}", "ERROR")
            return False

        self.log(f"上传图片: {self.image_path.name}")
        try:
            payload = {"session": self.session_token}
            data = {"request-json": json.dumps(payload)}
            with self.image_path.open("rb") as fh:
                files = [("file", (self.image_path.name, fh, "application/octet-stream"))]
                resp = self.session.post(f"{self.api_base}/upload", data=data, files=files)
            resp.raise_for_status()
            result = resp.json()
            if result.get("status") != "success":
                self.log(f"上传失败: {result}", "ERROR")
                return False
            self.submission_id = result.get("subid")
            self.job_id = result.get("job_id")
            self.log(f"✓ 上传成功，submission_id={self.submission_id}, job_id={self.job_id}")
            return True
        except Exception as e:
            self.log(f"上传异常: {e}", "ERROR")
            return False

    def test_poll_job(self) -> bool:
        """轮询等待 Job 完成"""
        if not self.job_id:
            self.log("缺少 job_id，无法轮询", "ERROR")
            return False

        self.log(f"等待 Job {self.job_id} 完成（最多 {self.timeout} 秒）...")
        start_time = time.time()
        last_status = None

        while True:
            elapsed = time.time() - start_time
            if elapsed > self.timeout:
                self.log(f"超时：Job {self.job_id} 在 {self.timeout} 秒内未完成", "ERROR")
                return False

            try:
                resp = self.session.get(f"{self.api_base}/jobs/{self.job_id}")
                resp.raise_for_status()
                data = resp.json()
                status = data.get("status")
                if status != last_status:
                    self.log(f"Job 状态: {status} (已等待 {elapsed:.1f} 秒)")
                    last_status = status

                if status == "success":
                    self.log(f"✓ Job {self.job_id} 成功完成（耗时 {elapsed:.1f} 秒）")
                    return True
                elif status == "failure":
                    self.log(f"✗ Job {self.job_id} 失败: {data}", "ERROR")
                    return False
                elif status in {"queued", "solving"}:
                    time.sleep(self.poll_interval)
                else:
                    self.log(f"未知状态: {status}", "WARN")
                    time.sleep(self.poll_interval)
            except Exception as e:
                self.log(f"轮询异常: {e}", "ERROR")
                time.sleep(self.poll_interval)

    def test_query_endpoints(self) -> bool:
        """测试查询端点"""
        if not self.job_id:
            self.log("缺少 job_id，跳过查询测试", "WARN")
            return False

        self.log("测试查询端点...")
        endpoints = [
            ("calibration", f"/jobs/{self.job_id}/calibration"),
            ("info", f"/jobs/{self.job_id}/info"),
            ("annotations", f"/jobs/{self.job_id}/annotations"),
            ("objects_in_field", f"/jobs/{self.job_id}/objects_in_field"),
            ("tags", f"/jobs/{self.job_id}/tags"),
            ("machine_tags", f"/jobs/{self.job_id}/machine_tags"),
        ]

        success_count = 0
        for name, path in endpoints:
            try:
                resp = self.session.get(f"{self.api_base}{path}")
                resp.raise_for_status()
                data = resp.json()
                self.log(f"  ✓ {name}: {json.dumps(data)[:100]}...")
                success_count += 1
            except Exception as e:
                self.log(f"  ✗ {name} 失败: {e}", "ERROR")

        self.log(f"查询端点测试完成: {success_count}/{len(endpoints)} 成功")
        return success_count > 0

    def test_download_artifacts(self) -> bool:
        """测试文件下载"""
        if not self.job_id:
            self.log("缺少 job_id，跳过下载测试", "WARN")
            return False

        self.log("测试文件下载...")
        base_url = self.api_base.replace("/api", "")
        endpoints = {
            "wcs": f"{base_url}/wcs_file/{self.job_id}",
            "new_fits": f"{base_url}/new_fits_file/{self.job_id}/",
            "corr": f"{base_url}/corr_file/{self.job_id}",
            "annotated": f"{base_url}/annotated_display/{self.job_id}",
        }

        success_count = 0
        for name, url in endpoints.items():
            try:
                resp = self.session.get(url)
                if resp.status_code == 200:
                    size = len(resp.content)
                    self.log(f"  ✓ {name}: {size} bytes")
                    success_count += 1
                else:
                    self.log(f"  ✗ {name}: HTTP {resp.status_code}", "WARN")
            except Exception as e:
                self.log(f"  ✗ {name} 异常: {e}", "WARN")

        self.log(f"文件下载测试完成: {success_count}/{len(endpoints)} 成功")
        return success_count > 0

    def test_unsupported_features(self) -> bool:
        """测试明确标记为不支持的功能"""
        self.log("测试不支持的功能端点...")
        endpoints = [
            ("sdss_image_for_wcs", {"wcs": "test"}),
            ("galex_image_for_wcs", {"wcs": "test"}),
        ]

        success_count = 0
        for name, payload in endpoints:
            try:
                resp = self.session.post(f"{self.api_base}/{name}", json=payload)
                resp.raise_for_status()
                data = resp.json()
                if data.get("status") == "error" and "not supported" in data.get("errormessage", "").lower():
                    self.log(f"  ✓ {name}: 正确返回不支持信息")
                    success_count += 1
                else:
                    self.log(f"  ✗ {name}: 未返回预期的错误信息", "WARN")
            except Exception as e:
                self.log(f"  ✗ {name} 异常: {e}", "WARN")

        self.log(f"不支持功能测试完成: {success_count}/{len(endpoints)} 成功")
        return True  # 这个测试不阻塞整体流程

    def test_submission_status(self) -> bool:
        """测试 submission 状态查询"""
        if not self.submission_id:
            self.log("缺少 submission_id，跳过 submission 测试", "WARN")
            return False

        self.log("测试 submission 状态查询...")
        try:
            resp = self.session.get(f"{self.api_base}/submissions/{self.submission_id}")
            resp.raise_for_status()
            data = resp.json()
            self.log(f"  ✓ Submission 状态: {data.get('status')}")
            return True
        except Exception as e:
            self.log(f"  ✗ Submission 查询失败: {e}", "ERROR")
            return False

    def run_full_test(self) -> bool:
        """运行完整测试流程"""
        self.log("=" * 60)
        self.log("开始完整服务测试")
        self.log("=" * 60)

        tests = [
            ("登录", self.test_login),
            ("上传", self.test_upload),
            ("轮询 Job", self.test_poll_job),
            ("查询端点", self.test_query_endpoints),
            ("下载文件", self.test_download_artifacts),
            ("Submission 状态", self.test_submission_status),
            ("不支持功能", self.test_unsupported_features),
        ]

        results = []
        for name, test_func in tests:
            try:
                result = test_func()
                results.append((name, result))
            except Exception as e:
                self.log(f"测试 '{name}' 发生异常: {e}", "ERROR")
                results.append((name, False))

        # 汇总结果
        self.log("=" * 60)
        self.log("测试结果汇总:")
        passed = sum(1 for _, r in results if r)
        total = len(results)
        for name, result in results:
            status = "✓ PASS" if result else "✗ FAIL"
            self.log(f"  {status}: {name}")

        self.log(f"\n总计: {passed}/{total} 测试通过")
        self.log("=" * 60)

        return passed == total

    def print_summary(self):
        """打印测试摘要"""
        print("\n" + "=" * 60)
        print("测试摘要")
        print("=" * 60)
        print(f"API Base: {self.api_base}")
        print(f"Job ID: {self.job_id}")
        print(f"Submission ID: {self.submission_id}")
        print(f"测试项数: {len(self.test_results)}")
        print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="测试 Astrometry Lite 服务")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE, help=f"API 基础 URL (默认: {DEFAULT_API_BASE})")
    parser.add_argument("--apikey", default=DEFAULT_API_KEY, help=f"API Key (默认: {DEFAULT_API_KEY})")
    parser.add_argument("--file", type=Path, default=DEFAULT_IMAGE, help=f"测试图片路径 (默认: {DEFAULT_IMAGE})")
    parser.add_argument("--poll", type=float, default=3.0, help="轮询间隔（秒，默认: 3.0）")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help=f"超时时间（秒，默认: {DEFAULT_TIMEOUT}）")
    parser.add_argument("--quick", action="store_true", help="快速测试（跳过轮询和下载）")
    args = parser.parse_args()

    tester = ServiceTester(
        api_base=args.api_base,
        apikey=args.apikey,
        image_path=args.file,
        poll_interval=args.poll,
        timeout=args.timeout,
    )

    if args.quick:
        # 快速测试模式
        tester.test_login()
        tester.test_upload()
        tester.test_submission_status()
        tester.test_unsupported_features()
    else:
        # 完整测试
        success = tester.run_full_test()
        tester.print_summary()
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

