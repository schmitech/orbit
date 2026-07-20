"""
Thin click wizard over the adapter SDK library.

Run with server/ as the import root (the venv from the repo root):

    cd server
    ../venv/bin/python -m adapter_sdk.cli                                      # interactive wizard
    ../venv/bin/python -m adapter_sdk.cli --list                              # list families
    ../venv/bin/python -m adapter_sdk.cli --spec doc-generator --from-json answers.json --yes

The wizard only collects an `answers` dict; all generation logic lives in the
library (specs/renderer/validator/writer), so a future admin UI can reuse the
same path by producing the same dict.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Optional

import click

from .enricher import enrich_soft_fields
from .renderer import render_adapter
from .specs import SPEC_REGISTRY, Question, get_spec
from .validator import validate_yaml_text
from .writer import write_adapter


def _prompt_question(q: Question, default: Any) -> Any:
    """Prompt for a single question using the variant-aware default."""
    if q.help:
        click.echo(click.style(f"  ({q.help})", fg="bright_black"))

    if q.type == "bool":
        return click.confirm(q.prompt, default=bool(default) if default is not None else False)

    if q.type == "list":
        shown = ", ".join(default) if isinstance(default, list) else ""
        raw = click.prompt(f"{q.prompt} (comma-separated)", default=shown, show_default=True)
        return [item.strip() for item in raw.split(",") if item.strip()]

    if q.type == "int":
        return click.prompt(q.prompt, default=default, type=int)

    # str (optionally with choices); allow blank -> None when default is None (optional field)
    kwargs: Dict[str, Any] = {"default": default, "show_default": True}
    if q.choices:
        kwargs["type"] = click.Choice(q.choices)
    if default is None:
        kwargs["default"] = ""
    val = click.prompt(q.prompt, **kwargs)
    return None if val == "" else val


def _collect_answers(spec) -> Dict[str, Any]:
    answers: Dict[str, Any] = {}
    chosen_variant: Optional[str] = None

    # Ask the variant selector first so subsequent defaults reflect it.
    ordered = list(spec.questions)
    if spec.variant_field:
        ordered.sort(key=lambda q: 0 if q.field == spec.variant_field else 1)

    for q in ordered:
        default = spec.question_default(q, chosen_variant)
        value = _prompt_question(q, default)
        answers[q.field] = value
        if spec.variant_field and q.field == spec.variant_field:
            chosen_variant = value

    return answers


def _maybe_enrich(spec, answers: Dict[str, Any]) -> None:
    """Offer to AI-fill the soft fields for this spec."""
    if not spec.soft_fields():
        return
    if not click.confirm("Use AI to generate skill description / routing examples?", default=False):
        return
    description = click.prompt("Describe in one line what this adapter should do")
    provider = click.prompt("Inference provider to use for generation", default="openai")
    try:
        result = asyncio.run(enrich_soft_fields(spec, description, provider=provider))
    except Exception as exc:  # noqa: BLE001 - surface any provider/JSON error, keep manual answers
        click.echo(click.style(f"  AI enrichment failed ({exc}); keeping manual values.", fg="yellow"))
        return
    for field, value in result.items():
        answers[field] = value
        click.echo(click.style(f"  {field} -> {value}", fg="green"))


@click.command()
@click.option("--list", "list_specs", is_flag=True, help="List available adapter families and exit.")
@click.option("--spec", "spec_key", help="Adapter family key (skips the family prompt).")
@click.option("--from-json", "from_json", type=click.Path(exists=True),
              help="Load answers from a JSON file (non-interactive).")
@click.option("--yes", is_flag=True, help="Write without the final confirmation.")
@click.option("--no-register", is_flag=True, help="Write the file but do not add it to adapters.yaml imports.")
@click.option("--overwrite", is_flag=True, help="Overwrite an existing adapter file.")
@click.option("--dry-run", is_flag=True, help="Render and validate, print YAML, but do not write.")
def main(list_specs, spec_key, from_json, yes, no_register, overwrite, dry_run):
    """Generate an ORBIT adapter config file.

    Interactively, run with no options to pick a family and answer prompts; the
    generated YAML is written to config/adapters/<name>.yaml and registered in
    config/adapters.yaml so ORBIT loads it. Reload without a restart via
    `orbit admin reload-adapters`.

    \b
    Examples:
      python -m adapter_sdk.cli --list                    # list adapter families
      python -m adapter_sdk.cli                            # interactive wizard (opt. AI enrichment)
      python -m adapter_sdk.cli --spec doc-generator --dry-run   # preview, don't write
      python -m adapter_sdk.cli --spec fetch --from-json answers.json --yes   # non-interactive

    \b
    Tip: `--spec <family> --dry-run` prints a valid example you can copy into a
    --from-json answers file (JSON keys = the family's question fields).
    """
    if list_specs:
        for key, spec in SPEC_REGISTRY.items():
            click.echo(f"{click.style(key, fg='cyan', bold=True)}: {spec.description}")
        return

    if not spec_key:
        keys = list(SPEC_REGISTRY)
        for i, key in enumerate(keys, 1):
            click.echo(f"  {i}. {click.style(key, fg='cyan')} — {SPEC_REGISTRY[key].title}")
        idx = click.prompt("Select a family", type=click.IntRange(1, len(keys)))
        spec_key = keys[idx - 1]

    spec = get_spec(spec_key)

    if from_json:
        with open(from_json, encoding="utf-8") as f:
            answers = json.load(f)
    else:
        click.echo(click.style(f"\n{spec.title}: {spec.description}\n", bold=True))
        answers = _collect_answers(spec)
        _maybe_enrich(spec, answers)

    try:
        yaml_text = render_adapter(spec, answers)
    except ValueError as exc:
        click.echo(click.style(str(exc), fg="red", bold=True))
        raise SystemExit(1)

    errors = validate_yaml_text(yaml_text)
    if errors:
        click.echo(click.style("Validation failed:", fg="red", bold=True))
        for e in errors:
            click.echo(click.style(f"  - {e}", fg="red"))
        raise SystemExit(1)

    click.echo(click.style("\n--- generated ---", fg="bright_black"))
    click.echo(yaml_text)
    click.echo(click.style("--- valid ---\n", fg="green"))

    if dry_run:
        return

    name = answers.get("name")
    if not name:
        click.echo(click.style("No 'name' in answers; cannot write.", fg="red"))
        raise SystemExit(1)

    if not yes and not click.confirm(f"Write config/adapters/{name}.yaml"
                                     f"{'' if no_register else ' and register it'}?", default=True):
        click.echo("Aborted.")
        return

    path = write_adapter(name, yaml_text, register=not no_register, overwrite=overwrite)
    click.echo(click.style(f"Wrote {path}", fg="green"))
    if not no_register:
        click.echo(click.style("Registered in config/adapters.yaml imports.", fg="green"))
    click.echo("Reload with: orbit admin reload-adapters (or restart the server).")


if __name__ == "__main__":
    main()
