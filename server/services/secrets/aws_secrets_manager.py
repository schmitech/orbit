"""
AWS Secrets Manager Backend

Resolves ${VAR_NAME} placeholders as AWS Secrets Manager secrets of the same
name.
"""

import logging
from typing import Dict, Optional

from .base_secrets import SecretsBackend

logger = logging.getLogger(__name__)


class AWSSecretsManagerBackend(SecretsBackend):
    """AWS Secrets Manager-backed secrets resolution."""

    def __init__(self, region_name: Optional[str] = None, endpoint_url: Optional[str] = None):
        """
        Initialize the AWS Secrets Manager backend.

        Args:
            region_name: AWS region. Omit to use the boto3 default (env /
                instance role / profile / SSO).
            endpoint_url: Custom endpoint, e.g. for LocalStack in testing.
        """
        try:
            import boto3
        except ImportError as e:
            raise ImportError(
                "The AWS Secrets Manager backend requires boto3. Install it with "
                "'./install/setup.sh --profile secrets-management' or 'pip install boto3'."
            ) from e

        self._client = boto3.client(
            "secretsmanager",
            region_name=region_name or None,
            endpoint_url=endpoint_url or None,
        )
        self._cache: Dict[str, Optional[str]] = {}

        # Fail loudly if AWS Secrets Manager is not reachable / credentials are bad.
        try:
            self._client.list_secrets(MaxResults=1)
        except Exception as e:
            raise RuntimeError(
                f"Cannot reach AWS Secrets Manager: {e}. "
                "Check credentials, region, and network access before starting the server."
            ) from e

        logger.info(f"Initialized AWSSecretsManagerBackend (region={region_name or 'default'})")

    def get_secret(self, name: str) -> Optional[str]:
        if name in self._cache:
            return self._cache[name]

        from botocore.exceptions import ClientError

        try:
            response = self._client.get_secret_value(SecretId=name)
            value = response.get("SecretString")
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "ResourceNotFoundException":
                value = None
            else:
                raise

        self._cache[name] = value
        return value
