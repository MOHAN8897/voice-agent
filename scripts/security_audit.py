#!/usr/bin/env python3
"""Unified security testing runner for Semgrep, OWASP ZAP, and Strix.

Usage:
    python scripts/security_audit.py --mode sast
    python scripts/security_audit.py --mode zap --target http://localhost:8000
    python scripts/security_audit.py --mode strix --target http://localhost:8000
    python scripts/security_audit.py --all
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys


def run_cmd(cmd: list[str], description: str) -> int:
    print(f"\n[+] Running {description}...")
    print(f"    Command: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode == 0:
        print(f"[PASS] {description} passed successfully.")
    else:
        print(f"[FAIL] {description} exited with status code {result.returncode}.")
    return result.returncode


def run_semgrep() -> int:
    cmd = [
        "semgrep",
        "scan",
        "--error",
        "--config", "p/owasp-top-ten",
        "--config", "p/security-audit",
        "--config", ".semgrep.yml",
        "server/",
        "voxly-ai/src/",
    ]
    return run_cmd(cmd, "Semgrep SAST Security Analysis")


def run_zap(target: str) -> int:
    cmd = [
        "docker",
        "run",
        "--rm",
        "-t",
        "zaproxy/zap-stable",
        "zap-baseline.py",
        "-t", target,
        "-g", "gen.conf",
        "-r", "zap_report.html",
    ]
    return run_cmd(cmd, f"OWASP ZAP Dynamic Scan against {target}")


def run_strix(target: str) -> int:
    cmd = [
        "docker",
        "run",
        "--rm",
        "-e", f"OPENAI_API_KEY={os.getenv('OPENAI_API_KEY', '')}",
        "ghcr.io/usestrix/strix:latest",
        "--target", target,
    ]
    return run_cmd(cmd, f"Strix Autonomous Agent Testing against {target}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-Tool Security Testing Suite")
    parser.add_argument("--mode", choices=["sast", "zap", "strix", "all"], default="sast", help="Security scan mode")
    parser.add_argument("--target", default="http://localhost:8000", help="Target URL for active scans (ZAP/Strix)")
    args = parser.parse_args()

    rc = 0
    if args.mode in ("sast", "all"):
        rc |= run_semgrep()
    if args.mode in ("zap", "all"):
        rc |= run_zap(args.target)
    if args.mode in ("strix", "all"):
        rc |= run_strix(args.target)

    sys.exit(rc)


if __name__ == "__main__":
    main()
