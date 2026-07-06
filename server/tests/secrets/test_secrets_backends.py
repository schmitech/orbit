"""
Tests for Cloud Secrets Backends (AWS Secrets Manager + Azure Key Vault + GCP
Secret Manager)

- AWS is exercised against moto's in-memory AWS mock (skipped if moto/boto3 absent).
- Azure is exercised against an in-memory fake SecretClient that mimics the
  azure-keyvault-secrets surface (skipped if azure-keyvault-secrets absent).
- GCP is exercised against an in-memory fake SecretManagerServiceClient that
  mimics the google-cloud-secret-manager surface (skipped if absent).
"""

import sys
from pathlib import Path
from unittest import mock

import pytest

SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))


# ---------------------------------------------------------------------------
# Azure in-memory fake (mimics the subset of azure-keyvault-secrets we call)
# ---------------------------------------------------------------------------

def _make_fake_keyvault_client(store: dict):
    from azure.core.exceptions import ResourceNotFoundError

    class _FakeSecret:
        def __init__(self, value):
            self.value = value

    class _FakeSecretProperties:
        def __init__(self, name):
            self.name = name

    class _FakeSecretClient:
        def list_properties_of_secrets(self):
            return [_FakeSecretProperties(n) for n in sorted(store)]

        def get_secret(self, name):
            if name not in store:
                raise ResourceNotFoundError(f"missing: {name}")
            return _FakeSecret(store[name])

    return _FakeSecretClient()


# ---------------------------------------------------------------------------
# GCP in-memory fake (mimics the subset of google-cloud-secret-manager we call)
# ---------------------------------------------------------------------------

def _make_fake_secretmanager_client(store: dict):
    from google.api_core.exceptions import NotFound

    class _FakePayload:
        def __init__(self, data: bytes):
            self.data = data

    class _FakeResponse:
        def __init__(self, data: bytes):
            self.payload = _FakePayload(data)

    class _FakeSecret:
        def __init__(self, name):
            self.name = name

    class _FakeSecretManagerServiceClient:
        def list_secrets(self, request):
            return [_FakeSecret(n) for n in sorted(store)]

        def access_secret_version(self, request):
            name = request["name"]
            if name not in store:
                raise NotFound(f"missing: {name}")
            return _FakeResponse(store[name].encode("utf-8"))

    return _FakeSecretManagerServiceClient()


# ---------------------------------------------------------------------------
# Parametrized backend fixture: one contract, all cloud backends
# ---------------------------------------------------------------------------
# Each case yields (backend, existing_name, expected_value, missing_name, call_counter)

@pytest.fixture(params=["aws", "azure", "gcp"])
def secrets_case(request):
    if request.param == "aws":
        moto = pytest.importorskip("moto")
        boto3 = pytest.importorskip("boto3")
        with moto.mock_aws():
            client = boto3.client("secretsmanager", region_name="us-east-1")
            client.create_secret(Name="EXISTING_SECRET", SecretString="secret-value")

            from services.secrets.aws_secrets_manager import AWSSecretsManagerBackend
            backend = AWSSecretsManagerBackend(region_name="us-east-1")
            counter = mock.Mock(wraps=backend._client.get_secret_value)
            backend._client.get_secret_value = counter
            yield backend, "EXISTING_SECRET", "secret-value", "MISSING_SECRET", counter

    elif request.param == "azure":
        kv_mod = pytest.importorskip("azure.keyvault.secrets")
        pytest.importorskip("azure.identity")
        store = {"EXISTING-SECRET": "secret-value"}
        fake_client = _make_fake_keyvault_client(store)
        with mock.patch.object(kv_mod, "SecretClient", return_value=fake_client):
            from services.secrets.azure_key_vault import AzureKeyVaultBackend
            backend = AzureKeyVaultBackend(vault_url="https://fake.vault.azure.net/")
            counter = mock.Mock(wraps=fake_client.get_secret)
            fake_client.get_secret = counter
            # Placeholder name uses underscores; backend translates to hyphens.
            yield backend, "EXISTING_SECRET", "secret-value", "MISSING_SECRET", counter

    else:
        sm_mod = pytest.importorskip("google.cloud.secretmanager")
        store = {"projects/test-project/secrets/EXISTING_SECRET/versions/latest": "secret-value"}
        fake_client = _make_fake_secretmanager_client(store)
        with mock.patch.object(sm_mod, "SecretManagerServiceClient", return_value=fake_client):
            from services.secrets.gcp_secret_manager import GCPSecretManagerBackend
            backend = GCPSecretManagerBackend(project="test-project")
            counter = mock.Mock(wraps=fake_client.access_secret_version)
            fake_client.access_secret_version = counter
            yield backend, "EXISTING_SECRET", "secret-value", "MISSING_SECRET", counter


