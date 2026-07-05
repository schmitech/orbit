"""
Tests for Cloud File Storage Backends (S3 + Azure Blob + GCS)

Runs the same storage contract as test_file_storage.py against the cloud
backends, so behaviour stays identical across filesystem/S3/Azure/GCS.

- S3 is exercised against moto's in-memory AWS mock (skipped if moto/boto3 absent).
- Azure Blob is exercised against an in-memory fake container client that mimics
  the azure-storage-blob surface (skipped if azure-storage-blob absent).
- GCS is exercised against an in-memory fake storage.Client that mimics the
  google-cloud-storage surface (skipped if google-cloud-storage absent).

Note: the empty-directory-cleanup behaviour of the filesystem backend is
intentionally NOT part of the cloud contract — object stores have no directories.
"""

import sys
from pathlib import Path
from unittest import mock

import pytest

# Add server directory to Python path
SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))


# ---------------------------------------------------------------------------
# Azure in-memory fake (mimics the subset of azure-storage-blob we call)
# ---------------------------------------------------------------------------

def _make_fake_azure_service(store: dict):
    """Build a fake BlobServiceClient whose container is backed by `store`."""
    from azure.core.exceptions import ResourceNotFoundError

    class _FakeDownload:
        def __init__(self, data):
            self._data = data

        def readall(self):
            return self._data

    class _FakeProps:
        def __init__(self, size):
            self.size = size

    class _FakeBlobClient:
        def __init__(self, name):
            self._name = name

        def exists(self):
            return self._name in store

        def get_blob_properties(self):
            if self._name not in store:
                raise ResourceNotFoundError(f"missing: {self._name}")
            return _FakeProps(len(store[self._name]))

    class _FakeBlobItem:
        def __init__(self, name):
            self.name = name

    class _FakeContainerClient:
        def get_container_properties(self):
            return {}

        def upload_blob(self, name, data, overwrite=False):
            if name in store and not overwrite:
                raise ValueError(f"blob exists: {name}")
            store[name] = bytes(data)

        def download_blob(self, name):
            if name not in store:
                raise ResourceNotFoundError(f"missing: {name}")
            return _FakeDownload(store[name])

        def delete_blob(self, name):
            if name not in store:
                raise ResourceNotFoundError(f"missing: {name}")
            del store[name]

        def list_blobs(self, name_starts_with=""):
            return [_FakeBlobItem(n) for n in sorted(store) if n.startswith(name_starts_with or "")]

        def get_blob_client(self, name):
            return _FakeBlobClient(name)

    class _FakeServiceClient:
        def get_container_client(self, name):
            return _FakeContainerClient()

    return _FakeServiceClient()


# ---------------------------------------------------------------------------
# GCS in-memory fake (mimics the subset of google-cloud-storage we call)
# ---------------------------------------------------------------------------

def _make_fake_gcs_client(store: dict):
    """Build a fake storage.Client whose bucket is backed by `store`."""
    from google.api_core.exceptions import NotFound

    class _FakeBlob:
        def __init__(self, name):
            self.name = name
            self.size = None

        def upload_from_string(self, data, content_type=None):
            store[self.name] = bytes(data) if isinstance(data, (bytes, bytearray)) else data.encode()

        def download_as_bytes(self):
            if self.name not in store:
                raise NotFound(f"missing: {self.name}")
            return store[self.name]

        def delete(self):
            if self.name not in store:
                raise NotFound(f"missing: {self.name}")
            del store[self.name]

        def exists(self):
            return self.name in store

    class _FakeBucket:
        name = "test-bucket"

        def blob(self, name):
            return _FakeBlob(name)

        def get_blob(self, name):
            if name not in store:
                return None
            blob = _FakeBlob(name)
            blob.size = len(store[name])
            return blob

    class _FakeClient:
        def get_bucket(self, name):
            return _FakeBucket()

        def bucket(self, name):
            return _FakeBucket()

        def list_blobs(self, bucket_or_name, prefix=""):
            return [_FakeBlob(n) for n in sorted(store) if n.startswith(prefix or "")]

    return _FakeClient()


# ---------------------------------------------------------------------------
# Parametrized storage fixture: one contract, all cloud backends
# ---------------------------------------------------------------------------

