"""
Vision-backed OCR services.

For providers that expose image understanding but no dedicated OCR endpoint
(OpenAI, Gemini, Anthropic, ...), this reuses the existing ``VisionService``:
images are OCR'd directly, and PDFs are rasterized page-by-page with pypdfium2
and each page image is sent through ``extract_text_from_image``.

Each provider gets a thin subclass so the factory can instantiate it by name
(the factory calls ``ServiceClass(config)`` with no provider argument).
"""

import asyncio
import logging
from io import BytesIO
from typing import Dict, Any, List, Optional

from ...base import ServiceType
from ...services import OcrService

logger = logging.getLogger(__name__)

# Bound concurrent per-page vision calls so a large PDF doesn't fan out to
# hundreds of simultaneous API requests.
_MAX_CONCURRENT_PAGES = 4


class VisionBackedOcrService(OcrService):
    """OCR service that delegates to a VisionService, rasterizing PDFs first."""

    # Overridden by concrete provider subclasses.
    VISION_PROVIDER: str = ""

    def __init__(self, config: Dict[str, Any], provider_name: Optional[str] = None):
        super().__init__(config, provider_name or self.VISION_PROVIDER)
        self._vision_service = None

        # OCR tuning forwarded from files.processing.ai_document by the processor.
        ai_cfg = config.get("ai_document", {}) or {}
        self.max_pages = ai_cfg.get("max_pages", 50)
        self.dpi = ai_cfg.get("dpi", 150)
        self.prompt = ai_cfg.get("prompt")
        self.model_override = ai_cfg.get("model")

    async def initialize(self) -> bool:
        """Build and initialize the underlying vision service."""
        from ...factory import AIServiceFactory

        visions_config = self.config.get("visions", {})
        if self.model_override:
            # Apply the OCR model override to this provider's vision config.
            visions_config = dict(visions_config)
            provider_cfg = dict(visions_config.get(self.provider_name, {}))
            provider_cfg["model"] = self.model_override
            visions_config[self.provider_name] = provider_cfg

        # Bypass the factory cache when overriding the model so we don't read a
        # differently-configured cached VisionService, nor pollute the shared
        # cache used by the direct vision path (it keys only on type+provider).
        self._vision_service = AIServiceFactory.create_service(
            ServiceType.VISION,
            self.provider_name,
            {"visions": visions_config},
            use_cache=not bool(self.model_override),
        )
        if not self._vision_service.initialized:
            await self._vision_service.initialize()
        self.initialized = True
        return True

    async def verify_connection(self) -> bool:
        return True

    async def close(self) -> None:
        self._vision_service = None
        self.initialized = False

    async def extract_document(
        self,
        file_data: bytes,
        mime_type: str,
        filename: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.initialized:
            await self.initialize()

        if mime_type.startswith("image/"):
            page_images = self._split_image_frames(file_data)
        else:
            page_images = self._rasterize_pdf(file_data)

        if not page_images:
            return {"text": "", "page_count": 0}

        semaphore = asyncio.Semaphore(_MAX_CONCURRENT_PAGES)

        async def _ocr_bounded(image_bytes: bytes) -> str:
            async with semaphore:
                return await self._ocr_image(image_bytes)

        page_texts = await asyncio.gather(*[_ocr_bounded(img) for img in page_images])
        text = "\n\n---\n\n".join(page_texts)
        return {"text": text, "page_count": len(page_images)}

    async def _ocr_image(self, image_bytes: bytes) -> str:
        if self.prompt:
            return await self._vision_service.analyze_image(image_bytes, prompt=self.prompt)
        return await self._vision_service.extract_text_from_image(image_bytes)

    def _split_image_frames(self, file_data: bytes) -> List[bytes]:
        """Split a multi-frame image (e.g. multi-page TIFF, animated GIF) into
        one PNG per frame. Single-frame images are returned unchanged so the
        vision service still sees the original bytes/format."""
        from PIL import Image, ImageSequence

        try:
            img = Image.open(BytesIO(file_data))
        except Exception as e:
            logger.debug(f"Could not open image for frame inspection: {e}")
            return [file_data]

        if getattr(img, "n_frames", 1) <= 1:
            return [file_data]

        total_frames = img.n_frames
        frames: List[bytes] = []
        for i, frame in enumerate(ImageSequence.Iterator(img)):
            if i >= self.max_pages:
                logger.warning(
                    f"Image has {total_frames} frames; OCR limited to first {self.max_pages} "
                    f"(files.processing.ai_document.max_pages)"
                )
                break
            buf = BytesIO()
            frame.convert("RGB").save(buf, format="PNG")
            frames.append(buf.getvalue())
        return frames

    def _rasterize_pdf(self, file_data: bytes) -> List[bytes]:
        """Render PDF pages to PNG bytes (capped at max_pages)."""
        import pypdfium2 as pdfium

        scale = self.dpi / 72.0
        pdf = pdfium.PdfDocument(file_data)
        try:
            page_count = min(len(pdf), self.max_pages)
            if len(pdf) > self.max_pages:
                logger.warning(
                    f"PDF has {len(pdf)} pages; OCR limited to first {self.max_pages} "
                    f"(files.processing.ai_document.max_pages)"
                )
            images: List[bytes] = []
            for i in range(page_count):
                bitmap = pdf[i].render(scale=scale)
                pil_image = bitmap.to_pil()
                buf = BytesIO()
                pil_image.save(buf, format="PNG")
                images.append(buf.getvalue())
            return images
        finally:
            pdf.close()


class OpenAIOcrService(VisionBackedOcrService):
    VISION_PROVIDER = "openai"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config, "openai")


class GeminiOcrService(VisionBackedOcrService):
    VISION_PROVIDER = "gemini"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config, "gemini")


class AnthropicOcrService(VisionBackedOcrService):
    VISION_PROVIDER = "anthropic"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config, "anthropic")


class CohereOcrService(VisionBackedOcrService):
    VISION_PROVIDER = "cohere"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config, "cohere")


class OllamaOcrService(VisionBackedOcrService):
    VISION_PROVIDER = "ollama"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config, "ollama")


class VLLMOcrService(VisionBackedOcrService):
    VISION_PROVIDER = "vllm"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config, "vllm")


class LlamaCppOcrService(VisionBackedOcrService):
    VISION_PROVIDER = "llama_cpp"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config, "llama_cpp")
