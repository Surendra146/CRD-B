import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


class Settings:
    default_cors_origins = "http://localhost:5173,http://127.0.0.1:5173"

    def __init__(self) -> None:
        self.database_url: str = os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://postgres:Psql%40123@localhost:5432/cm_db",
        )
        self.jwt_secret: str = os.getenv("JWT_SECRET", "supersecretkey")
        self.jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
        self.jwt_expires_minutes: int = int(os.getenv("JWT_EXPIRES_MINUTES", "1440"))
        self.auto_create_tables: bool = os.getenv("AUTO_CREATE_TABLES", "true").lower() in {"1", "true", "yes"}
        self.redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.enable_redis_progress: bool = os.getenv("ENABLE_REDIS_PROGRESS", "true").lower() in {"1", "true", "yes"}
        self.enable_socket_progress: bool = os.getenv("ENABLE_SOCKET_PROGRESS", "true").lower() in {"1", "true", "yes"}
        self.cors_origins: list[str] = [
            origin.strip().rstrip("/")
            for origin in os.getenv("CORS_ORIGINS", self.default_cors_origins).split(",")
            if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
