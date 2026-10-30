#!/usr/bin/env python3
"""Repeatable local SAST and explicitly targeted non-production security scans."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
BLOCKED = 3


def run_cmd(cmd: list[str], description: str, *, timeout: int = 900) -> int:
    print(f"[+] {description}", flush=True)
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    try:
        result = subprocess.run(cmd, cwd=ROOT, timeout=timeout, env=env, check=False)
    except FileNotFoundError:
        print(f"[BLOCKED] Required executable is unavailable: {cmd[0]}", flush=True)
        return BLOCKED
    except subprocess.TimeoutExpired:
        print(f"[INCOMPLETE] {description} exceeded its time limit.", flush=True)
        return BLOCKED
    print(f"[{'PASS' if result.returncode == 0 else 'FAIL'}] {description}: exit {result.returncode}", flush=True)
    return result.returncode


def validate_target(target: str) -> str:
    parsed = urlsplit(target)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError('Use an http(s) URL without credentials or fragments for an authorized non-production target.')
    _ = parsed.port  # Validate malformed/out-of-range ports as well.
    return target


def docker_target(target: str) -> str:
    parsed = urlsplit(validate_target(target))
    if parsed.hostname in {'localhost', '127.0.0.1', '::1'}:
        authority = 'host.docker.internal' + (f':{parsed.port}' if parsed.port else '')
        return urlunsplit((parsed.scheme, authority, parsed.path, parsed.query, ''))
    return target


def docker_ready() -> bool:
    if not shutil.which('docker'):
        print('[BLOCKED] Docker is not installed or not on PATH. ZAP and local Strix require Docker.', flush=True)
        return False
    try:
        ready = subprocess.run(['docker', 'info', '--format', '{{.ServerVersion}}'], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=15, check=False).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        ready = False
    if not ready:
        print('[BLOCKED] Docker daemon is unavailable.', flush=True)
    return ready


def run_semgrep() -> int:
    reports = ROOT / '.gravitas' / 'security-reports'
    reports.mkdir(parents=True, exist_ok=True)
    return run_cmd([
        'semgrep', 'scan', '--error', '--no-git-ignore', '--timeout', '20', '--config', 'p/owasp-top-ten', '--config', 'p/security-audit',
        '--config', '.semgrep.yml', '--json-output', str(reports / 'semgrep.json'),
        'server/', 'worker/', 'scripts/', 'dialtact-app/src/', 'web/app/', 'web/lib/', 'web/components/',
    ], 'Semgrep SAST')


def run_zap(target: str) -> int:
    target = docker_target(target)
    if not docker_ready():
        return BLOCKED
    reports = ROOT / '.gravitas' / 'security-reports' / 'zap'
    reports.mkdir(parents=True, exist_ok=True)
    return run_cmd([
        'docker', 'run', '--rm', '--add-host=host.docker.internal:host-gateway',
        '-v', f'{reports}:/zap/wrk:rw', '-v', f'{ROOT / ".zap"}:/zap/config:ro',
        'ghcr.io/zaproxy/zaproxy:stable', 'zap-baseline.py', '-t', target,
        '-c', '/zap/config/rules.tsv', '-r', 'report.html', '-J', 'report.json',
    ], 'OWASP ZAP baseline')


def run_strix(target: str, budget: float = 5.0) -> int:
    validate_target(target)
    if not docker_ready():
        return BLOCKED
    if not shutil.which('strix'):
        print('[BLOCKED] Install the official strix-agent CLI (for example: pipx install strix-agent).', flush=True)
        return BLOCKED
    if not os.environ.get('STRIX_LLM') or not os.environ.get('LLM_API_KEY'):
        print('[BLOCKED] Configure STRIX_LLM and LLM_API_KEY for the local scanner.', flush=True)
        return BLOCKED
    # Official CLI creates strix_runs/ reports. Credentials stay in the environment.
    return run_cmd(['strix', '-n', '-t', target, '--scan-mode', 'quick', '--max-budget', str(budget)],
                   'Strix autonomous security scan', timeout=1800)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['sast', 'zap', 'strix', 'all'], default='sast')
    parser.add_argument('--target', help='Explicitly authorized non-production http(s) URL for ZAP/Strix')
    parser.add_argument('--budget', type=float, default=5.0, help='Maximum Strix model cost in USD (default: 5)')
    args = parser.parse_args()
    if args.mode != 'sast':
        if not args.target:
            parser.error('--target is required for active scans; use a non-production target you are authorized to test')
        try:
            validate_target(args.target)
        except ValueError as exc:
            parser.error(str(exc))
    if not 0 < args.budget <= 100:
        parser.error('--budget must be greater than zero and at most 100 USD')
    results = []
    if args.mode in {'sast', 'all'}:
        results.append(run_semgrep())
    if args.mode in {'zap', 'all'}:
        results.append(run_zap(args.target))
    if args.mode in {'strix', 'all'}:
        results.append(run_strix(args.target, args.budget))
    sys.exit(max(results, default=0))


if __name__ == '__main__':
    main()
