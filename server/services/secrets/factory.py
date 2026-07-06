"""
Secrets Backend Factory

Selects and constructs a SecretsBackend based on configuration. The backend
is chosen by ``secrets_management.provider`` (default: env), so existing
.env-based deployments are unaffected.
"""

import logging
from typing import Any, Dict, Optional

from .base_secrets import SecretsBackend

logger = logging.getLogger(__name__)


def create_secrets_backend(config: Dict[str, Any]) -> Optional[SecretsBackend]:
    """
    Construct a secrets backend from the merged config.

    Args:
        config: Merged configuration dictionary.

    Returns:
        A SecretsBackend instance, or None when provider is "env" (the
        default) — callers should treat None as "resolve from os.environ
        only", exactly as before this feature existed.

    Raises:
        ValueError: If provider is not a recognized value.
    """
    secrets_management = config.get('secrets_management', {})
    provider = (secrets_management.get('provider') or 'env').lower()

    if provider == 'env':
        return None

    if provider == 'aws':
        from .aws_secrets_manager import AWSSecretsManagerBackend
        aws = secrets_management.get('aws', {})
        return AWSSecretsManagerBackend(
            region_name=aws.get('region') or None,
            endpoint_url=aws.get('endpoint_url') or None,
        )

    if provider == 'azure':
        from .azure_key_vault import AzureKeyVaultBackend
        azure = secrets_management.get('azure', {})
        return AzureKeyVaultBackend(vault_url=azure['vault_url'])

    if provider == 'gcp':
        from .gcp_secret_manager import GCPSecretManagerBackend
        gcp = secrets_management.get('gcp', {})
        return GCPSecretManagerBackend(project=gcp['project'])

    raise ValueError(
        f"Unknown secrets_management.provider '{provider}'. Valid options: env, aws, azure, gcp."
    )
