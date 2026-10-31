"""Use only the container created for this audit. Do not print connection secrets."""
import json, os, subprocess, sys
from pathlib import Path
from urllib.parse import quote
root = Path(__file__).resolve().parents[3]
os.chdir(root)
sys.path.insert(0, str(root))
info = json.loads(subprocess.check_output(["docker", "inspect", "codex-campaign-audit-db"]))[0]
assert info["Config"]["Labels"].get("codex.audit") == "campaign-platform"
assert info["NetworkSettings"]["Ports"]["5432/tcp"] == [{"HostIp": "127.0.0.1", "HostPort": "55432"}]
password = next(v.split("=", 1)[1] for v in info["Config"]["Env"] if v.startswith("POSTGRES_PASSWORD="))
os.environ["CAMPAIGN_AUDIT_DATABASE_URL"] = f"postgresql+asyncpg://postgres:{quote(password, safe='')}@127.0.0.1:55432/postgres"
import pytest
raise SystemExit(pytest.main(["server/tests/test_campaign_execution_safety.py", "-q", "--disable-warnings", "--tb=short", "-x"]))
