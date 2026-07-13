"""
Unit tests for the privacy filter (PII) moderation service.

Tests cover:
- Configuration parsing (threshold, flag_categories, model default)
- Span-to-result mapping (thresholds, category filtering, unknown labels)
- moderate_content and moderate_batch with a mocked pipeline
- Fail-open behavior on pipeline errors and failed initialization

The transformers pipeline is mocked throughout so no model is downloaded.
"""

import pytest
import sys
import os
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, MagicMock

# Add the server directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from ai_services.implementations.moderation.privacy_filter_moderation_service import (
    PrivacyFilterModerationService,
    PRIVACY_FILTER_CATEGORIES,
    DEFAULT_MODEL,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def basic_config():
    """Basic configuration for testing."""
    return {
        'moderations': {
            'privacy_filter': {
                'device': 'cpu',
                'threshold': 0.5,
            }
        }
    }


def make_service(config):
    """Create a service instance with a mocked, pre-initialized pipeline."""
    service = PrivacyFilterModerationService(config)
    service.initialized = True
    service.pipeline = MagicMock()
    service.executor = ThreadPoolExecutor(max_workers=1)
    return service


@pytest.fixture
def service(basic_config):
    return make_service(basic_config)


def span(label, score, word="x"):
    """Build a pipeline output span."""
    return {'entity_group': label, 'score': score, 'word': word}


# =============================================================================
# Configuration parsing
# =============================================================================

class TestConfiguration:

    def test_model_defaults_to_privacy_filter(self, basic_config):
        service = PrivacyFilterModerationService(basic_config)
        assert service.model == DEFAULT_MODEL

    def test_model_override(self, basic_config):
        basic_config['moderations']['privacy_filter']['model'] = 'my-org/my-finetune'
        service = PrivacyFilterModerationService(basic_config)
        assert service.model == 'my-org/my-finetune'

    def test_default_threshold_and_categories(self):
        service = PrivacyFilterModerationService({'moderations': {'privacy_filter': {'device': 'cpu'}}})
        assert service.threshold == 0.5
        assert service.flag_categories == set(PRIVACY_FILTER_CATEGORIES)

    def test_custom_flag_categories(self, basic_config):
        basic_config['moderations']['privacy_filter']['flag_categories'] = ['secret', 'account_number']
        service = PrivacyFilterModerationService(basic_config)
        assert service.flag_categories == {'secret', 'account_number'}

    def test_unknown_flag_categories_ignored(self, basic_config):
        basic_config['moderations']['privacy_filter']['flag_categories'] = ['secret', 'not_a_category']
        service = PrivacyFilterModerationService(basic_config)
        assert service.flag_categories == {'secret'}


# =============================================================================
# Span-to-result mapping
# =============================================================================

class TestSpansToResult:

    def test_no_spans_is_safe(self, service):
        result = service._spans_to_result([])
        assert result.is_flagged is False
        assert result.categories == {}
        assert result.provider == 'privacy_filter'

    def test_span_above_threshold_flags(self, service):
        result = service._spans_to_result([span('private_email', 0.99)])
        assert result.is_flagged is True
        assert result.categories == {'pii.private_email': 0.99}

    def test_span_below_threshold_reported_not_flagged(self, service):
        result = service._spans_to_result([span('private_person', 0.3)])
        assert result.is_flagged is False
        assert result.categories == {'pii.private_person': 0.3}

    def test_unflagged_category_reported_not_flagged(self, basic_config):
        basic_config['moderations']['privacy_filter']['flag_categories'] = ['secret']
        service = make_service(basic_config)
        result = service._spans_to_result([span('private_date', 0.95)])
        assert result.is_flagged is False
        assert result.categories == {'pii.private_date': 0.95}

    def test_unknown_entity_group_ignored(self, service):
        result = service._spans_to_result([span('organization', 0.99)])
        assert result.is_flagged is False
        assert result.categories == {}

    def test_repeated_category_keeps_max_score(self, service):
        result = service._spans_to_result([
            span('private_phone', 0.6),
            span('private_phone', 0.9),
            span('private_phone', 0.7),
        ])
        assert result.categories == {'pii.private_phone': 0.9}

    def test_multiple_categories(self, service):
        result = service._spans_to_result([
            span('private_person', 0.99),
            span('private_email', 0.98),
        ])
        assert result.is_flagged is True
        assert set(result.categories) == {'pii.private_person', 'pii.private_email'}


# =============================================================================
# moderate_content
# =============================================================================

class TestModerateContent:

    @pytest.mark.asyncio
    async def test_flags_pii(self, service):
        service.pipeline.return_value = [span('private_email', 0.999, 'a@b.com')]
        result = await service.moderate_content("My email is a@b.com")
        assert result.is_flagged is True
        assert result.categories == {'pii.private_email': 0.999}
        service.pipeline.assert_called_once_with("My email is a@b.com")

    @pytest.mark.asyncio
    async def test_clean_content_passes(self, service):
        service.pipeline.return_value = []
        result = await service.moderate_content("The weather is nice today")
        assert result.is_flagged is False
        assert result.error is None

    @pytest.mark.asyncio
    async def test_pipeline_error_fails_open(self, service):
        service.pipeline.side_effect = RuntimeError("model exploded")
        result = await service.moderate_content("some text")
        assert result.is_flagged is False
        assert 'model exploded' in result.error

    @pytest.mark.asyncio
    async def test_failed_initialization_fails_open(self, basic_config):
        service = PrivacyFilterModerationService(basic_config)
        service.initialized = False
        service.initialize = AsyncMock(return_value=False)
        result = await service.moderate_content("some text")
        assert result.is_flagged is False
        assert 'initialization failed' in result.error


# =============================================================================
# moderate_batch
# =============================================================================

class TestModerateBatch:

    @pytest.mark.asyncio
    async def test_empty_batch(self, service):
        assert await service.moderate_batch([]) == []

    @pytest.mark.asyncio
    async def test_batch_results_align_with_inputs(self, service):
        service.pipeline.return_value = [
            [span('private_person', 0.99)],
            [],
        ]
        results = await service.moderate_batch(["Alice Smith", "hello world"])
        assert len(results) == 2
        assert results[0].is_flagged is True
        assert results[1].is_flagged is False

    @pytest.mark.asyncio
    async def test_single_item_batch_span_list(self, service):
        # For a single input the pipeline returns one span list, not a list of lists
        service.pipeline.return_value = [span('secret', 0.97)]
        results = await service.moderate_batch(["api key: sk-123"])
        assert len(results) == 1
        assert results[0].is_flagged is True

    @pytest.mark.asyncio
    async def test_batch_error_fails_open_per_item(self, service):
        service.pipeline.side_effect = RuntimeError("boom")
        results = await service.moderate_batch(["a", "b", "c"])
        assert len(results) == 3
        assert all(r.is_flagged is False and r.error for r in results)
