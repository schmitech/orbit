"""
AWS Athena Datasource Implementation
"""

import logging
from ...base.base_datasource import BaseDatasource

logger = logging.getLogger(__name__)


class AthenaDatasource(BaseDatasource):
    """AWS Athena datasource implementation."""

    @property
    def datasource_name(self) -> str:
        """Return the name of this datasource for config lookup."""
        return 'athena'

    async def initialize(self) -> None:
        """Initialize the Athena connection."""
        athena_config = self.config.get('datasources', {}).get('athena', {})

        try:
            from pyathena import connect
            from pyathena.cursor import DictCursor
        except ImportError:
            logger.error("PyAthena not available. Install with: pip install pyathena")
            raise

        s3_staging_dir = athena_config.get('s3_staging_dir')
        region_name = athena_config.get('region_name')
        schema_name = athena_config.get('schema_name')
        catalog_name = athena_config.get('catalog_name')
        work_group = athena_config.get('work_group')
        aws_access_key_id = athena_config.get('aws_access_key_id')
        aws_secret_access_key = athena_config.get('aws_secret_access_key')
        aws_session_token = athena_config.get('aws_session_token')

        if not s3_staging_dir:
            raise ValueError("Athena datasource requires 's3_staging_dir' in datasources.athena config")
        if not region_name:
            raise ValueError("Athena datasource requires 'region_name' in datasources.athena config")

        # Preflight auth validation to fail fast with actionable guidance
        self._preflight_validate_auth(
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            aws_session_token=aws_session_token,
            region_name=region_name,
            s3_staging_dir=s3_staging_dir,
        )

        try:
            logger.info(
                "Initializing Athena connection (region=%s, schema=%s, work_group=%s)",
                region_name,
                schema_name or "default",
                work_group or "primary",
            )

            connect_kwargs = {
                "s3_staging_dir": s3_staging_dir,
                "region_name": region_name,
                "schema_name": schema_name,
                "catalog_name": catalog_name,
                "work_group": work_group,
                "cursor_class": DictCursor,
            }

            if aws_access_key_id and aws_secret_access_key:
                connect_kwargs["aws_access_key_id"] = aws_access_key_id
                connect_kwargs["aws_secret_access_key"] = aws_secret_access_key

            if aws_session_token:
                connect_kwargs["aws_session_token"] = aws_session_token

            # Remove unset optional parameters.
            connect_kwargs = {k: v for k, v in connect_kwargs.items() if v is not None}

            self._client = connect(**connect_kwargs)

            # Test the connection
            cursor = self._client.cursor()
            cursor.execute("SELECT 1 AS test")
            cursor.fetchone()
            cursor.close()

            self._initialized = True
            logger.info("Athena connection established successfully")

        except Exception as e:
            logger.error(f"Failed to connect to Athena: {str(e)}")
            raise

    async def health_check(self) -> bool:
        """Perform a health check on the Athena connection."""
        if not self._initialized or not self._client:
            return False

        try:
            cursor = self._client.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            return True
        except Exception as e:
            logger.error(f"Athena health check failed: {e}")
            return False

    async def close(self) -> None:
        """Close the Athena connection."""
        if self._client:
            try:
                self._client.close()
            except Exception as e:
                logger.warning(f"Error closing Athena connection: {e}")
            self._client = None
            self._initialized = False
            logger.info("Athena connection closed")

    def _preflight_validate_auth(
        self,
        aws_access_key_id,
        aws_secret_access_key,
        aws_session_token,
        region_name,
        s3_staging_dir,
    ) -> None:
        """
        Validate auth inputs before attempting Athena API calls.
        Raises ValueError with clear setup guidance on invalid combinations.
        """
        errors = []
        warnings = []

        key = (aws_access_key_id or "").strip()
        secret = (aws_secret_access_key or "").strip()
        token = (aws_session_token or "").strip()

        # Basic required runtime settings
        if not region_name:
            errors.append("Missing DATASOURCE_ATHENA_REGION")
        if not s3_staging_dir:
            errors.append("Missing DATASOURCE_ATHENA_S3_STAGING_DIR")

        # Credential pair consistency checks
        if (key and not secret) or (secret and not key):
            errors.append(
                "DATASOURCE_ATHENA_ACCESS_KEY_ID and DATASOURCE_ATHENA_SECRET_ACCESS_KEY must be set together"
            )

        # Temporary credential checks
        if key.startswith("ASIA") and not token:
            errors.append(
                "Temporary AWS credentials detected (ASIA...) but DATASOURCE_ATHENA_SESSION_TOKEN is missing"
            )

        # Common placeholder/misconfigured values
        placeholder_values = {"your-key", "changeme", "example", "test", "token"}
        if key.lower() in placeholder_values or secret.lower() in placeholder_values:
            errors.append("Athena credentials appear to be placeholder values, not real AWS credentials")

        # Guidance when explicit creds are omitted (default chain still allowed)
        if not key and not secret:
            warnings.append(
                "No explicit Athena credentials configured; relying on AWS default credential chain "
                "(AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY, profile, role, or instance metadata)"
            )

        for msg in warnings:
            logger.warning(f"Athena preflight: {msg}")

        if errors:
            raise ValueError(
                "Athena credential preflight failed: "
                + "; ".join(errors)
                + ". Set DATASOURCE_ATHENA_ACCESS_KEY_ID / DATASOURCE_ATHENA_SECRET_ACCESS_KEY "
                + "(and DATASOURCE_ATHENA_SESSION_TOKEN for temporary creds), "
                + "or use valid AWS default-chain credentials."
            )
