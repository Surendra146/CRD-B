
from app.config.settings import get_settings
from app.services.media_storage.local import LocalMediaStorage
from app.services.media_storage.r2 import R2MediaStorage


def get_media_storage():
    settings = get_settings()

    if settings.media_storage_backend == "local":
        return LocalMediaStorage(
            settings.whatsapp_template_media_root
        )

    if settings.media_storage_backend == "r2":
        return R2MediaStorage(
            endpoint_url=settings.r2_endpoint_url,
            bucket_name=settings.r2_bucket_name,
            access_key_id=settings.r2_access_key_id,
            secret_access_key=settings.r2_secret_access_key,
        )

    raise ValueError("Unsupported media storage backend")
