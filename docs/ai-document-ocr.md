# AI/LLM Document OCR

## Overview

ORBIT ships two local "universal" document processors — **Docling** (IBM) and **MarkItDown** (Microsoft). Both extract text well from digitally-authored documents but struggle with **scanned or image-only PDFs**, where there is no text layer to pull from.

The **AI document processor** (`ai_document`) adds a third option that offloads OCR to an LLM inference service. It is a peer to Docling and MarkItDown: enabled by a flag, selected via `processor_priority`, and it handles **PDFs and images**.

It is **opt-in** and disabled by default.

## Backends

The active backend is chosen by `files.processing.ai_document.provider` and must also be enabled in `ocr.yaml`.

| Backend | Providers | How it works |
|:--|:--|:--|
| **Mistral native OCR** | `mistral` | Sends the PDF/image directly to Mistral's dedicated `client.ocr` endpoint, which returns per-page markdown. No rasterization. |
| **Vision-backed** | `openai`, `gemini`, `anthropic`, `cohere`, `ollama`, `vllm`, `llama_cpp` | Rasterizes each PDF page to an image (via `pypdfium2`) and calls the provider's existing vision model (`VisionService.extract_text_from_image`). Single-frame images are OCR'd directly; multi-frame images (multi-page TIFF, animated GIF) are split frame-by-frame. |

Vision-backed providers reuse their per-provider settings (API key, model) from `vision.yaml`. The `ocr.yaml` entry for those providers only needs an `enabled` flag.

## Enabling it

1. **`config/config.yaml`** — turn it on and make it the priority processor:

   ```yaml
   files:
     processing:
       ai_document_enabled: true
       processor_priority: "ai_document"   # try AI OCR first for PDFs and images
       ai_document:
         provider: "mistral"               # mistral | openai | gemini | anthropic | cohere | ollama | vllm | llama_cpp
         model: null                       # optional override; null = provider's model from ocr.yaml
         max_pages: 50                     # cap pages/frames for vision-backed providers (Mistral ignores)
         dpi: 150                          # rasterization DPI for vision-backed PDF OCR
         prompt: null                      # optional custom OCR prompt (vision-backed only)
   ```

2. **`config/ocr.yaml`** — enable the provider you selected (the provider **must** be `enabled: true` here, since service registration is gated on it):

   ```yaml
   ocr:
     mistral:
       enabled: true
       api_key: ${MISTRAL_API_KEY}
       model: "mistral-ocr-latest"
   ```

See [`ocr.yaml`](../install/default-config/ocr.yaml) for the full OCR provider reference and the `files.processing` section of [`config.yaml`](../install/default-config/config.yaml) for the `ai_document` block.

## How it overrides the vision path

This is the important interaction to understand. ORBIT already has a **vision path** for images: in `FileProcessingService._extract_content`, any upload with an `image/*` MIME type is normally dispatched to `_extract_image_content`, which calls the configured `VisionService` and returns an image **description plus OCR text** — *before* the file ever reaches the processor registry. PDFs, by contrast, always go through the processor registry.

When the AI document processor is the **priority** processor, it takes over image handling too:

```python
# server/services/file_processing/file_processing_service.py
if self.enable_vision and mime_type.startswith('image/') and not self._ai_ocr_is_priority():
    return await self._extract_image_content(...)   # normal vision path
...
processors = self.processor_registry.get_processors(mime_type)   # AIDocumentProcessor is first
```

`_ai_ocr_is_priority()` returns true only when **both** `ai_document_enabled: true` and `processor_priority: "ai_document"`. When that holds, the `image/*` short-circuit is skipped, so images fall through to the registry — where `AIDocumentProcessor` is registered first and handles them through the OCR service. In effect, **choosing `ai_document` as the priority processor reroutes images away from the vision adapter and through the OCR backend instead.**

### Routing summary

| `processor_priority` | `ai_document_enabled` | PDFs | Images |
|:--|:--|:--|:--|
| `ai_document` | `true` | AI OCR (registry) | **AI OCR** (vision path skipped) |
| `markitdown` / `docling` | `true` | MarkItDown/Docling first; AI OCR is a fallback | Vision path (unchanged) |
| any | `false` | Docling/MarkItDown/native | Vision path (unchanged) |

So the AI processor only "overrides" the vision adapter when it is explicitly made the priority processor. Enabling it without prioritizing it leaves image handling on the vision path and keeps AI OCR available only as a PDF fallback.

### Behavioral differences vs the vision path

| | Vision path (`_extract_image_content`) | AI OCR (`AIDocumentProcessor`) |
|:--|:--|:--|
| Output | Image **description** + extracted text | OCR **markdown** only (pages joined with `\n\n---\n\n`) |
| PDFs | Not handled (registry does) | Handled (native or rasterized) |
| Multi-page images | First frame only | All frames (up to `max_pages` for vision-backed) |
| `extraction_method` metadata | `vision` | `ai_ocr` |
| Per-adapter provider override | Yes (`vision_provider`, resolved per API key) | **No** — uses the global `ai_document.provider` (see Limitations) |

## Metadata

Files processed by the AI OCR processor are tagged with:

- `processed_by: "ai_ocr"`
- `extraction_method: "ai_ocr"`
- `ocr_provider: "<provider>"`
- `page_count` — the number of pages/frames **actually OCR'd**: capped at `max_pages` for vision-backed providers, full document count for Mistral (which ignores `max_pages`).

## Limitations

- **PDFs and images only.** Other formats (DOCX, PPTX, XLSX, HTML, CSV, …) already carry extractable text and continue to route to Docling / MarkItDown / native processors. To OCR an office document, convert it to PDF first.
- **No per-adapter OCR provider override.** The vision path resolves a per-API-key `vision_provider` from the adapter config; the processor path has no API key, so AI OCR always uses the global `files.processing.ai_document.provider`. A per-adapter `ocr_provider` override is a possible follow-up.
- **Model override bypasses the vision cache.** When `ai_document.model` is set for a vision-backed provider, the underlying `VisionService` is built with `use_cache=false` so the override is honored without reading or polluting the shared vision-service cache. With no override, the shared cache is used as normal.
- **Cost/latency.** Vision-backed OCR makes one model call per page; large PDFs can be slow and expensive. Use `max_pages` to bound this, or prefer Mistral's native OCR for multi-page PDFs.

## Dependencies

No extra install beyond the `files` profile: `pypdfium2` and `Pillow` (page rasterization) and `mistralai` (Mistral backend) are already included. Vision-backed providers require their respective provider SDK/keys, same as the vision feature.
```

