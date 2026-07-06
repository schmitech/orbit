"""
GCP Secret Manager Backend

Resolves ${VAR_NAME} placeholders as GCP Secret Manager secrets of the same
name (latest version).
"""

import logging
from typing import Dict, Optional

from .base_secrets import SecretsBackend

logger = logging.getLogger(__name__)


class GCPSecretManagerBackend(SecretsBackend):
    """GCP Secret Manager-backed secrets resolution."""

    def __init__(self, project: str):
        """
        Initialize the GCP Secret Manager backend.

        Args:
            project: GCP project ID that owns the secrets.
        """
        try:
            from google.cloud import secretmanager
        except ImportError as e:
            raise ImportError(
                "The GCP Secret Manager backend requires google-cloud-secret-manager. "
                "Install it with './install/setup.sh --profile secrets-management' or "
                "'pip install google-cloud-secret-manager'."
            ) from e

        if not project:
            raise ValueError("secrets_management.gcp.project is required for the gcp provider.")

        self._project = project
        self._client = secretmanager.SecretManagerServiceClient()
        self._cache: Dict[str, Optional[str]] = {}

        # Fail loudly if Secret Manager is not reachable / credentials are bad.
        try:
            next(iter(self._client.list_secrets(request={"parent": f"projects/{project}", "page_size": 1})), None)
        except Exception as e:
            raise RuntimeError(
                f"Cannot reach GCP Secret Manager for project '{project}': {e}. "
                "Check credentials and project ID before starting the server."
            ) from e

        logger.info(f"Initialized GCPSecretManagerBackend (project={project})")

    def get_secret(self, name: str) -> Optional[str]:
        if name in self._cache:
            return self._cache[name]

        from google.api_core.exceptions import NotFound

        secret_path = f"projects/{self._project}/secrets/{name}/versions/latest"
        try:
            response = self._client.access_secret_version(request={"name": secret_path})
            value = response.payload.data.decode("UTF-8")
        except NotFound:
            value = None

        self._cache[name] = value
        return value
