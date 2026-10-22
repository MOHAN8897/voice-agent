"""Local UI smoke-test API with isolated data and no provider credentials.

Run from the repository root: python -m scripts.pstn_smoke_server
This is a test fixture, not the production server launcher.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from server.config.env import Settings, get_settings


def main() -> None:
    Settings.model_config["env_file"] = None
    os.environ.update({
        "OPENAI_API_KEY": "unit-test-placeholder",
        "SARVAM_API_KEY": "unit-test-placeholder",
        "DATABASE_URL": "",
        "REDIS_URL": "",
        "APP_CONSOLE_USERNAME": "e2e",
        "APP_CONSOLE_PASSWORD": "e2e-test",
        "DEV_PORTAL_USERNAME": "dev",
        "DEV_PORTAL_PASSWORD": "devpass",
        "APP_ENVIRONMENT": "development",
    })
    data_root = Path(__file__).resolve().parents[1] / "data"
    with tempfile.TemporaryDirectory(prefix="pstn-ui-", dir=data_root) as data_dir:
        os.environ["DATA_DIR"] = data_dir
        get_settings.cache_clear()
        import uvicorn

        uvicorn.run("server.app:app", host="127.0.0.1", port=8100)


if __name__ == "__main__":
    main()
