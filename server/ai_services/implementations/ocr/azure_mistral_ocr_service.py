"""
Azure AI Foundry native Mistral Document AI (OCR) service.

Mistral OCR/Document AI deployments on Azure AI Foundry are NOT reachable
through the OpenAI-compatible chat.completions surface (AzureBaseService) —
they expose Mistral's own native OCR protocol at a dedicated endpoint (e.g.
``https://<resource>.services.ai.azure.com/providers/mistral/azure/ocr``).
This service uses the ``mistralai.azure`` client (bundled with the
``mistralai`` SDK already required for MistralOcrService), which speaks that
exact protocol/auth, and mirrors MistralOcrService's request/response
handling. See docs/integrations/azure-mistral-ocr.md for background on why
the chat-completions route 404s with ``api_not_supported`` for this model.
"""

import base64
import logging
from typing import Dict, Any, Optional

from ...errors import raise_sanitized
from ...services import OcrService

logger = logging.getLogger(__name__)

# The SDK's ocr.process_async() hardcodes this path and appends it to
# whatever server_url is configured — passing the full Target URI (which
# already ends in this path, per Azure's own deployment-page sample) would
# double it up into .../providers/mistral/azure/ocr/providers/mistral/azure/ocr
# and 404. Strip it back off so users can still paste the documented Target
# URI verbatim into config.
_OCR_ROUTE_SUFFIX = "/providers/mistral/azure/ocr"


class AzureMistralOcrService(OcrService):
    """Mistral Document AI OCR hosted on Azure AI Foundry (``mistralai.azure`` client)."""

    DEFAULT_API_VERSION = "2024-05-01-preview"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config, "azure_mistral")
        self._setup_azure_mistral_config()

    def _setup_azure_mistral_config(self) -> None:
        provider_config = self._extract_provider_config()

        # Copy the exact Target URI shown on the deployment's Azure AI
        # Foundry page — the host/path shape varies by deployment type
        # (unified Foundry endpoint vs. a dedicated serverless host), so
        # this is not defaulted or guessed.
        self.endpoint = provider_config.get("endpoint")
        if not self.endpoint:
            raise ValueError(
                "Azure endpoint is required for azure_mistral OCR. Set it in "
                "configuration under ocr.azure_mistral.endpoint — copy the exact "
                "Target URI from the deployment's Azure AI Foundry page."
            )

        # AZURE_OCR_API_KEY is the documented env var for this service
        # (env.example); AZURE_API_KEY is kept only as a compatibility
        # fallback for setups that already share one Azure key across
        # services.
        self.api_key = (
            provider_config.get("api_key")
            or self._resolve_api_key("AZURE_OCR_API_KEY")
            or self._resolve_api_key("AZURE_API_KEY")
        )
        if not self.api_key:
            raise ValueError(
                "Azure API key is required for azure_mistral OCR. Set AZURE_OCR_API_KEY "
                "environment variable or provide it in configuration."
            )

        self.model = provider_config.get("deployment_name") or provider_config.get("model") or "mistral-document-ai-2505"
        self.api_version = provider_config.get("api_version", self.DEFAULT_API_VERSION)

        from mistralai.azure.client import MistralAzure

        # Strip the OCR route the SDK appends itself, so the full documented
        # Target URI can still be pasted into config verbatim (see
        # _OCR_ROUTE_SUFFIX above).
        server_url = self.endpoint.rstrip("/")
        if server_url.lower().endswith(_OCR_ROUTE_SUFFIX):
            server_url = server_url[: -len(_OCR_ROUTE_SUFFIX)]

        self.client = MistralAzure(
            api_key=self.api_key,
            server_url=server_url,
            api_version=self.api_version,
        )

        logger.debug(f"Configured Azure Mistral OCR service with model: {self.model}")

    async def initialize(self) -> bool:
        # No cheap connectivity probe exists for this endpoint (unlike a
        # models.list()-style call) — client construction above is all that's
        # required, mirroring MistralOcrService's lightweight verification.
        self.initialized = True
        return True

    async def verify_connection(self) -> bool:
        return self.initialized

    async def close(self) -> None:
        self.client = None
        self.initialized = False

    async def extract_document(
        self,
        file_data: bytes,
        mime_type: str,
        filename: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Extract markdown from a PDF or image via Azure's Mistral OCR endpoint."""
        if not self.initialized:
            await self.initialize()

        b64 = base64.b64encode(file_data).decode("utf-8")
        if mime_type.startswith("image/"):
            document = {
                "type": "image_url",
                "image_url": f"data:{mime_type};base64,{b64}",
            }
        else:
            document = {
                "type": "document_url",
                "document_url": f"data:application/pdf;base64,{b64}",
            }
            if filename:
                document["document_name"] = filename

        try:
            response = await self.client.ocr.process_async(
                model=self.model,
                document=document,
            )
        except Exception as e:
            self._handle_azure_mistral_error(e, "document OCR")
            raise

        pages = getattr(response, "pages", None) or []
        markdown = "\n\n---\n\n".join(
            (getattr(page, "markdown", "") or "") for page in pages
        )
        return {
            "text": markdown,
            "page_count": len(pages),
            "media_usage": {"unit": "pages", "quantity": len(pages)},
        }

    def _handle_azure_mistral_error(self, error: Exception, operation: str = "operation") -> None:
        error_str = str(error)
        if "401" in error_str or "unauthorized" in error_str.lower():
            logger.error(f"Azure Mistral OCR authentication failed during {operation}: Invalid credentials")
        elif "404" in error_str:
            logger.error(
                f"Azure Mistral OCR endpoint not found during {operation} — verify "
                f"ocr.azure_mistral.endpoint matches the exact Target URI from the "
                f"Azure AI Foundry deployment page: {error_str}"
            )
        elif "rate limit" in error_str.lower() or "429" in error_str:
            logger.warning(f"Azure Mistral OCR rate limit exceeded during {operation}")
        else:
            logger.error(f"Azure Mistral OCR error during {operation}: {error_str}")

        raise_sanitized(error, provider=self.provider_name, operation=operation)
