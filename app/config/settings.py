import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


class Settings:
    default_cors_origins = "http://localhost:5173,http://127.0.0.1:5173"

    def __init__(self) -> None:
        raw_db_url = os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://hanuram_runtime@localhost:5432/hanuram_dev",
        )
        # Normalize Render / cloud PostgreSQL URLs for psycopg v3 dialect
        if raw_db_url.startswith("postgres://"):
            raw_db_url = raw_db_url.replace("postgres://", "postgresql+psycopg://", 1)
        elif raw_db_url.startswith("postgresql://") and not raw_db_url.startswith("postgresql+"):
            raw_db_url = raw_db_url.replace("postgresql://", "postgresql+psycopg://", 1)
        self.database_url: str = raw_db_url

        self.environment: str = os.getenv("ENVIRONMENT", "production")
        self.jwt_secret: str = os.getenv("JWT_SECRET", "supersecretkey")
        if self.environment.lower() == "production":
            if not os.getenv("DATABASE_URL"):
                raise ValueError("DATABASE_URL is required in production")
            if self.jwt_secret == "supersecretkey" or len(self.jwt_secret) < 32:
                raise ValueError("Production JWT_SECRET must contain at least 32 characters")
        # Meta credentials and routing are server-owned; never expose to React.
        self.whatsapp_provider: str = os.getenv("WHATSAPP_PROVIDER", "meta_cloud")
        # Only explicit true enables delivery; unset/invalid values fail closed.
        self.whatsapp_sending_enabled: bool = os.getenv("WHATSAPP_SENDING_ENABLED", "false").strip().lower() == "true"
        self.whatsapp_graph_version: str = os.getenv("WHATSAPP_GRAPH_VERSION", "v23.0")
        self.meta_app_secret: str = os.getenv("META_APP_SECRET", "")
        self.whatsapp_verify_token: str = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
        self.meta_app_id: str = os.getenv("META_APP_ID", "")
        self.whatsapp_signup_config_id: str = os.getenv("WHATSAPP_SIGNUP_CONFIG_ID", "")
        self.whatsapp_token_encryption_key: str = os.getenv("WHATSAPP_TOKEN_ENCRYPTION_KEY", "")

        self.control_database_url = os.getenv("CONTROL_DATABASE_URL", self.database_url).replace("postgres://", "postgresql+psycopg://", 1)
        if self.control_database_url.startswith("postgresql://"):
            self.control_database_url = self.control_database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        self.enforce_whatsapp_consent = os.getenv("ENFORCE_WHATSAPP_CONSENT", "true").lower() == "true"
        self.enforce_subscription = os.getenv("ENFORCE_SUBSCRIPTION", "true").lower() == "true"
        self.require_rls = os.getenv("REQUIRE_RLS", "true" if self.environment.lower() == "production" else "false").lower() == "true"
        # WhatsApp template media storage configuration
        self.media_storage_backend: str = os.getenv(
            "MEDIA_STORAGE_BACKEND", "local"
        ).strip().lower()

        if self.media_storage_backend not in {"local", "r2"}:
            raise ValueError(
                "MEDIA_STORAGE_BACKEND must be 'local' or 'r2'"
            )

        self.whatsapp_template_media_root: str = os.getenv(
            "WHATSAPP_TEMPLATE_MEDIA_ROOT", ".template-media"
        )

        # Cloudflare R2 configuration
        self.r2_endpoint_url: str = os.getenv("R2_ENDPOINT_URL", "")
        self.r2_bucket_name: str = os.getenv("R2_BUCKET_NAME", "")
        self.r2_access_key_id: str = os.getenv("R2_ACCESS_KEY_ID", "")
        self.r2_secret_access_key: str = os.getenv("R2_SECRET_ACCESS_KEY", "")
        if self.media_storage_backend == "r2":
            if not all([
                self.r2_endpoint_url,
                self.r2_bucket_name,
                self.r2_access_key_id,
                self.r2_secret_access_key,
            ]):
                raise ValueError(
                    "Cloudflare R2 storage configuration is incomplete"
                )
        self.database_authorization_keys = {
            purpose: os.getenv("DATABASE_AUTH_" + purpose.upper() + "_KEY", "")
            for purpose in ("identity", "staff", "jobs")
        }
        self.max_broadcast_recipients = int(os.getenv("MAX_BROADCAST_RECIPIENTS", "20"))
        self.campaign_transport = os.getenv("CAMPAIGN_TRANSPORT", "celery")
        self.enable_distributed_limits = os.getenv("ENABLE_DISTRIBUTED_LIMITS", "false").lower() == "true"
        self.tenant_requests_per_minute = int(os.getenv("TENANT_REQUESTS_PER_MINUTE", "300"))

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
