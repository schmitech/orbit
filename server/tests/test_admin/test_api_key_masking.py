"""
Unit tests for API key masking.

Covers:
  - utils.text_utils.mask_api_key() directly (all parameter combinations)
  - The exact call pattern used by admin_routes.py (show_last=True, prefix="***"),
    verifying it reproduces the legacy inline `f"***{key[-4:]}" if ... else "***"`
    expressions that were consolidated into mask_api_key.
"""

import pytest

from utils.text_utils import mask_api_key


# ---------------------------------------------------------------------------
# Default behavior (used by services/api_key_service.py logging calls)
# ---------------------------------------------------------------------------

class TestMaskApiKeyDefaults:

    def test_none_key_returns_none_string(self):
        assert mask_api_key(None) == "None"

    def test_empty_key_returns_none_string(self):
        assert mask_api_key("") == "None"

    def test_short_key_returns_four_asterisks(self):
        assert mask_api_key("abc") == "****"

    def test_key_length_equal_to_num_chars_returns_four_asterisks(self):
        assert mask_api_key("abcd") == "****"

    def test_show_first_by_default(self):
        assert mask_api_key("sk-1234567890") == "sk-1..."

    def test_show_last_when_requested(self):
        assert mask_api_key("sk-1234567890", show_last=True) == "...7890"

    def test_custom_num_chars(self):
        assert mask_api_key("sk-1234567890", num_chars=6) == "sk-123..."

    def test_custom_num_chars_show_last(self):
        assert mask_api_key("sk-1234567890", show_last=True, num_chars=6) == "...567890"


# ---------------------------------------------------------------------------
# admin_routes.py usage: show_last=True, prefix="***"
#
# These reproduce the exact legacy expressions that were consolidated, e.g.:
#   f"***{api_key[-4:]}" if len(api_key) >= 4 else "***"
# ---------------------------------------------------------------------------

class TestMaskApiKeyAdminRoutesPrefix:

    def test_normal_key_matches_legacy_format(self):
        api_key = "sk-abcdEFGH1234"
        legacy = f"***{api_key[-4:]}" if len(api_key) >= 4 else "***"
        assert mask_api_key(api_key, show_last=True, prefix="***") == legacy
        assert mask_api_key(api_key, show_last=True, prefix="***") == "***1234"

    def test_missing_key_falls_back_to_prefix_only(self):
        assert mask_api_key(None, show_last=True, prefix="***") == "***"
        assert mask_api_key("", show_last=True, prefix="***") == "***"

    def test_short_key_falls_back_to_prefix_only(self):
        # Legacy off-by-one: `len(api_key) >= 4` treated a 4-char key as
        # "long enough" and leaked the whole key after the prefix.
        # mask_api_key intentionally fixes this: len <= num_chars falls back.
        assert mask_api_key("abcd", show_last=True, prefix="***") == "***"
        assert mask_api_key("abc", show_last=True, prefix="***") == "***"

    def test_never_leaks_full_key_for_short_keys(self):
        for key in ["a", "ab", "abc", "abcd"]:
            masked = mask_api_key(key, show_last=True, prefix="***")
            assert key not in masked

    @pytest.mark.parametrize(
        "api_key,expected",
        [
            ("1234567890abcdef", "***cdef"),
            ("short5", "***ort5"),
            ("exactly8", "***tly8"),
        ],
    )
    def test_various_keys(self, api_key, expected):
        assert mask_api_key(api_key, show_last=True, prefix="***") == expected

    def test_masked_output_never_contains_middle_of_key(self):
        api_key = "sk-super-secret-middle-section-9999"
        masked = mask_api_key(api_key, show_last=True, prefix="***")
        assert "super-secret-middle-section" not in masked
        assert masked == "***9999"


# ---------------------------------------------------------------------------
# Ambiguous identifiers (record _id OR raw api_key) as logged by
# admin_routes.py for rename/update/deactivate/delete/status endpoints.
# Masking must be safe to apply even when the identifier turns out to be a
# raw API key that a caller passed in place of the record id.
# ---------------------------------------------------------------------------

class TestMaskApiKeyForAmbiguousIdentifiers:

    def test_mongo_style_object_id_is_masked_without_error(self):
        object_id = "507f1f77bcf86cd799439011"
        masked = mask_api_key(object_id, show_last=True, prefix="***")
        assert masked == "***9011"
        assert object_id not in masked

    def test_raw_api_key_passed_as_identifier_is_masked(self):
        raw_key = "sk-live-abcdefghijklmnopqrstuvwxyz"
        masked = mask_api_key(raw_key, show_last=True, prefix="***")
        assert raw_key not in masked
        assert masked == "***wxyz"
