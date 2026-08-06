import os
import tempfile


# Establish test isolation before any application module reads DATABASE_URL.
db_fd, db_path = tempfile.mkstemp(prefix="spelling-tests-", suffix=".db")
os.close(db_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
os.environ["OPENAI_API_KEY"] = ""
