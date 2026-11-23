"""The install wizard must write a Gemini model the Gemini API still serves.

Google shut gemini-2.0-flash down on the Gemini API on 2026-06-01:
https://ai.google.dev/gemini-api/docs/deprecations
"""

import importlib.util
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
SHUT_DOWN_GEMINI = {"gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-flash", "gemini-1.5-pro"}


def _wizard_providers():
    spec = importlib.util.spec_from_file_location("orbit_install_wizard", REPO_ROOT / "install" / "wizard.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {provider["key"]: provider for provider in module.PROVIDERS}


def test_wizard_gemini_model_matches_the_shipped_gemini_config():
    with (REPO_ROOT / "config" / "inference.yaml").open(encoding="utf-8") as fh:
        shipped = yaml.safe_load(fh)["inference"]["gemini"]["model"]

    model = _wizard_providers()["gemini"]["model"]

    assert model not in SHUT_DOWN_GEMINI
    assert model == shipped
