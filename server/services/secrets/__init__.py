"""
Secrets Management Service

Provides pluggable secrets backends for resolving ${VAR_NAME} placeholders
used throughout config/*.yaml. Supports the local .env / process environment
(default), AWS Secrets Manager, Azure Key Vault, and GCP Secret Manager.
Backend selection is config-driven via ``create_secrets_backend``.

Cloud backend classes lazy-import their SDKs, so importing this package does
not require boto3, azure-keyvault-secrets, or google-cloud-secret-manager
unless a cloud backend is instantiated.
"""

from .base_secrets import SecretsBackend
from .aws_secrets_manager import AWSSecretsManagerBackend
from .azure_key_vault import AzureKeyVaultBackend
from .gcp_secret_manager import GCPSecretManagerBackend
from .factory import create_secrets_backend

__all__ = [
    'SecretsBackend',
    'AWSSecretsManagerBackend',
    'AzureKeyVaultBackend',
    'GCPSecretManagerBackend',
    'create_secrets_backend',
]
