
from urllib.parse import urlsplit

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, BotoCoreError
from app.services.media_storage.keys import MAX_MEDIA_BYTES, validate_key


class StorageUnavailable(OSError):
    """Safe storage failure; underlying provider details are not public."""


class R2MediaStorage:
    def __init__(
        self,
        endpoint_url: str,
        bucket_name: str,
        access_key_id: str,
        secret_access_key: str,
        client=None,
    ):
        endpoint = urlsplit(endpoint_url)
        if (endpoint.scheme != 'https' or not endpoint.hostname or endpoint.username
                or endpoint.password or endpoint.query or endpoint.fragment
                or endpoint.path not in {'', '/'}):
            raise ValueError("R2 endpoint must use HTTPS")
        if not bucket_name:
            raise ValueError("R2 bucket name is required")
        if not access_key_id or not secret_access_key:
            raise ValueError("R2 credentials are required")

        self.bucket = bucket_name
        self.client = client or boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name="auto",
            config=Config(
                signature_version="s3v4",
                connect_timeout=5,
                read_timeout=30,
                retries={"mode": "standard", "total_max_attempts": 3},
            ),
        )

    def _key(self, key: str) -> str:
        return validate_key(key)

    def _call(self, operation, **kwargs):
        try:
            return getattr(self.client, operation)(Bucket=self.bucket, **kwargs)
        except ClientError as error:
            code = error.response.get('Error', {}).get('Code')
            if code in {'NoSuchKey', 'NotFound', '404'}:
                raise FileNotFoundError('Stored media not found') from None
            if code in {'PreconditionFailed', '412'}:
                raise FileExistsError('Stored media already exists') from None
            raise StorageUnavailable('Media storage unavailable') from None
        except (BotoCoreError, OSError):
            raise StorageUnavailable('Media storage unavailable') from None

    def put(self, key: str, data: bytes) -> None:
        if len(data) > MAX_MEDIA_BYTES:
            raise ValueError("Media exceeds storage limit")

        self._call('put_object',
            Key=self._key(key),
            Body=data,
            IfNoneMatch='*',
        )

    def get(self, key: str) -> bytes:
        response = self._call('get_object',
            Key=self._key(key),
        )
        body = response["Body"]
        try:
            if response.get('ContentLength', 0) > MAX_MEDIA_BYTES:
                raise ValueError("Stored media exceeds size limit")
            data = body.read(MAX_MEDIA_BYTES + 1)
        except (BotoCoreError, OSError):
            raise StorageUnavailable('Media storage unavailable') from None
        finally:
            body.close()

        if len(data) > MAX_MEDIA_BYTES:
            raise ValueError("Stored media exceeds size limit")

        return data

    def delete(self, key: str) -> None:
        self._call('delete_object',
            Key=self._key(key),
        )
