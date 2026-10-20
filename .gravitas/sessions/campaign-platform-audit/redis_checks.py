import json, os, subprocess, sys
from pathlib import Path
root = Path(__file__).resolve().parents[3]
os.chdir(root); sys.path.insert(0, str(root))
info=json.loads(subprocess.check_output(["docker","inspect","codex-campaign-audit-redis"]))[0]
assert info["Config"]["Labels"].get("codex.audit") == "campaign-platform"
assert info["NetworkSettings"]["Ports"]["6379/tcp"] == [{"HostIp":"127.0.0.1","HostPort":"56379"}]
os.environ["CAMPAIGN_AUDIT_REDIS_URL"] = "redis://127.0.0.1:56379/0"
import pytest
raise SystemExit(pytest.main(["server/tests/test_primary_media_auth.py","-q","--disable-warnings","--tb=short","-x"]))
