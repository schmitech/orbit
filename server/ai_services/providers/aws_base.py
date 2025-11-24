"""
AWS-specific base class for all AWS Bedrock services.

This module provides a unified base class for all AWS Bedrock-based services,
consolidating common functionality like credential management, client initialization,
and error handling for AWS services.
"""

from typing import Dict, Any, Optional
import logging
import boto3
from botocore.exceptions import ClientError

from ..base import ProviderAIService, ServiceType
from ..connection import RetryHandler



logger = logging.getLogger(__name__)
class AWSBaseService(ProviderAIService):
    """
    Base class for all AWS Bedrock services.

    This class consolidates:
    - AWS credentials resolution (access key, secret key, or IAM role)
    - boto3 client initialization for bedrock-runtime
    - Region configuration
    - Connection verification
    - Common AWS error handling patterns
    """

    DEFAULT_REGION = "us-east-1"

    def __init__(self, config: Dict[str, Any], service_type: ServiceType = None, provider_name: str = "aws"):
        """
        Initialize the aws base service.

        Args:
            config: Configuration dictionary
            service_type: Type of AI service
            provider_name: Provider name (defaults to "aws")
        """
        # For cooperative multiple inheritance
        if service_type:
            super().__init__(config, service_type, provider_name)
        else:
            super().__init__(config, ServiceType.INFERENCE, provider_name)
        self._setup_aws_config()

    def _setup_aws_config(self) -> None:
        """
        Set up AWS-specific configuration.

        This method:
        1. Resolves AWS credentials (explicit or from environment/IAM)
        2. Sets the AWS region
        3. Gets the model configuration
        4. Initializes the boto3 bedrock-runtime client
        """
        aws_config = self._extract_provider_config()

        # Get AWS credentials (optional - can use IAM role)
        self.access_key = aws_config.get("access_key") or self._resolve_api_key("AWS_ACCESS_KEY_ID", required=False)
        self.secret_key = aws_config.get("secret_access_key") or self._resolve_api_key("AWS_SECRET_ACCESS_KEY", required=False)

        # Get region
        self.region = aws_config.get("region", self.DEFAULT_REGION)

        # Get model
        self.model = self._get_model("anthropic.claude-3-sonnet-20240229-v1:0")

        # Response format configuration
        self.content_type = aws_config.get("content_type", "application/json")
        self.accept = aws_config.get("accept", "application/json")

        # Initialize boto3 client
        # If credentials are provided, use them; otherwise, boto3 will use default credential chain
        if self.access_key and self.secret_key:
            self.client = boto3.client(
                "bedrock-runtime",
                region_name=self.region,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key
            )
        else:
            # Use default AWS credential chain (environment vars, IAM role, ~/.aws/credentials, etc.)
            self.client = boto3.client(
                "bedrock-runtime",
                region_name=self.region
            )

        # Setup retry handler
        retry_config = self._get_retry_config()
        self.retry_handler = RetryHandler(
            max_retries=retry_config['max_retries'],
            initial_wait_ms=retry_config['initial_wait_ms'],
            max_wait_ms=retry_config['max_wait_ms'],
            exponential_base=retry_config['exponential_base'],
            enabled=retry_config['enabled']
        )

        logger.info(
            f"Configured AWS Bedrock service with model: {self.model} in region: {self.region}"
        )

    async def initialize(self) -> bool:
        """
        Initialize the AWS Bedrock service.

        Returns:
            True if initialization was successful, False otherwise
        """
        try:
            # Verify connection
            if await self.verify_connection():
                self.initialized = True
                logger.info(
                    f"Initialized AWS Bedrock {self.service_type.value} service "
                    f"with model {self.model}"
                )
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to initialize AWS Bedrock service: {str(e)}")
            return False

    async def verify_connection(self) -> bool:
        """
        Verify AWS Bedrock connection by listing available models.

        Returns:
            True if the connection is working, False otherwise
        """
        try:
            # List foundation models to verify connection
            response = self.client.list_foundation_models()
            model_count = len(response.get('modelSummaries', []))
            logger.debug(
                f"AWS Bedrock connection verified successfully. Found {model_count} models"
            )
            return True
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_msg = e.response['Error']['Message']
            logger.error(
                f"AWS Bedrock connection verification failed [{error_code}]: {error_msg}"
            )
            return False
        except Exception as e:
            logger.error(f"AWS Bedrock connection verification failed: {str(e)}")
            return False

    async def close(self) -> None:
        """
        Close the AWS Bedrock service and release resources.

        Note: boto3 clients don't require explicit cleanup
        """
        self.client = None
        self.initialized = False
        logger.debug("Closed AWS Bedrock service")

    def _get_max_tokens(self, default: int = 1024) -> int:
        """
        Get max_tokens configuration.

        Args:
            default: Default value if not configured

        Returns:
            Maximum number of tokens
        """
        provider_config = self._extract_provider_config()
        return provider_config.get('max_tokens', default)

    def _get_temperature(self, default: float = 0.7) -> float:
        """
        Get temperature configuration.

        Args:
            default: Default value if not configured

        Returns:
            Temperature value
        """
        provider_config = self._extract_provider_config()
        return provider_config.get('temperature', default)

    def _get_top_p(self, default: float = 1.0) -> float:
        """
        Get top_p configuration.

        Args:
            default: Default value if not configured

        Returns:
            Top P value
        """
        provider_config = self._extract_provider_config()
        return provider_config.get('top_p', default)

    def _build_messages(self, prompt: str, messages: list = None) -> tuple[str, list]:
        """
        Build messages for AWS Bedrock, separating the system prompt.

        AWS Bedrock (especially Claude models) requires the system prompt to be
        separate from the conversation messages.

        Args:
            prompt: The input prompt string (used as a fallback)
            messages: An optional list of message dictionaries

        Returns:
            A tuple containing (system_prompt, conversation_messages)
        """
        system_prompt = ""
        conversation_messages = []

        if messages:
            # Case 1: Process a list of messages
            for message in messages:
                if message.get("role") == "system":
                    system_prompt = message.get("content", "")
                else:
                    conversation_messages.append(message)
        else:
            # Case 2: Parse the raw prompt string
            if "\nUser:" in prompt and "Assistant:" in prompt:
                parts = prompt.split("\nUser:", 1)
                if len(parts) == 2:
                    system_prompt = parts[0].strip()
                    user_part = parts[1].replace("Assistant:", "").strip()
                    conversation_messages = [{"role": "user", "content": user_part}]
            else:
                # If no clear separation, treat the whole prompt as a user message
                conversation_messages = [{"role": "user", "content": prompt}]

        # Ensure there's at least one message
        if not conversation_messages:
            conversation_messages = [{"role": "user", "content": ""}]

        return system_prompt, conversation_messages

    def _handle_aws_error(self, error: Exception, operation: str = "operation") -> None:
        """
        Handle AWS-specific errors with appropriate logging.

        Args:
            error: The exception that occurred
            operation: Description of the operation that failed
        """
        if isinstance(error, ClientError):
            error_code = error.response['Error']['Code']
            error_message = error.response['Error']['Message']

            if error_code == 'UnrecognizedClientException':
                logger.error(
                    f"AWS authentication failed during {operation}: Invalid credentials"
                )
            elif error_code == 'ThrottlingException':
                logger.warning(
                    f"AWS rate limit exceeded during {operation}: {error_message}"
                )
            elif error_code == 'ModelNotReadyException':
                logger.error(
                    f"AWS model not ready during {operation}: {error_message}"
                )
            elif error_code == 'ValidationException':
                logger.error(
                    f"AWS validation error during {operation}: {error_message}"
                )
            else:
                logger.error(
                    f"AWS Bedrock error [{error_code}] during {operation}: {error_message}"
                )
        else:
            logger.error(f"Unexpected error during {operation}: {str(error)}")
