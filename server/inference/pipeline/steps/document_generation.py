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
import re
from datetime import date
from typing import Optional, Dict, Any, List

from ..base import PipelineStep, ProcessingContext
from ._utils import get_generation_memory, get_rewrite_prompt_config, store_generation_memory

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
        logger.debug("Document generation: format=%s, adapter=%s", fmt, context.adapter_name)

        spec = await self._generate_spec(context, fmt)
        if spec is None:
            context.set_error("Document spec generation failed.")
            return context

        config = self.container.get_or_none('config') or {}
        renderer_config = config.get('document_renderer', {})
        try:
            renderer = DocumentRenderer(renderer_config)
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
        await store_generation_memory(
            self.container, context.adapter_name, context.session_id, {"spec": spec},
        )
        logger.info("Document generated: format=%s, size=%d bytes", fmt, len(document_bytes))
        return context

    # ------------------------------------------------------------------
    # Shared config helpers
    # ------------------------------------------------------------------

    def _author_display(self) -> str:
        """Return the configured author string (with org suffix when set)."""
        config = self.container.get_or_none('config') or {}
        meta = config.get('document_renderer', {}).get('metadata', {})
        author = meta.get('author', 'ORBIT')
        org = meta.get('organization', '')
        return f"{author} — {org}" if org else author

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

    async def _resolve_rewrite_providers(self, context: ProcessingContext):
        """Resolve an ordered, de-duplicated list of LLM providers to try for spec generation.

        Priority:
        1. Explicit rewrite_provider on the skill adapter config.
        2. Original (calling) adapter's inference_provider.
        3. Skill adapter's inference_provider.
        4. Global llm_provider fallback.

        Returns a list (rather than a single provider) so _generate_spec can fall through to the
        next candidate when one fails — e.g. a bad API key — instead of silently degrading to a
        bare fallback document.
        """
        providers: list = []
        seen_names: set = set()

        def _add(label: Optional[str], provider) -> None:
            if provider is None:
                return
            # De-dupe by provider name so a broken provider (e.g. openai) isn't retried.
            key = label or f"id:{id(provider)}"
            if key in seen_names:
                return
            seen_names.add(key)
            providers.append((label or "provider", provider))

        if self.container.has('adapter_manager'):
            adapter_manager = self.container.get('adapter_manager')

            # 1. Explicit rewrite_provider on the skill adapter config.
            if context.adapter_name:
                skill_config = adapter_manager.get_adapter_config(context.adapter_name)
                if skill_config:
                    rewrite_provider_name = skill_config.get('rewrite_provider')
                    rewrite_model = skill_config.get('rewrite_model') or None
                    if rewrite_provider_name:
                        logger.debug(
                            "Document spec: rewrite_provider=%r rewrite_model=%r",
                            rewrite_provider_name, rewrite_model,
                        )
                        try:
                            # Use provider/model as the de-dupe key so the same provider
                            # with its default model can still serve as a fallback.
                            rewrite_label = (
                                f"{rewrite_provider_name}/{rewrite_model}"
                                if rewrite_model else rewrite_provider_name
                            )
                            _add(
                                rewrite_label,
                                await adapter_manager.get_overridden_provider(
                                    rewrite_provider_name, context.adapter_name,
                                    explicit_model_override=rewrite_model,
                                ),
                            )
                        except Exception as e:
                            logger.debug(
                                "Could not resolve rewrite_provider '%s': %s",
                                rewrite_provider_name, e,
                            )

            # 2/3. Original (calling) adapter, then the skill adapter's inference_provider.
            for adapter_name in (context.original_adapter_name, context.adapter_name):
                if not adapter_name:
                    continue
                adapter_config = adapter_manager.get_adapter_config(adapter_name)
                if not adapter_config:
                    continue
                inference_provider = adapter_config.get('inference_provider')
                if inference_provider:
                    try:
                        _add(
                            inference_provider,
                            await adapter_manager.get_overridden_provider(
                                inference_provider, adapter_name
                            ),
                        )
                    except Exception as e:
                        logger.debug(
                            "Could not resolve provider for '%s': %s", adapter_name, e
                        )

        # 4. Global fallback provider.
        _add("global", self.container.get_or_none('llm_provider'))

        return providers

    # ------------------------------------------------------------------
    # Document spec generation via LLM
    # ------------------------------------------------------------------

    async def _generate_spec(self, context: ProcessingContext, fmt: str) -> Optional[dict]:
        """Call an LLM to produce a structured JSON document specification.

        Tries each candidate provider in priority order, falling through to the next when one
        fails (e.g. a bad API key, a timeout, or malformed JSON). Only when every provider
        fails do we resort to _fallback_spec.
        """
        providers = await self._resolve_rewrite_providers(context)
        if not providers:
            logger.warning("No LLM provider available — using fallback document spec")
            return self._fallback_spec(context)
        logger.debug(
            "Document spec provider queue: %s",
            ", ".join(label for label, _ in providers),
        )

        prompt_cfg = get_rewrite_prompt_config(self.container, 'document')

        # document.yaml's document_generation.llm settings predate the externalized prompt
        # config and remain authoritative when set, so existing overrides (e.g. a larger
        # max_tokens budget for big reports) aren't silently shadowed by rewriters-prompts.yaml.
        config = self.container.get_or_none('config') or {}
        llm_override = config.get('document_generation', {}).get('llm', {})
        max_tokens = llm_override.get('max_tokens', prompt_cfg.get('max_tokens', 2000))
        temperature = llm_override.get('temperature', prompt_cfg.get('temperature', 0.3))
        history_limit = llm_override.get('history_limit', prompt_cfg.get('history_limit', 6))

        memory = await get_generation_memory(self.container, context.adapter_name, context.session_id)
        prompt = self._build_spec_prompt(context, fmt, prompt_cfg, history_limit=history_limit, memory=memory)
        if prompt is None:
            logger.warning("Malformed 'document' rewrite config — using fallback document spec")
            return self._fallback_spec(context)

        for label, llm_provider in providers:
            try:
                raw = await llm_provider.generate(prompt, max_tokens=max_tokens, temperature=temperature)
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
                    logger.warning(
                        "Provider '%s' returned incomplete document spec — trying next provider",
                        label,
                    )
                    continue
                logger.debug(
                    "Document spec generated via '%s': title=%r, sections=%d",
                    label, spec['title'], len(spec['sections']),
                )
                return spec
            except Exception as e:
                logger.warning(
                    "Document spec generation via '%s' failed: %s — trying next provider",
                    label, e,
                )
                continue

        logger.warning("All providers failed for document spec — using fallback")
        return self._fallback_spec(context)

    @staticmethod
    def _extract_markdown_tables(messages: List[Dict[str, str]]) -> List[List[List[str]]]:
        """Parse markdown pipe-tables from conversation messages into 2-D string arrays."""
        tables = []
        for msg in messages:
            content = msg.get('content', '') or ''
            lines = content.splitlines()
            i = 0
            while i < len(lines):
                if '|' in lines[i]:
                    block = []
                    while i < len(lines) and '|' in lines[i]:
                        block.append(lines[i])
                        i += 1
                    rows = []
                    for line in block:
                        cells = [c.strip() for c in line.strip().strip('|').split('|')]
                        # skip separator rows like |---|:---:|
                        if cells and all(re.match(r'^[-: ]+$', c) for c in cells if c):
                            continue
                        cleaned = [re.sub(r'\*{1,2}|`', '', c).strip() for c in cells]
                        if any(cleaned):
                            rows.append(cleaned)
                    if len(rows) >= 2:
                        tables.append(rows)
                else:
                    i += 1
        return tables

    def _build_spec_prompt(
        self, context: ProcessingContext, fmt: str, prompt_cfg: Dict[str, Any], history_limit: int = 6,
        memory: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Build the LLM prompt asking for a JSON document spec from history + context.

        Format hints, rules, section schema, and the overall template are externalized in
        config/rewriters-prompts.yaml (rewriters.document); only the per-format branching and
        markdown-table pre-extraction logic stay here. Returns None if the config is malformed.
        """
        recent_msgs = context.context_messages[-history_limit:] if context.context_messages else []
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

        display_author = self._author_display()
        today = date.today().isoformat()
        previous_generation_text = (
            f"\nPrevious document spec (this request may be a refinement — start from it and "
            f"apply the requested changes):\n{json.dumps(memory['spec'])}\n"
            if memory and memory.get('spec') else ""
        )

        template = prompt_cfg.get('template')
        format_hints = prompt_cfg.get('format_hints', {})
        rules_by_key = prompt_cfg.get('rules', {})
        section_schema_cfg = prompt_cfg.get('section_schema', {})
        if not template or not format_hints or not rules_by_key or not section_schema_cfg:
            logger.warning("Incomplete 'document' rewrite config in config/rewriters-prompts.yaml")
            return None

        hint = format_hints.get(fmt, format_hints.get('default', 'a structured document'))

        # For xlsx and pptx: pre-parse markdown tables from conversation history so the LLM
        # receives structured data directly rather than having to re-extract it from prose.
        pre_extracted = ""
        if fmt in ('xlsx', 'pptx'):
            md_tables = self._extract_markdown_tables(recent_msgs)
            if md_tables:
                lines = ["Pre-extracted table data (use these as \"table\" arrays in the JSON):"]
                for t_idx, tbl in enumerate(md_tables, 1):
                    lines.append(f"Table {t_idx}:")
                    lines.append(json.dumps(tbl))
                pre_extracted = "\n" + "\n".join(lines) + "\n"

        if fmt == 'xlsx':
            rules_key = 'xlsx'
        elif fmt == 'pptx':
            rules_key = 'pptx'
        elif fmt in ('pdf', 'docx'):
            rules_key = 'pdf_docx'
        else:
            rules_key = 'default'
        rules = rules_by_key.get(rules_key, rules_by_key.get('default', ''))

        section_schema = section_schema_cfg.get('base', '')
        if fmt in ('pdf', 'docx', 'pptx'):
            section_schema += section_schema_cfg.get('chart_suffix', '')
        section_schema += '}'

        try:
            return template.format(
                format_hint=hint,
                section_schema=section_schema,
                display_author=display_author,
                today=today,
                rules=rules,
                history_text=history_text,
                pre_extracted=pre_extracted,
                context_text=context_text,
                previous_generation_text=previous_generation_text,
                message=context.message,
            )
        except (KeyError, IndexError) as e:
            logger.warning(f"Malformed 'document' rewrite template in config/rewriters-prompts.yaml: {e}")
            return None

    def _fallback_spec(self, context: ProcessingContext) -> dict:
        """Last-resort spec used when LLM spec generation fails for every provider.

        Pulls the prior assistant analysis and any thread-cached data into the document so a
        provider failure degrades to "the findings, unstructured" rather than "just the
        question". Falls back to the user's message only when no prior content is available.
        """
        sections = []

        # Prior assistant analysis — the content the user usually wants in the document.
        for msg in reversed(context.context_messages or []):
            if msg.get('role') == 'assistant' and (msg.get('content') or '').strip():
                sections.append({
                    "heading": "Summary",
                    "body": msg['content'].strip(),
                    "bullet_points": [],
                })
                break

        # Thread-cached dataset / retrieved context.
        if context.formatted_context and context.formatted_context.strip():
            sections.append({
                "heading": "Data",
                "body": context.formatted_context.strip(),
                "bullet_points": [],
            })

        # Nothing prior to draw on — record the request itself.
        if not sections:
            sections.append({"heading": "Content", "body": context.message, "bullet_points": []})

        return {
            "title": context.message[:100],
            "sections": sections,
            "metadata": {"author": self._author_display(), "date": date.today().isoformat()},
        }