@pytest.fixture(params=["s3", "azure", "gcs"])
def storage(request):
    if request.param == "s3":
        moto = pytest.importorskip("moto")
        boto3 = pytest.importorskip("boto3")
        with moto.mock_aws():
            boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
            from services.file_storage.s3_storage import S3Storage
            yield S3Storage(bucket="test-bucket", region_name="us-east-1")
    elif request.param == "azure":
        blob_mod = pytest.importorskip("azure.storage.blob")
        store: dict = {}
        fake_service = _make_fake_azure_service(store)
        with mock.patch.object(
            blob_mod.BlobServiceClient, "from_connection_string", return_value=fake_service
        ):
            from services.file_storage.azure_blob_storage import AzureBlobStorage
            yield AzureBlobStorage(
                container="test-container",
                connection_string="UseDevelopmentStorage=true",
            )
    else:
        storage_mod = pytest.importorskip("google.cloud.storage")
        store = {}
        fake_client = _make_fake_gcs_client(store)
        with mock.patch.object(storage_mod, "Client", return_value=fake_client):
            from services.file_storage.gcs_storage import GcsStorage
            yield GcsStorage(bucket="test-bucket")


# ---------------------------------------------------------------------------
# Shared contract (mirrors test_file_storage.py, minus directory cleanup)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_put_and_get_file(storage):
    file_data = b"Hello, World!"
    key = "test_api_key/file_123/test.txt"
    metadata = {"filename": "test.txt", "mime_type": "text/plain", "file_size": len(file_data)}

    result_key = await storage.put_file(file_data, key, metadata)
    assert result_key == key
    assert await storage.get_file(key) == file_data


@pytest.mark.asyncio
async def test_get_file_not_found(storage):
    with pytest.raises(FileNotFoundError):
        await storage.get_file("nonexistent/file.txt")


@pytest.mark.asyncio
async def test_delete_file(storage):
    key = "api_key/file_id/delete_test.txt"
    await storage.put_file(b"Delete me", key, {"filename": "delete_test.txt"})
    assert await storage.file_exists(key)

    assert await storage.delete_file(key) is True
    assert not await storage.file_exists(key)
    # Metadata sidecar is gone too
    with pytest.raises(FileNotFoundError):
        await storage.get_metadata(key)


@pytest.mark.asyncio
async def test_delete_nonexistent_file(storage):
    assert await storage.delete_file("nonexistent/file.txt") is False


@pytest.mark.asyncio
async def test_list_files(storage):
    files = [
        ("api_key_1/file_1/doc1.txt", b"content1"),
        ("api_key_1/file_2/doc2.txt", b"content2"),
        ("api_key_2/file_3/doc3.txt", b"content3"),
    ]
    for key, data in files:
        await storage.put_file(data, key, {"filename": key.split("/")[-1]})

    files_list = await storage.list_files("api_key_1")
    assert len(files_list) == 2
    assert any("doc1.txt" in f for f in files_list)
    assert any("doc2.txt" in f for f in files_list)
    # Sidecars must not leak into listings
    assert not any(f.endswith(".metadata.json") for f in files_list)

    all_files = await storage.list_files("")
    assert len(all_files) >= 3


@pytest.mark.asyncio
async def test_list_files_delimits_prefix(storage):
    files = [
        ("api_key_1/file_1/doc1.txt", b"content1"),
        ("api_key_10/file_2/doc2.txt", b"content2"),
    ]
    for key, data in files:
        await storage.put_file(data, key, {"filename": key.split("/")[-1]})

    assert await storage.list_files("api_key_1") == ["api_key_1/file_1/doc1.txt"]
    assert await storage.list_files("api_key_1/") == ["api_key_1/file_1/doc1.txt"]


@pytest.mark.asyncio
async def test_list_files_empty(storage):
    assert await storage.list_files("nonexistent_api_key") == []


@pytest.mark.asyncio
async def test_get_metadata(storage):
    key = "api_key/file_id/test.txt"
    metadata = {
        "filename": "test.txt",
        "mime_type": "text/plain",
        "file_size": 4,
        "custom_field": "custom_value",
    }
    await storage.put_file(b"Test", key, metadata)

    retrieved = await storage.get_metadata(key)
    assert retrieved["filename"] == "test.txt"
    assert retrieved["custom_field"] == "custom_value"


@pytest.mark.asyncio
async def test_get_metadata_not_found(storage):
    with pytest.raises(FileNotFoundError):
        await storage.get_metadata("nonexistent/file.txt")


@pytest.mark.asyncio
async def test_metadata_with_special_characters(storage):
    key = "api_key/file_id/test.txt"
    metadata = {
        "filename": "test.txt",
        "description": "Test with special chars: äöü 中文 emoji 😀",
        "tags": ["test", "unicode", "special-chars"],
    }
    await storage.put_file(b"content", key, metadata)
    retrieved = await storage.get_metadata(key)

    assert retrieved["description"] == metadata["description"]
    assert retrieved["tags"] == metadata["tags"]


