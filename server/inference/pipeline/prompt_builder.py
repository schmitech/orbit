"""
Shared prompt and instruction builder.

This module centralizes system-prompt resolution and system-message
construction so websocket handlers and pipeline steps can use the same
prompt-service backed behavior.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from typing import Optional

from .base import ProcessingContext

logger = logging.getLogger(__name__)


class PromptInstructionBuilder:
    """Builds prompt-service backed system instructions."""

    DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant."

    def __init__(
        self,
        config: Optional[dict] = None,
        prompt_service=None,
        clock_service=None,
        prompt_cache: Optional[OrderedDict[str, str]] = None,
        prompt_cache_max_size: int = 100,
        builder_logger=None,
    ):
        self.config = config or {}
        self.prompt_service = prompt_service
        self.clock_service = clock_service
        self._prompt_cache = prompt_cache if prompt_cache is not None else OrderedDict()
        self._prompt_cache_max_size = prompt_cache_max_size
        self.logger = builder_logger or logger

    async def build_system_message_content(self, context: ProcessingContext) -> str:
        """Build the content for a system message / realtime session instructions."""
        parts = []

        system_prompt = await self.get_system_prompt(context)
        parts.append(system_prompt)

        time_instruction = self.build_time_instruction(context)
        if time_instruction:
            parts.append(time_instruction)

        language_instruction = self.build_language_instruction(context)
        if language_instruction:
            parts.append(language_instruction)

        chart_instruction = self.build_chart_instruction()
        if chart_instruction:
            parts.append(chart_instruction)

        if context.formatted_context:
            is_file_or_multimodal = context.adapter_name and (
                "file" in context.adapter_name.lower() or "multimodal" in context.adapter_name.lower()
            )

            if is_file_or_multimodal:
                parts.append(
                    f"\n<context>\n## UPLOADED FILE CONTENT\n\n{context.formatted_context}\n</context>"
                )
                parts.append(
                    "\nAnswer using the uploaded file content in <context>. If the answer is not there, say so."
                )
            else:
                parts.append(f"\n<context>\n{context.formatted_context}\n</context>")
                parts.append(
                    "\nPrioritize the <context> section when answering. If the answer is not there, say so."
                )
        else:
            parts.append("\nAnswer based on the system prompt. Maintain your persona.")

        return "\n".join(parts)

    def build_time_instruction(self, context: ProcessingContext) -> str:
        """Build time instruction based on clock service and context."""
        if not self.clock_service or not getattr(self.clock_service, "enabled", False):
            return ""

        timezone = getattr(context, "timezone", None)
        time_format = getattr(context, "time_format", None)
        return self.clock_service.get_time_instruction(timezone, time_format)

    async def get_system_prompt(self, context: ProcessingContext) -> str:
        """Resolve the base system prompt from prompt service with fallback."""
        if not context.system_prompt_id:
            return self.DEFAULT_SYSTEM_PROMPT

        cache_key = f"prompt:{context.system_prompt_id}"
        if cache_key in self._prompt_cache:
            self._prompt_cache.move_to_end(cache_key)
            logger.debug("Using in-memory cached system prompt for %s", context.system_prompt_id)
            return self._prompt_cache[cache_key]

        if self.prompt_service:
            try:
                prompt_doc = await self.prompt_service.get_prompt_by_id(context.system_prompt_id)
                if prompt_doc:
                    prompt_text = prompt_doc.get("prompt", "")
                    self._prompt_cache[cache_key] = prompt_text
                    if len(self._prompt_cache) > self._prompt_cache_max_size:
                        self._prompt_cache.popitem(last=False)
                    return prompt_text
            except Exception as e:
                logger.warning("Failed to retrieve system prompt: %s", str(e))

        return self.DEFAULT_SYSTEM_PROMPT

    def build_language_instruction(self, context: ProcessingContext) -> str:
        """Build language instruction based on detected language."""
        lang_detect_config = self.config.get("language_detection", {})
        language_detection_enabled = lang_detect_config.get("enabled", False)

        if not language_detection_enabled:
            if self.logger.isEnabledFor(logging.DEBUG):
                logger.debug("Language detection disabled - no instruction added")
            return ""

        detected_language = getattr(context, "detected_language", None)
        detection_meta = getattr(context, "language_detection_meta", {}) or {}
        min_conf = lang_detect_config.get("min_confidence", 0.7)
        prefer_ascii_en = lang_detect_config.get("prefer_english_for_ascii", True)

        if not detected_language:
            msg = context.message or ""
            ascii_ratio = (sum(1 for c in msg if ord(c) < 128) / len(msg)) if msg else 1.0
            if prefer_ascii_en and ascii_ratio > 0.95:
                return "\nIMPORTANT: Reply entirely in English. Do not include any other language."
            return (
                "\nIMPORTANT: Reply in the same language the user is using. "
                "Always match the user's language. Do not provide translations or explanations in other languages."
            )

        language_names = {
            "en": "English",
            "es": "Spanish",
            "fr": "French",
            "de": "German",
            "it": "Italian",
            "pt": "Portuguese",
            "nl": "Dutch",
            "ru": "Russian",
            "zh": "Chinese",
            "ja": "Japanese",
            "ko": "Korean",
            "ar": "Arabic",
            "hi": "Hindi",
            "th": "Thai",
            "el": "Greek",
            "he": "Hebrew",
        }

        language_name = language_names.get(detected_language, detected_language.upper())

        method = detection_meta.get("method", "")
        confidence = float(detection_meta.get("confidence", 0.0))
        msg = context.message or ""
        ascii_ratio = (sum(1 for c in msg if ord(c) < 128) / len(msg)) if msg else 1.0

        trusted_method = method in (
            "ensemble_voting",
            "word_pattern_detection",
            "phrase_pattern_detection",
        ) and confidence >= 0.5
        trusted_non_en_fallback = method == "threshold_fallback" and detected_language != "en"
        low_conf_or_heuristic = (
            confidence < min_conf and not trusted_method and not trusted_non_en_fallback
        ) or method in ("heuristic_ascii_bias", "all_backends_failed", "length_fallback")
        if prefer_ascii_en and ascii_ratio > 0.95 and low_conf_or_heuristic:
            return (
                "\nIMPORTANT: The user's message appears to be in English or ambiguous. "
                "Default to English and respond entirely in English. Do not include translations or any non-English text."
            )

        if detected_language == "en":
            return "\nIMPORTANT: Respond entirely in English. Do not include any non-English words or translations."

        if confidence >= 0.85 and method not in (
            "threshold_fallback",
            "heuristic_ascii_bias",
            "sticky_previous",
        ):
            instruction = (
                f"\nIMPORTANT: The user is writing in {language_name}. You must respond entirely in {language_name}. "
                f"Do not include translations, explanations in other languages, or bilingual responses. "
                f"Write naturally as a native {language_name} speaker would."
            )
        else:
            instruction = (
                "\nIMPORTANT: Match the language of the user's message. "
                "If the user is writing in English, respond in English. "
                "If they're writing in another language, respond in that same language."
            )

        if self.logger.isEnabledFor(logging.DEBUG):
            logger.debug("Using language instruction for %s (%s)", language_name, detected_language)

        return instruction

    def build_chart_instruction(self) -> str:
        """Build compact chart formatting instruction for LLM."""
        return (
            "--- CHART FORMATTING RULES ---\n"
            "When the user asks for a chart, graph, or visualization, output a fenced code block with language `chart`.\n"
            "When the user asks for a table, use a standard markdown table instead.\n"
            "\n"
            "FORMAT A — Simple (numeric array + labels):\n"
            "```chart\n"
            "type: bar\n"
            "title: Sales by Quarter\n"
            "data: [45000, 52000, 48000, 60000]\n"
            "labels: [Q1, Q2, Q3, Q4]\n"
            "```\n"
            "\n"
            "FORMAT B — Table (auto-detects series from columns):\n"
            "```chart\n"
            "type: line\n"
            "title: Revenue vs Expenses\n"
            "showLegend: true\n"
            "| Month | Revenue | Expenses |\n"
            "|-------|---------|----------|\n"
            "| Jan   | 100000  | 80000    |\n"
            "| Feb   | 112000  | 85000    |\n"
            "```\n"
            "\n"
            "FORMAT C — Key/value with JSON data and series (for advanced charts):\n"
            "```chart\n"
            "type: composed\n"
            "title: Revenue and Margin\n"
            "xKey: month\n"
            "yAxisLabel: Revenue\n"
            "yAxisRightLabel: Margin\n"
            "showLegend: true\n"
            'data: [{"month":"Jan","revenue":120000,"margin":0.28},{"month":"Feb","revenue":134000,"margin":0.31}]\n'
            'series: [{"key":"revenue","name":"Revenue","type":"bar","color":"#3b82f6","yAxisId":"left"},{"key":"margin","name":"Margin","type":"line","color":"#f59e0b","yAxisId":"right"}]\n'
            "```\n"
            "\n"
            "CHART TYPES: bar, line, pie, area, scatter, composed\n"
            "\n"
            "SERIES OBJECT PROPERTIES:\n"
            '  "key": (REQUIRED) the field name in each data object — must match a key in data. Do NOT use "dataKey", always use "key".\n'
            '  "name": display label for the legend\n'
            '  "type": "bar", "line", "area", or "scatter" (only needed for composed charts)\n'
            '  "color": hex color, e.g. "#3b82f6"\n'
            '  "yAxisId": "left" (default) or "right" for dual-axis charts\n'
            '  "stackId": group name to stack bars/areas together\n'
            '  "strokeWidth": line thickness (default 2)\n'
            '  "dot": true/false — show data point dots on lines\n'
            '  "opacity": 0-1 fill opacity for area/bar\n'
            "\n"
            "CONFIG OPTIONS (one per line, key: value):\n"
            "  type, title, description, xKey, xAxisLabel, yAxisLabel, yAxisRightLabel,\n"
            "  xAxisType (category or number), stacked (true/false), showLegend (true/false),\n"
            "  showGrid (true/false), height (pixels), width (pixels),\n"
            "  valueFormat (number/compact/currency/percent), valuePrefix, valueSuffix,\n"
            "  valueDecimals, valueCurrency, colors (comma-separated hex codes)\n"
            "\n"
            "REFERENCE LINES (optional):\n"
            '  referenceLines: [{"y":500,"label":"Target","color":"#ef4444"}]\n'
            "\n"
            "RULES:\n"
            '1. In series arrays, always use "key" — never "dataKey".\n'
            "2. Every item in labels[] must have a corresponding value in data[].\n"
            "3. Every series must reference a field that exists in the data objects.\n"
            "4. labels[] and data[] arrays must be the same length.\n"
            "5. Use hex color codes (e.g. #3b82f6). Labels can contain spaces.\n"
            "6. For pie charts, use xKey for the name field and a single series key for the value field.\n"
            "--- END CHART FORMATTING RULES ---\n"
        )
