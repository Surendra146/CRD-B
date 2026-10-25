
import io
from unittest.mock import Mock

import pytest

from app.services.media_storage.r2 import R2MediaStorage


KEY = "1/2/3/" + "a" * 32


@pytest.fixture
def storage():
    client = Mock()
    client.get_object.return_value = {
        "Body": io.BytesIO(b"sample-media")
    }

    return R2MediaStorage(
        endpoint_url="https://example.r2.cloudflarestorage.com",
        bucket_name="test-private-media",
        access_key_id="test",
        secret_access_key="test",
        client=client,
    )


def test_put(storage):
    storage.put(KEY, b"sample-media")

    storage.client.put_object.assert_called_once_with(
        Bucket="test-private-media",
        Key=KEY,
        Body=b"sample-media",
        IfNoneMatch='*',
    )


def test_get(storage):
    assert storage.get(KEY) == b"sample-media"


def test_delete(storage):
    storage.delete(KEY)

    storage.client.delete_object.assert_called_once_with(
        Bucket="test-private-media",
        Key=KEY,
    )


@pytest.mark.parametrize(
    "key",
    [
        "../outside",
        "/absolute",
        "1/2/3/../../secret",
        "1/2/3/invalid",
    ],
)
def test_invalid_keys(storage, key):
    with pytest.raises(ValueError):
        storage.put(key, b"data")
