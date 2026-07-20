"""
ORBIT Adapter SDK.

A small library for generating ORBIT adapter config files (config/adapters/*.yaml)
from a deterministic spec registry, with optional AI enrichment of "soft" fields.

Public surface:
    - specs:     AdapterSpec dataclass + SPEC_REGISTRY (source of truth)
    - renderer:  render_adapter(spec, answers) -> YAML text
    - validator: validate_structure(config) -> list[str] of errors
    - writer:    write_adapter(...) -> writes file + registers in adapters.yaml
    - enricher:  enrich_soft_fields(...) -> AI-filled skill_description/routing_examples

The core (specs/renderer/validator/writer) is non-interactive: it takes an
`answers` dict and returns/writes YAML. The click wizard in cli.py and any future
admin UI are just front-ends that produce that dict.
"""

from .specs import AdapterSpec, Question, SPEC_REGISTRY, get_spec

__all__ = ["AdapterSpec", "Question", "SPEC_REGISTRY", "get_spec"]
