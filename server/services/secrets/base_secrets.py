"""
Base Secrets Backend Interface

Abstract base class for secrets-management backends. Supports resolving
${VAR_NAME} placeholders used throughout config/*.yaml from a cloud secrets
manager (AWS Secrets Manager, Azure Key Vault, GCP Secret Manager) instead of
(or in addition to) the local .env / process environment.
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)


class SecretsBackend(ABC):
    """
    Abstract base class for secrets backends.

    Implementations look up a secret by the exact same name used in the
    ${VAR_NAME} placeholder (e.g. "DATASOURCE_POSTGRES_PASSWORD") so that no
    existing config/*.yaml file needs to change to adopt a cloud backend.
    """

    @abstractmethod
    def get_secret(self, name: str) -> Optional[str]:
        """
        Look up a secret value by name.

        Args:
            name: The placeholder name, e.g. "DATASOURCE_POSTGRES_PASSWORD".

        Returns:
            The secret value, or None if no secret with that name exists.
            Implementations must not raise for a not-found secret.

        Raises:
            Exception: Implementations may raise for auth/network failures.
                Callers are expected to catch, log, and fall back to
                os.environ / the config default.
        """
        pass
