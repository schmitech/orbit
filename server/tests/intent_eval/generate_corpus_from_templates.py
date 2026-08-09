#!/usr/bin/env python3
"""
Seeds (or refreshes) an intent-eval corpus from a template library's own
`nl_examples`.

Each `nl_example` is the template author's own claim that a given phrasing
should match that template — the cheapest, least-disputable ground truth
available, and a reasonable bootstrap corpus before hand-labeling a larger
question set (e.g. hr_test_queries.md) is worth the effort.

Re-running this generator OVERWRITES the auto-generated cases (any nl_example
whose query text changed or was removed is regenerated fresh from the
templates file, which is the source of truth). Cases you append with a query
text that doesn't match any current nl_example are preserved across a
regeneration; hand-edits to a case whose query text DOES match an nl_example
are not, since that case is regenerated from the template on every run.

Usage:
    python server/tests/intent_eval/generate_corpus_from_templates.py \\
        --templates examples/intent-templates/sql-intent-template/sqlite/hr/hr-templates.yaml \\
        --output server/tests/intent_eval/corpora/intent-sql-sqlite-hr.yaml \\
        --adapter intent-sql-sqlite-hr
"""

import argparse
import os
import sys

import yaml


def build_corpus(templates_path: str, adapter_name: str, existing_output_path: str = None) -> dict:
    with open(templates_path, "r") as f:
        data = yaml.safe_load(f)

    templates = data.get("templates", data) if isinstance(data, dict) else data
    if not templates:
        raise ValueError(f"No templates found in {templates_path}")

    cases = []
    for tmpl in templates:
        template_id = tmpl.get("id")
        if not template_id:
            continue
        for example in tmpl.get("nl_examples", []) or []:
            cases.append({
                "query": example,
                "expected_template_id": template_id,
                "expect": "match",
            })

    # Preserve any hand-appended cases from a prior run whose query text isn't
    # one of the nl_examples just (re)generated above.
    preserved = []
    if existing_output_path and os.path.exists(existing_output_path):
        with open(existing_output_path, "r") as f:
            existing = yaml.safe_load(f) or {}
        generated_queries = {c["query"] for c in cases}
        preserved = [c for c in existing.get("cases", []) if c.get("query") not in generated_queries]

    return {
        "adapter": adapter_name,
        "source": templates_path,
        "note": (
            "Auto-generated from nl_examples via generate_corpus_from_templates.py. "
            "Cases whose query text matches a current nl_example are regenerated on every "
            "run — hand-edit those upstream in the templates file instead. Cases with any "
            "other query text (append your own below) are preserved across regeneration."
        ),
        "cases": cases + preserved,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--templates", required=True, help="Path to a templates YAML file")
    parser.add_argument("--output", required=True, help="Path to write the corpus YAML")
    parser.add_argument("--adapter", required=True, help="Adapter name this corpus targets")
    args = parser.parse_args()

    corpus = build_corpus(args.templates, args.adapter, existing_output_path=args.output)
    with open(args.output, "w") as f:
        yaml.safe_dump(corpus, f, sort_keys=False, allow_unicode=True, width=100)

    print(f"Wrote {len(corpus['cases'])} cases to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
