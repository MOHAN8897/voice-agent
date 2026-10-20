"""Isolated API target: no local secrets, provider warmup, jobs or production DB."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
os.environ["DATA_DIR"] = str(ROOT / ".gravitas" / "security-reports" / "zap-data")
os.environ["DATABASE_URL"] = ""
os.environ["REDIS_URL"] = ""
os.environ["SAAS_AUTH_ENABLED"] = "true"
os.environ["APP_ENVIRONMENT"] = "development"
for name in ("OPENAI_API_KEY", "GEMINI_API_KEY", "SARVAM_API_KEY", "NANGO_SECRET_KEY", "NANGO_API_KEY", "VOBIZ_AUTH_TOKEN", "TELNYX_API_KEY"):
    os.environ[name] = ""
os.environ["OPENAI_API_KEY"] = "isolated-scanner-placeholder"
os.environ["SARVAM_API_KEY"] = "isolated-scanner-placeholder"
from server.config.env import Settings, get_settings
Settings.model_config["env_file"] = None
get_settings.cache_clear()
from server.app import app
import uvicorn

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8011, lifespan="off", access_log=False)
