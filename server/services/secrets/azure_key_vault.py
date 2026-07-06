"""
Azure Key Vault Backend

Resolves ${VAR_NAME} placeholders as Azure Key Vault secrets. Key Vault secret
names may only contain alphanumeric characters and hyphens, so underscores in
the placeholder name are translated to hyphens for the lookup.
"""

import logging
from typing import Dict, Optional

from .base_secrets import SecretsBackend

logger = logging.getLogger(__name__)


class AzureKeyVaultBackend(SecretsBackend):
    """Azure Key Vault-backed secrets resolution."""

    def __init__(self, vault_url: str):
        """
        Initialize the Azure Key Vault backend.

        Args:
            vault_url: Vault URL, e.g. "https://your-vault.vault.azure.net/".
        """
        try:
            from azure.keyvault.secrets import SecretClient
            from azure.identity import DefaultAzureCredential
        except ImportError as e:
            raise ImportError(
                "The Azure Key Vault backend requires azure-keyvault-secrets and "
                "azure-identity. Install them with "
                "'./install/setup.sh --profile secrets-management' or "
                "'pip install azure-keyvault-secrets azure-identity'."
            ) from e

        self._client = SecretClient(vault_url=vault_url, credential=DefaultAzureCredential())
        self._cache: Dict[str, Optional[str]] = {}

        # Fail loudly if the vault is not reachable / credentials are bad.
        try:
            next(iter(self._client.list_properties_of_secrets()), None)
        except Exception as e:
            raise RuntimeError(
                f"Cannot reach Azure Key Vault '{vault_url}': {e}. "
                "Check credentials, vault URL, and access policy before starting the server."
            ) from e

        logger.info(f"Initialized AzureKeyVaultBackend (vault_url={vault_url})")

    @staticmethod
    def _vault_name(name: str) -> str:
        """Translate a ${VAR_NAME} placeholder into a valid Key Vault secret name."""
        return name.replace("_", "-")

    def get_secret(self, name: str) -> Optional[str]:
        if name in self._cache:
            return self._cache[name]

        from azure.core.exceptions import ResourceNotFoundError

        try:
            secret = self._client.get_secret(self._vault_name(name))
            value = secret.value
        except ResourceNotFoundError:
            value = None

        self._cache[name] = value
        return value
