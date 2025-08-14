import pytest
from unittest.mock import Mock
import sys
import os

# Add server directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from inference.pipeline.steps.language_detection import (
    LanguageDetectionStep,
    DetectionResult,
)
from inference.pipeline.base import ProcessingContext


class TestLanguageDetectionStep:
    @pytest.fixture
    def mock_container(self):
        container = Mock()
        container.get_or_none.return_value = {
            'language_detection': {
                'enabled': True,
                'backends': ['langdetect'],
                'min_confidence': 0.8,
                'min_margin': 0.2,
                'prefer_english_for_ascii': True,
                'enable_stickiness': True,
                'fallback_language': 'en',
            },
            'general': {'verbose': False},
        }
        return container

    @pytest.fixture
    def step(self, mock_container):
        s = LanguageDetectionStep(mock_container)
        s.logger = Mock()
        return s

    def test_length_fallback_defaults_to_english(self, step):
        assert step._detect_language_ensemble("").language == 'en'
        assert step._detect_language_ensemble("  ").language == 'en'
        assert step._detect_language_ensemble("a").language == 'en'

    def test_ascii_bias_prefers_english_when_low_conf(self, step):
        # Force a low-confidence Spanish result from backend on ASCII English text
        def mock_backend(_):
            return DetectionResult(language='es', confidence=0.6, method='mock')

        # Disable script short-circuiting
        original_script = step._detect_by_script
        step._detect_by_script = lambda txt: DetectionResult('unknown', 0.0, 'script_detection', {'reason': 'no_patterns_matched'})
        step.backends = [('mock', 1.0, mock_backend)]

        text = "Please help with my account and password reset"
        result = step._detect_language_ensemble(text)

        # Expect heuristic to default to English
        assert result.language == 'en'
        assert result.method in ('heuristic_ascii_bias', 'threshold_fallback', 'ensemble_voting')

        # Restore
        step._detect_by_script = original_script

    def test_sticky_previous_language_on_ambiguous(self, step):
        # Create near-tie, both under min_confidence to trigger stickiness
        def backend_en(_):
            return DetectionResult(language='en', confidence=0.62, method='mock')

        def backend_es(_):
            return DetectionResult(language='es', confidence=0.63, method='mock')

        # Disable script short-circuiting
        original_script = step._detect_by_script
        step._detect_by_script = lambda txt: DetectionResult('unknown', 0.0, 'script_detection', {'reason': 'no_patterns_matched'})
        step.backends = [('en_backend', 1.0, backend_en), ('es_backend', 1.0, backend_es)]

        text = "Como estas"
        result = step._detect_language_ensemble(text, previous_language='en')

        # Expect stickiness to choose English when below thresholds/margins
        assert result.language == 'en'
        assert result.method in ('sticky_previous', 'heuristic_ascii_bias', 'threshold_fallback')

        # Restore
        step._detect_by_script = original_script

    def test_script_detection_overrides_backends(self, step):
        # Backends would say English, but Japanese script should short-circuit
        def backend_en(_):
            return DetectionResult(language='en', confidence=0.9, method='mock')

        step.backends = [('en_backend', 1.0, backend_en)]
        text = "こんにちは, how are you?"
        result = step._detect_language_ensemble(text)
        assert result.language in ('ja', 'zh')  # Japanese script path may map to ja or zh by library
        assert result.method == 'script_detection'

    @pytest.mark.asyncio
    async def test_process_sets_detected_language_and_meta(self, step):
        context = ProcessingContext(message="This is clearly English.")
        result_context = await step.process(context)
        assert result_context.detected_language == 'en'
        assert isinstance(result_context.language_detection_meta, dict)

    def test_cleaning_urls_and_code(self, step):
        # Ensure cleaning doesn't break and still yields English under heuristics
        def mock_backend(_):
            return DetectionResult(language='es', confidence=0.6, method='mock')

        original_script = step._detect_by_script
        step._detect_by_script = lambda txt: DetectionResult('unknown', 0.0, 'script_detection', {'reason': 'no_patterns_matched'})
        step.backends = [('mock', 1.0, mock_backend)]

        text = "Please check https://example.com and `print('hello')` for details"
        result = step._detect_language_ensemble(text)
        assert result.language == 'en'

        step._detect_by_script = original_script

