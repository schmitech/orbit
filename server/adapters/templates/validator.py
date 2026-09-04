"""
Load-time validation for intent template libraries.

Runs the same schema (schema.py) that a template author's authoring-time
tooling should run, so the two can never disagree — a template that passes
validation offline is guaranteed to load the same way here.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from pydantic import ValidationError

from adapters.templates.schema import TemplateSpec

_SCAFFOLDING_MARKER_RE = re.compile(r"#\s*(FIXME|TODO)\b.*$", re.IGNORECASE)


@dataclass
class Finding:
    level: str  # "error" | "warning"
    template_id: Optional[str]
    message: str

    def __str__(self) -> str:
        prefix = f"[{self.template_id}]" if self.template_id else "[library]"
        return f"{prefix} {self.message}"


@dataclass
class ValidationReport:
    path: str
    template_count: int = 0
    findings: list[Finding] = field(default_factory=list)

    def add_error(self, template_id: Optional[str], message: str) -> None:
        self.findings.append(Finding(level="error", template_id=template_id, message=message))

    def add_warning(self, template_id: Optional[str], message: str) -> None:
        self.findings.append(Finding(level="warning", template_id=template_id, message=message))

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "error"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "warning"]

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    def log_summary(self, logger) -> None:
        for finding in self.findings:
            log = logger.error if finding.level == "error" else logger.warning
            log(f"Template validation ({self.path}): {finding}")


class TemplateValidationError(ValueError):
    """Raised in strict mode when a template library fails validation."""

    def __init__(self, report: ValidationReport):
        self.report = report
        error_lines = "\n".join(str(f) for f in report.errors)
        super().__init__(
            f"Template library '{report.path}' failed strict validation "
            f"({len(report.errors)} error(s)):\n{error_lines}"
        )


def content_hash(template: dict[str, Any]) -> str:
    """Stable sha256 hash of a template's canonicalized content, for audit/drift detection."""
    canonical = json.dumps(template, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _extract_templates(raw: Any) -> list[Any]:
    templates = raw.get("templates", raw) if isinstance(raw, dict) else raw
    if isinstance(templates, dict):
        return list(templates.values())
    if isinstance(templates, list):
        return templates
    return []


def _format_pydantic_error(err: dict[str, Any]) -> str:
    loc = ".".join(str(p) for p in err.get("loc", ()))
    return f"{loc}: {err.get('msg')}" if loc else str(err.get("msg"))


def scan_scaffolding_markers(source_text: str) -> list[str]:
    """Flag lines carrying a FIXME/TODO comment — a template left in a
    known-incomplete state by its author. Line-based since these are YAML
    comments, stripped before the file ever reaches parsed data."""
    markers = []
    for lineno, line in enumerate(source_text.splitlines(), start=1):
        match = _SCAFFOLDING_MARKER_RE.search(line)
        if match:
            markers.append(f"line {lineno}: {line.strip()}")
    return markers


def validate_library(
    raw: Optional[dict[str, Any]],
    *,
    path: str,
    strict: bool = False,
    source_text: Optional[str] = None,
) -> ValidationReport:
    """
    Validate every template in a raw (already YAML-parsed) template library
    against TemplateSpec.

    In `strict` mode, any error-level finding raises TemplateValidationError
    instead of returning — the caller should let this fail adapter init.
    In `warn` mode (default), findings are collected and returned for the
    caller to log; templates are not dropped.
    """
    report = ValidationReport(path=path)

    if source_text:
        for marker in scan_scaffolding_markers(source_text):
            report.add_warning(None, f"Scaffolding marker left in file: {marker}")

    for entry in _extract_templates(raw):
        if not isinstance(entry, dict):
            report.add_error(None, f"Template entry is not a mapping: {entry!r}")
            continue

        template_id = entry.get("id", "<no id>")
        report.template_count += 1

        try:
            validated = TemplateSpec.model_validate(entry)
            # Write normalization (e.g. semantic_tags coerced from a list of
            # single-key mappings into one dict) back into the raw entry —
            # this is the dict the adapter actually keeps and later code
            # (embedding text generation, reranking) reads via .get()/.items(),
            # not the discarded TemplateSpec instance.
            if validated.semantic_tags is not None:
                entry["semantic_tags"] = validated.semantic_tags
        except ValidationError as e:
            for err in e.errors():
                report.add_error(template_id, _format_pydantic_error(err))

    if strict and report.has_errors:
        raise TemplateValidationError(report)

    return report
