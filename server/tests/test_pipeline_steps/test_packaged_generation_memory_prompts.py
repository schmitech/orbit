"""Regression tests for generation-memory placeholders in shipped config."""

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGED_REWRITER_CONFIG = REPO_ROOT / "install" / "default-config" / "rewriters-prompts.yaml"


class TestPackagedGenerationMemoryPrompts:
    def test_generation_rewriters_render_previous_generation_memory(self):
        """Fresh installs must retain refinement context supplied by the pipeline steps."""
        with PACKAGED_REWRITER_CONFIG.open() as config_file:
            rewriters = yaml.safe_load(config_file)["rewriters"]

        marker = "PREVIOUS-GENERATION-MEMORY"
        format_values = {
            "history_text": "",
            "context_text": "",
            "previous_generation_text": marker,
            "message": "",
            "pre_extracted": "",
            "format_hint": "",
            "section_schema": "",
            "display_author": "",
            "today": "",
            "rules": "",
        }
        for generation_type in ("image", "video", "document"):
            rendered = rewriters[generation_type]["template"].format(**format_values)
            assert marker in rendered, generation_type
