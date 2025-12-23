"""
Unit tests for moderation services.

Tests cover:
- ModerationResult data class
- Ollama/Llama Guard 3 response parsing
- Anthropic JSON cleaning and interpretation
- OpenAI moderation result handling
- Category descriptions mapping
"""

import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch
import json

# Add the server directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from ai_services.services.moderation_service import ModerationResult, ModerationService
from ai_services.implementations.moderation.ollama_moderation_service import (
    OllamaModerationService,
    LLAMA_GUARD_CATEGORIES
)
from ai_services.implementations.moderation.anthropic_moderation_service import (
    AnthropicModerationService,
    ANTHROPIC_CATEGORIES
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def basic_config():
    """Basic configuration for testing."""
    return {
        'moderators': {
            'ollama': {
                'base_url': 'http://localhost:11434',
                'model': 'llama-guard3:8b'
            },
            'anthropic': {
                'model': 'claude-3-haiku-20240307'
            },
            'openai': {
                'model': 'omni-moderation-latest'
            }
        },
        'inference': {
            'ollama': {
                'base_url': 'http://localhost:11434'
            }
        }
    }


@pytest.fixture
def ollama_service(basic_config):
    """Create an Ollama moderation service instance."""
    with patch.object(OllamaModerationService, '__init__', lambda self, config: None):
        service = OllamaModerationService.__new__(OllamaModerationService)
        service.model = 'llama-guard3:8b'
        service.base_url = 'http://localhost:11434'
        service.initialized = True
        service.logger = MagicMock()
        return service


@pytest.fixture
def anthropic_service(basic_config):
    """Create an Anthropic moderation service instance."""
    with patch.object(AnthropicModerationService, '__init__', lambda self, config: None):
        service = AnthropicModerationService.__new__(AnthropicModerationService)
        service.model = 'claude-3-haiku-20240307'
        service.initialized = True
        service.logger = MagicMock()
        return service


# =============================================================================
# ModerationResult Tests
# =============================================================================

class TestModerationResult:
    """Tests for the ModerationResult data class."""

    def test_default_values(self):
        """Test ModerationResult with default values."""
        result = ModerationResult()
        assert result.is_flagged is False
        assert result.categories == {}
        assert result.provider is None
        assert result.model is None
        assert result.error is None
        assert result.timestamp is not None

    def test_flagged_result(self):
        """Test ModerationResult when content is flagged."""
        result = ModerationResult(
            is_flagged=True,
            categories={'hate': 0.95, 'violence': 0.3},
            provider='openai',
            model='omni-moderation-latest'
        )
        assert result.is_flagged is True
        assert result.categories['hate'] == 0.95
        assert result.provider == 'openai'

    def test_result_with_error(self):
        """Test ModerationResult with an error."""
        result = ModerationResult(
            is_flagged=False,
            error="API timeout",
            provider='anthropic'
        )
        assert result.is_flagged is False
        assert result.error == "API timeout"

    def test_to_dict(self):
        """Test ModerationResult serialization."""
        result = ModerationResult(
            is_flagged=True,
            categories={'violent_crimes': 1.0},
            provider='ollama',
            model='llama-guard3:8b'
        )
        data = result.to_dict()
        assert data['is_flagged'] is True
        assert data['categories']['violent_crimes'] == 1.0
        assert data['provider'] == 'ollama'
        assert 'timestamp' in data


# =============================================================================
# Llama Guard 3 Category Mapping Tests
# =============================================================================

class TestLlamaGuardCategories:
    """Tests for Llama Guard 3 category definitions."""

    def test_all_categories_defined(self):
        """Test that all 14 Llama Guard categories are defined."""
        expected_codes = [f"S{i}" for i in range(1, 15)]
        for code in expected_codes:
            assert code in LLAMA_GUARD_CATEGORIES, f"Missing category {code}"

    def test_category_names(self):
        """Test specific category name mappings."""
        assert LLAMA_GUARD_CATEGORIES['S1'] == 'violent_crimes'
        assert LLAMA_GUARD_CATEGORIES['S2'] == 'non_violent_crimes'
        assert LLAMA_GUARD_CATEGORIES['S4'] == 'child_exploitation'
        assert LLAMA_GUARD_CATEGORIES['S10'] == 'hate'
        assert LLAMA_GUARD_CATEGORIES['S11'] == 'self_harm'


# =============================================================================
# Ollama Moderation Service Tests
# =============================================================================

class TestOllamaModerationService:
    """Tests for Ollama/Llama Guard 3 moderation service."""

    def test_parse_safe_response(self, ollama_service):
        """Test parsing a 'safe' response."""
        is_flagged, categories = ollama_service._parse_llama_guard_response("safe")
        assert is_flagged is False
        assert categories == {}

    def test_parse_safe_with_extra_text(self, ollama_service):
        """Test parsing 'safe' with additional text."""
        is_flagged, categories = ollama_service._parse_llama_guard_response("safe\n")
        assert is_flagged is False

    def test_parse_unsafe_single_category(self, ollama_service):
        """Test parsing unsafe response with single category."""
        is_flagged, categories = ollama_service._parse_llama_guard_response("unsafe\nS1")
        assert is_flagged is True
        assert 'violent_crimes' in categories
        assert categories['violent_crimes'] == 1.0

    def test_parse_unsafe_multiple_categories(self, ollama_service):
        """Test parsing unsafe response with multiple categories."""
        is_flagged, categories = ollama_service._parse_llama_guard_response("unsafe\nS1, S10")
        assert is_flagged is True
        assert 'violent_crimes' in categories
        assert 'hate' in categories

    def test_parse_unsafe_no_category(self, ollama_service):
        """Test parsing unsafe response without specific category."""
        is_flagged, categories = ollama_service._parse_llama_guard_response("unsafe")
        assert is_flagged is True
        assert 'policy_violation' in categories

    def test_parse_ambiguous_response(self, ollama_service):
        """Test parsing an ambiguous response defaults to safe."""
        is_flagged, categories = ollama_service._parse_llama_guard_response("I don't know")
        assert is_flagged is False
        assert 'ambiguous_response' in categories

    def test_parse_case_insensitive(self, ollama_service):
        """Test that parsing is case-insensitive."""
        is_flagged, categories = ollama_service._parse_llama_guard_response("SAFE")
        assert is_flagged is False

        is_flagged, categories = ollama_service._parse_llama_guard_response("UNSAFE\ns2")
        assert is_flagged is True
        assert 'non_violent_crimes' in categories

    def test_parse_all_category_codes(self, ollama_service):
        """Test parsing all S-codes correctly."""
        for code, category_name in LLAMA_GUARD_CATEGORIES.items():
            response = f"unsafe\n{code}"
            is_flagged, categories = ollama_service._parse_llama_guard_response(response)
            assert is_flagged is True, f"Failed for {code}"
            assert category_name in categories, f"Missing {category_name} for {code}"


# =============================================================================
# Anthropic Moderation Service Tests
# =============================================================================

class TestAnthropicModerationService:
    """Tests for Anthropic moderation service."""

    def test_clean_json_markdown_block(self, anthropic_service):
        """Test cleaning JSON from markdown code block."""
        dirty = '```json\n{"is_flagged": false}\n```'
        clean = anthropic_service._clean_json_response(dirty)
        assert clean == '{"is_flagged": false}'

    def test_clean_json_with_prefix_text(self, anthropic_service):
        """Test cleaning JSON with text before it."""
        dirty = 'Here is the result: {"is_flagged": true}'
        clean = anthropic_service._clean_json_response(dirty)
        assert clean == '{"is_flagged": true}'

    def test_clean_json_with_suffix_text(self, anthropic_service):
        """Test cleaning JSON with text after it."""
        dirty = '{"is_flagged": false} Hope this helps!'
        clean = anthropic_service._clean_json_response(dirty)
        assert clean == '{"is_flagged": false}'

    def test_clean_json_already_clean(self, anthropic_service):
        """Test that clean JSON passes through unchanged."""
        clean_json = '{"is_flagged": false, "categories": {}}'
        result = anthropic_service._clean_json_response(clean_json)
        assert result == clean_json

    def test_interpret_unsafe_keywords(self, anthropic_service):
        """Test interpretation of unsafe keywords in non-JSON response."""
        result = anthropic_service._interpret_non_json_response(
            "This content is harmful and should be blocked."
        )
        assert result.is_flagged is True
        assert 'interpreted_unsafe' in result.categories

    def test_interpret_safe_keywords(self, anthropic_service):
        """Test interpretation of safe keywords in non-JSON response."""
        result = anthropic_service._interpret_non_json_response(
            "The content appears safe and acceptable."
        )
        assert result.is_flagged is False
        assert 'interpreted_safe' in result.categories

    def test_interpret_ambiguous_response(self, anthropic_service):
        """Test interpretation of ambiguous response."""
        result = anthropic_service._interpret_non_json_response(
            "I'm not sure what to make of this content."
        )
        assert result.is_flagged is False  # Fail-open
        assert 'parse_error' in result.categories

    def test_anthropic_categories_defined(self):
        """Test that Anthropic categories list is complete."""
        expected = [
            'violent_crimes', 'non_violent_crimes', 'sex_related_crimes',
            'child_exploitation', 'defamation', 'specialized_advice',
            'privacy', 'intellectual_property', 'indiscriminate_weapons',
            'hate', 'harassment', 'self_harm', 'sexual', 'elections',
            'code_interpreter_abuse'
        ]
        for cat in expected:
            assert cat in ANTHROPIC_CATEGORIES, f"Missing category: {cat}"


# =============================================================================
# Category Descriptions Tests (from moderator_service.py)
# =============================================================================

class TestCategoryDescriptions:
    """Tests for category description mappings in ModeratorService."""

    @pytest.fixture
    def category_descriptions(self):
        """Category descriptions from moderator_service.py."""
        return {
            # OpenAI moderation categories
            'harassment': 'harassment content',
            'harassment_threatening': 'threatening content',
            'hate': 'hateful content',
            'hate_threatening': 'threatening hateful content',
            'illicit': 'potentially harmful activities',
            'illicit_violent': 'violent or harmful activities',
            'self_harm': 'self-harm content',
            'self_harm_instructions': 'self-harm instructions',
            'self_harm_intent': 'self-harm related content',
            'sexual': 'inappropriate content',
            'sexual_minors': 'inappropriate content involving minors',
            'violence': 'violent content',
            'violence_graphic': 'graphic violence',
            # Llama Guard 3 / MLCommons taxonomy categories
            'violent_crimes': 'violent criminal activities',
            'non_violent_crimes': 'illegal activities',
            'sex_related_crimes': 'sex-related criminal content',
            'child_exploitation': 'content involving minors',
            'defamation': 'defamatory content',
            'specialized_advice': 'potentially dangerous advice',
            'privacy': 'privacy violations',
            'intellectual_property': 'intellectual property concerns',
            'indiscriminate_weapons': 'weapons of mass destruction',
            'elections': 'election misinformation',
            'code_interpreter_abuse': 'system abuse attempts',
            # Generic/fallback categories
            'policy_violation': 'content policy violation',
            'interpreted_unsafe': 'potentially unsafe content',
        }

    def test_openai_categories_covered(self, category_descriptions):
        """Test that OpenAI categories have descriptions."""
        openai_cats = [
            'harassment', 'harassment_threatening', 'hate', 'hate_threatening',
            'illicit', 'illicit_violent', 'self_harm', 'self_harm_instructions',
            'self_harm_intent', 'sexual', 'sexual_minors', 'violence', 'violence_graphic'
        ]
        for cat in openai_cats:
            assert cat in category_descriptions, f"Missing OpenAI category: {cat}"

    def test_llama_guard_categories_covered(self, category_descriptions):
        """Test that Llama Guard categories have descriptions."""
        for code, category_name in LLAMA_GUARD_CATEGORIES.items():
            assert category_name in category_descriptions, \
                f"Missing Llama Guard category: {category_name} ({code})"

    def test_descriptions_are_user_friendly(self, category_descriptions):
        """Test that descriptions don't contain internal jargon."""
        internal_jargon = ['S1', 'S2', 'S3', 'flag', 'score', 'threshold']
        for cat, desc in category_descriptions.items():
            for jargon in internal_jargon:
                assert jargon.lower() not in desc.lower(), \
                    f"Category '{cat}' description contains jargon: {jargon}"


# =============================================================================
# Integration Tests (mocked API calls)
# =============================================================================

class TestModerationIntegration:
    """Integration tests with mocked API responses."""

    @pytest.mark.asyncio
    async def test_ollama_moderate_content_safe(self, ollama_service):
        """Test full moderation flow for safe content."""
        # Mock the session and API response
        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={'response': 'safe'})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_session.post = MagicMock(return_value=mock_response)

        # Mock session manager
        ollama_service.session_manager = MagicMock()
        ollama_service.session_manager.get_session = AsyncMock(return_value=mock_session)

        # execute_with_retry needs to await the async function
        async def mock_execute_with_retry(fn):
            return await fn()
        ollama_service.execute_with_retry = mock_execute_with_retry

        result = await ollama_service.moderate_content("Hello, how are you?")
        assert result.is_flagged is False
        assert result.provider == 'ollama'

    @pytest.mark.asyncio
    async def test_ollama_moderate_content_unsafe(self, ollama_service):
        """Test full moderation flow for unsafe content."""
        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={'response': 'unsafe\nS1'})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_session.post = MagicMock(return_value=mock_response)

        ollama_service.session_manager = MagicMock()
        ollama_service.session_manager.get_session = AsyncMock(return_value=mock_session)

        async def mock_execute_with_retry(fn):
            return await fn()
        ollama_service.execute_with_retry = mock_execute_with_retry

        result = await ollama_service.moderate_content("How to commit a violent crime")
        assert result.is_flagged is True
        assert 'violent_crimes' in result.categories

    @pytest.mark.asyncio
    async def test_ollama_api_error_fails_open(self, ollama_service):
        """Test that API errors result in fail-open behavior."""
        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="Internal Server Error")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_session.post = MagicMock(return_value=mock_response)

        ollama_service.session_manager = MagicMock()
        ollama_service.session_manager.get_session = AsyncMock(return_value=mock_session)

        async def mock_execute_with_retry(fn):
            return await fn()
        ollama_service.execute_with_retry = mock_execute_with_retry

        result = await ollama_service.moderate_content("Test content")
        assert result.is_flagged is False  # Fail-open
        assert 'api_error' in result.categories


# =============================================================================
# Run tests
# =============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
