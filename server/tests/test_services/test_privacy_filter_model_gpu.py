"""
Real-model (GPU) validation of the privacy_filter moderation service, as pytest.

This is the CI-runnable form of validate_privacy_filter_model.py: same cases,
same intent, but expressed as marked tests so a GPU runner can gate the PR.

    # on a GPU runner (torch>=2.4 + CUDA, huggingface profile installed):
    pytest server/tests/ -m gpu

The whole module SKIPS (never fails) when no accelerator/torch is available, so
it is inert on the default CPU test box and in the normal `pytest -m unit` run.

Why it exists: the mocked unit tests inject clean `entity_group` labels and so
cannot catch the model's BIOES scheme leaking `S-`/`E-` prefixes that the
service drops — which would make single-token PII (a bare email/phone/account
number) invisible. These tests download the real model and assert those short
cases actually flag.
"""

import asyncio
import os
import sys

import pytest

# Resolve imports from server/ and from this test directory (for the shared script)
SERVER_DIR = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, os.path.abspath(SERVER_DIR))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _accelerator_available() -> bool:
    """True only if torch>=2.4 is usable AND a GPU (CUDA or MPS) is present.

    The >=2.4 floor matches transformers 5.x, which disables older torch and
    would leave the model unloadable anyway.
    """
    try:
        import torch
    except Exception:
        return False
    try:
        major, minor = (int(p) for p in torch.__version__.split(".")[:2])
        if (major, minor) < (2, 4):
            return False
        if torch.cuda.is_available():
            return True
        return bool(getattr(torch.backends, "mps", None) and torch.backends.mps.is_available())
    except Exception:
        return False


# Skip the entire module unless a real accelerator is present.
pytestmark = [
    pytest.mark.gpu,
    pytest.mark.skipif(
        not _accelerator_available(),
        reason="needs torch>=2.4 with CUDA or MPS; skipped on CPU-only boxes",
    ),
]

# Import the shared cases so the script and CI stay in lockstep.
from validate_privacy_filter_model import CASES  # noqa: E402
from ai_services.implementations.moderation.privacy_filter_moderation_service import (  # noqa: E402
    PrivacyFilterModerationService,
)


@pytest.fixture(scope="module")
def loaded_service():
    """Download + load the real model once for the whole module."""
    config = {"moderations": {"privacy_filter": {"device": "auto", "threshold": 0.5}}}
    service = PrivacyFilterModerationService(config)
    ok = asyncio.run(service.initialize())
    if not ok:
        pytest.skip("privacy_filter model failed to load (missing weights or torch<2.4)")
    yield service
    asyncio.run(service.close())


@pytest.mark.parametrize(
    "text,expected,single",
    CASES,
    ids=[c[0][:32] for c in CASES],
)
def test_real_model_detects_pii(loaded_service, text, expected, single):
    result = asyncio.run(loaded_service.moderate_content(text))
    got = set(result.categories.keys())

    missing = expected - got
    assert not missing, (
        f"{'single-token' if single else 'multi-token'} PII not detected in {text!r}: "
        f"missing {missing}; raw entity_groups="
        f"{[(s.get('entity_group'), round(float(s.get('score', 0)), 3)) for s in loaded_service.pipeline(text)]}"
    )

    if not expected:
        assert not result.is_flagged, f"benign control wrongly flagged: {text!r} -> {got}"
