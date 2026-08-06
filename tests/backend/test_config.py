import os
from pathlib import Path
import subprocess
import sys


def test_app_database_url_overrides_deployment_database_url() -> None:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = "postgresql://deployment.invalid/spelling"
    environment["APP_DATABASE_URL"] = "sqlite:///./data/spelling_trial.db"

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.shared.config import get_settings; print(get_settings().database_url)",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "sqlite:///./data/spelling_trial.db"
