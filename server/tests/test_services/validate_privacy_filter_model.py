"""
Real-model validation for the privacy_filter moderation service.

Unlike test_privacy_filter_moderation.py (which mocks the pipeline), this script
downloads and runs the REAL openai/privacy-filter model and drives the actual
PrivacyFilterModerationService.moderate_content path. Run it on a machine with
torch + GPU (or CPU with patience) after installing the huggingface profile.

    python server/tests/test_services/validate_privacy_filter_model.py

It answers one question the mocked tests cannot: does the transformers
token-classification pipeline actually emit the bare category labels the service
expects ("private_email", ...), or does the model's BIOES scheme leak "S-"/"E-"
prefixes that the service silently drops? Single-token PII (a bare email, phone,
or account number) is the case most likely to expose the bug, so those are
tested explicitly.

Exit code 0 = every expected detection fired. Non-zero = at least one miss.
"""

import asyncio
import os
import sys

# Resolve imports from server/
SERVER_DIR = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, os.path.abspath(SERVER_DIR))

from ai_services.implementations.moderation.privacy_filter_moderation_service import (  # noqa: E402
    PrivacyFilterModerationService,
    PRIVACY_FILTER_CATEGORIES,
)

# (message, expected pii.<category> keys that MUST be flagged, is_single_token_case)
CASES = [
    # --- Single-token / short PII: the BIOES "S-"/"E-" risk lives here ---
    ("alice.smith@example.com",                 {"pii.private_email"},   True),
    ("416-555-0192",                            {"pii.private_phone"},   True),
    ("000123456789",                            {"pii.account_number"},  True),
    ("sk-live-4f8a2b91c3d7e6f0a1b2c3d4",        {"pii.secret"},          True),
    ("https://john.private.example.com/me",     {"pii.private_url"},     True),
    # --- Multi-token PII: expected to work even if the bug exists ---
    ("Hi, my email is alice.smith@example.com", {"pii.private_email"},   False),
    ("Call me back at 416-555-0192",            {"pii.private_phone"},   False),
    ("My name is Alice Smith",                  {"pii.private_person"},  False),
    ("I live at 22 Baker Street, Toronto",      {"pii.private_address"}, False),
    ("I was born on March 12, 1988",            {"pii.private_date"},    False),
    # --- Benign control: must NOT flag ---
    ("What are your support hours?",            set(),                   False),
]


def dump_model_labels(service):
    """Print the model's ground-truth id2label so mismatches are obvious."""
    try:
        id2label = service.pipeline.model.config.id2label
        labels = sorted(set(id2label.values()))
        print("\n=== model id2label (ground truth) ===")
        print(labels)
        leaks = [l for l in labels if l not in ("O",) and l not in PRIVACY_FILTER_CATEGORIES]
        if leaks:
            print(
                "\n[!] These raw labels are NOT bare categories. If the pipeline "
                "surfaces them as entity_group, the service will DROP them:"
            )
            print("   ", leaks)
    except Exception as e:  # pragma: no cover - diagnostic only
        print(f"(could not read id2label: {e})")


def dump_raw_spans(service, text):
    """Show what the pipeline actually returns for one input."""
    spans = service.pipeline(text)
    groups = [(s.get("entity_group"), round(float(s.get("score", 0)), 3), s.get("word")) for s in spans]
    print(f'    raw pipeline entity_groups: {groups}')


async def main():
    config = {"moderations": {"privacy_filter": {"device": "auto", "threshold": 0.5}}}
    service = PrivacyFilterModerationService(config)

    print(f"Loading model: {service.model} (device={service.device}) ...")
    if not await service.initialize():
        print("FAILED to initialize/load model. Is the huggingface profile installed "
              "and torch>=2.4 available? Aborting.")
        return 2

    print(f"Loaded. device={service.device}")
    dump_model_labels(service)

    print("\n=== per-message results ===")
    failures = []
    for text, expected, single in CASES:
        result = await service.moderate_content(text)
        got = set(result.categories.keys())
        tag = "single-token" if single else ("benign" if not expected else "multi-token")
        missing = expected - got
        unexpected_flag = (not expected) and result.is_flagged

        status = "OK"
        if missing:
            status = "MISS"
            failures.append((text, expected, got, "missing expected category"))
        elif unexpected_flag:
            status = "FALSE-POSITIVE"
            failures.append((text, expected, got, "flagged benign content"))

        print(f"\n[{status}] ({tag}) {text!r}")
        print(f"    flagged={result.is_flagged}  categories={ {k: round(v,3) for k,v in result.categories.items()} }")
        if status != "OK":
            dump_raw_spans(service, text)

    print("\n" + "=" * 60)
    if failures:
        print(f"RESULT: {len(failures)} failure(s). The service is NOT reliably detecting PII:")
        for text, expected, got, why in failures:
            print(f"  - {why}: {text!r}  expected~{expected}  got={got}")
        print("\nIf single-token cases MISS while multi-token pass, the BIOES 'S-'/'E-' "
              "prefix leak is confirmed: fix by normalizing labels in _spans_to_result "
              "(strip a leading [BIES]- prefix) or by decoding spans per the model card.")
        return 1

    print("RESULT: PASS. All expected PII detected, no false positives on the benign "
          "control. The service works end-to-end with the real model.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
