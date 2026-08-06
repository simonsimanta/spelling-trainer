import os
import tempfile

import pytest


# Establish test isolation before any application module reads DATABASE_URL.
db_fd, db_path = tempfile.mkstemp(prefix="spelling-tests-", suffix=".db")
os.close(db_fd)
os.environ.pop("APP_DATABASE_URL", None)
os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
os.environ["OPENAI_API_KEY"] = ""


@pytest.fixture(autouse=True)
def wait_for_background_spelling_analysis():
    yield
    from app.backend.spelling import attempts

    attempts.wait_for_enrichment()
