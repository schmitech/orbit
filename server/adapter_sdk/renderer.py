"""
Renderer — turns a spec + answers into idiomatic, commented adapter YAML.

Uses Jinja2 (available in the venv) with one template per family under templates/,
modeled on the existing config/adapters/*.yaml files so the output keeps the
operator-guidance comments.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from .specs import AdapterSpec

_TEMPLATE_DIR = Path(__file__).parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    undefined=StrictUndefined,  # fail loudly on a missing variable instead of emitting blanks
    trim_blocks=False,
    lstrip_blocks=False,
    keep_trailing_newline=True,
)


def render_adapter(spec: AdapterSpec, answers: Dict[str, Any]) -> str:
    """Render one adapter file from a spec and a full set of answers."""
    context = spec.resolve(answers)
    template = _env.get_template(spec.template)
    return template.render(**context)