@pytest.mark.asyncio
async def test_file_exists(storage):
    key = "api_key/file_id/test.txt"
    assert not await storage.file_exists(key)
    await storage.put_file(b"content", key, {"filename": "test.txt"})
    assert await storage.file_exists(key)


@pytest.mark.asyncio
async def test_get_file_size(storage):
    file_data = b"This is a test file with some content"
    key = "api_key/file_id/test.txt"
    await storage.put_file(file_data, key, {"filename": "test.txt"})
    assert await storage.get_file_size(key) == len(file_data)


@pytest.mark.asyncio
async def test_get_file_size_not_found(storage):
    with pytest.raises(FileNotFoundError):
        await storage.get_file_size("nonexistent/file.txt")


@pytest.mark.asyncio
async def test_atomic_overwrite(storage):
    key = "api_key/file_id/atomic_test.txt"
    for i in range(5):
        await storage.put_file(f"Content version {i}".encode(), key, {"version": i})

    assert await storage.get_file(key) == b"Content version 4"
    assert (await storage.get_metadata(key))["version"] == 4


@pytest.mark.asyncio
async def test_empty_file(storage):
    key = "api_key/file_id/empty.txt"
    await storage.put_file(b"", key, {"filename": "empty.txt"})
    assert await storage.get_file(key) == b""


@pytest.mark.asyncio
async def test_large_file(storage):
    file_data = b"x" * (1024 * 1024)  # 1 MB
    key = "api_key/file_id/large.bin"
    await storage.put_file(file_data, key, {"filename": "large.bin"})
    assert await storage.get_file(key) == file_data


@pytest.mark.asyncio
async def test_prefix_isolation():
    """Objects stored under a configured prefix are transparent to callers."""
    moto = pytest.importorskip("moto")
    boto3 = pytest.importorskip("boto3")
    with moto.mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="prefixed-bucket")
        from services.file_storage.s3_storage import S3Storage

        storage = S3Storage(bucket="prefixed-bucket", prefix="orbit/uploads", region_name="us-east-1")
        key = "api_key/file_id/doc.txt"
        await storage.put_file(b"data", key, {"filename": "doc.txt"})

        # Caller sees the un-prefixed key back
        assert await storage.list_files("api_key") == [key]
        assert await storage.get_file(key) == b"data"

        # But the object physically lives under the prefix
        raw = client.list_objects_v2(Bucket="prefixed-bucket")["Contents"]
        assert all(obj["Key"].startswith("orbit/uploads/") for obj in raw)


# ---------------------------------------------------------------------------
# Factory selection
# ---------------------------------------------------------------------------

def test_factory_defaults_to_filesystem(tmp_path):
    from services.file_storage import create_storage_backend, FilesystemStorage

    backend = create_storage_backend({"files": {"storage_root": str(tmp_path)}})
    assert isinstance(backend, FilesystemStorage)


def test_factory_rejects_unknown_backend():
    from services.file_storage import create_storage_backend

    with pytest.raises(ValueError, match="Unknown storage_backend"):
        create_storage_backend({"files": {"storage_backend": "dropbox"}})


def test_factory_selects_s3():
    from services.file_storage import create_storage_backend, S3Storage

    moto = pytest.importorskip("moto")
    boto3 = pytest.importorskip("boto3")
    with moto.mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="factory-bucket")
        backend = create_storage_backend({
            "files": {"storage_backend": "s3", "s3": {"bucket": "factory-bucket", "region": "us-east-1"}}
        })
        assert isinstance(backend, S3Storage)


def test_factory_global_backend_overrides_adapter_default():
    from services.file_storage import create_storage_backend, S3Storage

    moto = pytest.importorskip("moto")
    boto3 = pytest.importorskip("boto3")
    with moto.mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="global-bucket")
        backend = create_storage_backend({
            "storage_backend": "filesystem",
            "files": {
                "storage_backend": "s3",
                "s3": {"bucket": "global-bucket", "region": "us-east-1"},
            },
        })
        assert isinstance(backend, S3Storage)


def test_factory_selects_gcs():
    from services.file_storage import create_storage_backend, GcsStorage

    storage_mod = pytest.importorskip("google.cloud.storage")
    fake_client = _make_fake_gcs_client({})
    with mock.patch.object(storage_mod, "Client", return_value=fake_client):
        backend = create_storage_backend({
            "files": {"storage_backend": "gcs", "gcs": {"bucket": "factory-bucket"}}
        })
        assert isinstance(backend, GcsStorage)
