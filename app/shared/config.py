from functools import lru_cache
import os

from dotenv import load_dotenv


load_dotenv()


class Settings:
    app_env: str = os.getenv("APP_ENV", "local")
    api_host: str = os.getenv("API_HOST", "127.0.0.1")
    api_port: int = int(os.getenv("API_PORT", "8000"))
    vite_port: int = int(os.getenv("VITE_PORT", "5173"))
    database_url: str = os.getenv("APP_DATABASE_URL") or os.getenv(
        "DATABASE_URL", "sqlite:///./data/spelling.db"
    )
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