# ---------------------------------------------------------------------------
# Shared contract
# ---------------------------------------------------------------------------

def test_get_existing_secret(secrets_case):
    backend, existing_name, expected_value, _missing_name, _counter = secrets_case
    assert backend.get_secret(existing_name) == expected_value


def test_get_missing_secret_returns_none(secrets_case):
    backend, _existing_name, _expected_value, missing_name, _counter = secrets_case
    assert backend.get_secret(missing_name) is None


def test_repeated_lookup_is_cached(secrets_case):
    backend, existing_name, expected_value, _missing_name, counter = secrets_case
    assert backend.get_secret(existing_name) == expected_value
    assert backend.get_secret(existing_name) == expected_value
    assert counter.call_count == 1


def test_repeated_miss_is_cached(secrets_case):
    backend, _existing_name, _expected_value, missing_name, counter = secrets_case
    assert backend.get_secret(missing_name) is None
    assert backend.get_secret(missing_name) is None
    assert counter.call_count == 1


# ---------------------------------------------------------------------------
# Azure-specific: underscore -> hyphen translation
# ---------------------------------------------------------------------------

def test_azure_translates_underscores_to_hyphens():
    kv_mod = pytest.importorskip("azure.keyvault.secrets")
    pytest.importorskip("azure.identity")
    store = {"DATASOURCE-POSTGRES-PASSWORD": "hunter2"}
    fake_client = _make_fake_keyvault_client(store)
    with mock.patch.object(kv_mod, "SecretClient", return_value=fake_client):
        from services.secrets.azure_key_vault import AzureKeyVaultBackend
        backend = AzureKeyVaultBackend(vault_url="https://fake.vault.azure.net/")
        assert backend.get_secret("DATASOURCE_POSTGRES_PASSWORD") == "hunter2"


# ---------------------------------------------------------------------------
# Factory tests
# ---------------------------------------------------------------------------

def test_factory_defaults_to_env_returns_none():
    from services.secrets.factory import create_secrets_backend
    assert create_secrets_backend({}) is None
    assert create_secrets_backend({'secrets_management': {'provider': 'env'}}) is None


def test_factory_rejects_unknown_provider():
    from services.secrets.factory import create_secrets_backend
    with pytest.raises(ValueError):
        create_secrets_backend({'secrets_management': {'provider': 'vault'}})


def test_factory_selects_aws():
    import services.secrets.aws_secrets_manager as aws_mod
    from services.secrets.factory import create_secrets_backend
    sentinel = object()
    with mock.patch.object(aws_mod, "AWSSecretsManagerBackend", return_value=sentinel) as ctor:
        result = create_secrets_backend({
            'secrets_management': {'provider': 'aws', 'aws': {'region': 'us-west-2'}}
        })
    assert result is sentinel
    ctor.assert_called_once_with(region_name='us-west-2', endpoint_url=None)


def test_factory_selects_azure():
    import services.secrets.azure_key_vault as azure_mod
    from services.secrets.factory import create_secrets_backend
    sentinel = object()
    with mock.patch.object(azure_mod, "AzureKeyVaultBackend", return_value=sentinel) as ctor:
        result = create_secrets_backend({
            'secrets_management': {
                'provider': 'azure',
                'azure': {'vault_url': 'https://fake.vault.azure.net/'},
            }
        })
    assert result is sentinel
    ctor.assert_called_once_with(vault_url='https://fake.vault.azure.net/')


def test_factory_selects_gcp():
    import services.secrets.gcp_secret_manager as gcp_mod
    from services.secrets.factory import create_secrets_backend
    sentinel = object()
    with mock.patch.object(gcp_mod, "GCPSecretManagerBackend", return_value=sentinel) as ctor:
        result = create_secrets_backend({
            'secrets_management': {'provider': 'gcp', 'gcp': {'project': 'test-project'}}
        })
    assert result is sentinel
    ctor.assert_called_once_with(project='test-project')
