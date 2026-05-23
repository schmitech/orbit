"""
Document Generation Step

Generates a document (PDF, DOCX, XLSX, PPTX) from the user's prompt when the adapter
is of type 'document_generation'. Replaces LLMInferenceStep for such adapters.

Flow:
  1. Resolve output format from adapter config (document_format field).
  2. Use an LLM to convert the user's message + context/history into a JSON document spec.
  3. Render the spec to bytes with DocumentRenderer (native Python libs, no external API).
  4. Store base64-encoded bytes in context.document and set context.document_format.
"""

import base64
import json
import logging
from datetime import date
from typing import Optional, Dict, Any

from ..base import PipelineStep, ProcessingContext

logger = logging.getLogger(__name__)


def _get_adapter_type(container, adapter_name: str) -> Optional[str]:
    """Return the adapter's 'type' field, or None if unavailable."""
    if not adapter_name or not container.has('adapter_manager'):
        return None
    try:
        adapter_manager = container.get('adapter_manager')
        adapter_config = adapter_manager.get_adapter_config(adapter_name)
        if adapter_config:
            return adapter_config.get('type')
    except Exception:
        pass
    return None


class DocumentGenerationStep(PipelineStep):
    """
    Generate a document from the user's text prompt.

    Executes only for adapters whose 'type' is 'document_generation'.
    Stores the result in context.document (base64), context.document_format,
    and context.document_revised_prompt.
    """

    def should_execute(self, context: ProcessingContext) -> bool:
        if context.is_blocked:
            return False
        return _get_adapter_type(self.container, context.adapter_name) == 'document_generation'

    def supports_streaming(self) -> bool:
        return False

    async def process(self, context: ProcessingContext) -> ProcessingContext:
        from ai_services.services.document_generation_service import DocumentRenderer

        fmt = self._resolve_format(context)
        logger.info("Document generation: format=%s, adapter=%s", fmt, context.adapter_name)

        spec = await self._generate_spec(context, fmt)
        if spec is None:
            context.set_error("Document spec generation failed.")
            return context

        try:
            renderer = DocumentRenderer()
            document_bytes = renderer.render(spec, fmt)
        except ImportError as e:
            context.set_error(
                f"Document generation library not installed: {e}. "
                "Install the 'files' dependency profile."
            )
            return context
        except Exception as e:
            logger.error("Document rendering failed: %s", e, exc_info=True)
            context.set_error(f"Document rendering failed: {e}")
            return context

        context.document = base64.b64encode(document_bytes).decode("utf-8")
        context.document_format = fmt
        context.document_revised_prompt = spec.get("title") or context.message
        context.response = context.document_revised_prompt
        logger.info("Document generated: format=%s, size=%d bytes", fmt, len(document_bytes))
        return context

    # ------------------------------------------------------------------
    # Format resolution
    # ------------------------------------------------------------------

    def _resolve_format(self, context: ProcessingContext) -> str:
        """Get format from adapter config, then global config, then default to 'pdf'."""
        if context.adapter_name and self.container.has('adapter_manager'):
            try:
                adapter_manager = self.container.get('adapter_manager')
                adapter_config = adapter_manager.get_adapter_config(context.adapter_name)
                if adapter_config:
                    fmt = adapter_config.get('document_format')
                    if fmt:
                        return fmt.lower()
            except Exception:
                pass
        config = self.container.get_or_none('config') or {}
        return config.get('document', {}).get('default_format', 'pdf')

    # ------------------------------------------------------------------
    # LLM provider resolution (mirrors ImageGenerationStep / VideoGenerationStep)
    # ------------------------------------------------------------------

    async def _resolve_rewrite_provider(self, context: ProcessingContext):
        """Resolve the LLM provider for document spec generation.

        Priority:
        1. Explicit rewrite_provider on the skill adapter config.
        2. Original adapter's inference_provider.
        3. Skill adapter's inference_provider.
        4. Global llm_provider fallback.
        """
        if self.container.has('adapter_manager'):
            adapter_manager = self.container.get('adapter_manager')

            if context.adapter_name:
                skill_config = adapter_manager.get_adapter_config(context.adapter_name)
                if skill_config:
                    rewrite_provider_name = skill_config.get('rewrite_provider')
                    if rewrite_provider_name:
                        try:
                            provider = await adapter_manager.get_overridden_provider(
                                rewrite_provider_name, context.adapter_name
                            )
                            if provider:
                                logger.debug(
                                    "Using rewrite_provider '%s' for document spec generation",
                                    rewrite_provider_name,
                                )
                                return provider
                        except Exception as e:
                            logger.debug(
                                "Could not resolve rewrite_provider '%s': %s",
                                rewrite_provider_name, e,
                            )

            for adapter_name in (context.original_adapter_name, context.adapter_name):
                if not adapter_name:
                    continue
                adapter_config = adapter_manager.get_adapter_config(adapter_name)
                if not adapter_config:
                    continue
                inference_provider = adapter_config.get('inference_provider')
                if inference_provider:
                    try:
                        provider = await adapter_manager.get_overridden_provider(
                            inference_provider, adapter_name
                        )
                        if provider:
                            return provider
                    except Exception as e:
                        logger.debug(
                            "Could not resolve provider for '%s': %s", adapter_name, e
                        )

        return self.container.get_or_none('llm_provider')

    # ------------------------------------------------------------------
    # Document spec generation via LLM
    # ------------------------------------------------------------------

    async def _generate_spec(self, context: ProcessingContext, fmt: str) -> Optional[dict]:
        """Call an LLM to produce a structured JSON document specification."""
        llm_provider = await self._resolve_rewrite_provider(context)
        if not llm_provider:
            logger.warning("No LLM provider available — using fallback document spec")
            return self._fallback_spec(context)

        # Build context from conversation history (cap at 6 turns)
        recent_msgs = context.context_messages[-6:] if context.context_messages else []
        if (recent_msgs and recent_msgs[-1].get('role') == 'user'
                and recent_msgs[-1].get('content', '').strip() == context.message.strip()):
            recent_msgs = recent_msgs[:-1]

        history_lines = []
        for msg in recent_msgs:
            role = msg.get('role', 'user').title()
            content = msg.get('content', '')
            if role and content:
                history_lines.append(f"{role}: {content}")
        history_text = "\n".join(history_lines) if history_lines else "No prior conversation."
        context_text = (
            f"\nData/Context:\n{context.formatted_context}\n"
            if context.formatted_context else ""
        )

        format_hints: Dict[str, str] = {
            'pdf': 'a structured report with sections, paragraphs, and tables',
            'docx': 'a Word document with headings, paragraphs, and tables',
            'xlsx': 'a spreadsheet where each section becomes a named worksheet with tabular data',
            'pptx': 'a presentation where each section becomes a slide with a title and bullet points',
        }
        hint = format_hints.get(fmt, 'a structured document')
        today = date.today().isoformat()

        prompt = (
            f"You are a document structure designer. Generate {hint}.\n"
            "Output ONLY a valid JSON object — no markdown code fences, no explanation.\n\n"
            "Required JSON schema:\n"
            '{"title": "...", "sections": [{"heading": "...", "body": "...", '
            '"table": [["col1", "col2"], ["val1", "val2"]], "bullet_points": ["..."]}], '
            f'"metadata": {{"author": "ORBIT", "date": "{today}"}}}}\n\n'
            "Rules:\n"
            "1. Use the conversation history and any data/context to populate real content.\n"
            "2. Every section must have at least a heading and either body text or bullet_points.\n"
            "3. Include a table only when the data has rows and columns; omit the table key otherwise.\n"
            "4. Output ONLY the JSON object. No extra text before or after.\n\n"
            f"Conversation History:\n{history_text}\n"
            f"{context_text}"
            f"User request: {context.message}"
        )

        try:
            raw = await llm_provider.generate(prompt, max_tokens=2000, temperature=0.3)
            raw = raw.strip()
            # Strip markdown code fences if the LLM ignored the instruction
            if raw.startswith("```"):
                parts = raw.split("```")
                raw = parts[1] if len(parts) > 1 else raw
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()
            spec = json.loads(raw)
            if 'title' not in spec or 'sections' not in spec:
                logger.warning("LLM returned incomplete document spec — using fallback")
                return self._fallback_spec(context)
            logger.debug(
                "Document spec generated: title=%r, sections=%d",
                spec['title'], len(spec['sections']),
            )
            return spec
        except Exception as e:
            logger.warning("Failed to generate document spec: %s — using fallback", e)
            return self._fallback_spec(context)

    @staticmethod
    def _fallback_spec(context: ProcessingContext) -> dict:
        """Minimal single-section spec used when LLM spec generation fails."""
        return {
            "title": context.message[:100],
            "sections": [
                {"heading": "Content", "body": context.message, "bullet_points": []}
            ],
            "metadata": {"author": "ORBIT", "date": date.today().isoformat()},
        }
