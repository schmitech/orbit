"""
Phase 4: mixed-language detection from spans, not backend disagreement.

Segmentation tests are pure. Detection tests run the real backends and skip
if none is installed.
"""

import pytest
from inference.pipeline.base import ProcessingContext
from inference.pipeline.steps.language_detection import (
    LANGDETECT_AVAILABLE,
    LANGID_AVAILABLE,
    PYCLD2_AVAILABLE,
    LanguageDetectionStep,
    span_segments,
)


def _pieces(text):
    return [(text[a:b], script) for a, b, script in span_segments(text)]


# ---------------------------------------------------------------------------
# Segmentation
# ---------------------------------------------------------------------------

def test_clause_punctuation_separates_spans():
    assert _pieces("I need the report, pero rápido por favor") == [
        ("I need the report", "Latin"), ("pero rápido por favor", "Latin"),
    ]


def test_script_change_separates_spans():
    assert _pieces("明日の meeting の資料を送ってください") == [
        ("明日の", "Han"), ("meeting", "Latin"), ("の資料を送ってください", "Han"),
    ]


def test_code_urls_and_email_are_boundaries_not_text():
    text = "run `pip install foo` then see https://example.com/a?b=1 or mail ops@example.com, merci"
    pieces = [piece for piece, _ in _pieces(text)]
    assert pieces == ["run", "then see", "or mail", "merci"]


def test_offsets_are_code_points_around_emoji_and_supplementary_characters():
    text = "😀 Hola amigo 🇪🇸, 𝒳 see you tomorrow"
    assert [piece for piece, _ in _pieces(text)] == ["Hola amigo", "see you tomorrow"]  # 𝒳 is Common script


def test_combining_marks_stay_inside_the_span():
    text = "café, thank you"  # decomposed "café"
    assert _pieces(text)[0] == ("café", "Latin")


def test_single_clause_is_one_segment():
    assert len(span_segments("The café downstairs has great croissants")) == 1


# ---------------------------------------------------------------------------
# Detection (real backends)
# ---------------------------------------------------------------------------

needs_backends = pytest.mark.skipif(
    not (LANGDETECT_AVAILABLE and LANGID_AVAILABLE and PYCLD2_AVAILABLE),
    reason="span detection tests need all three detection backends",
)


class _Container:
    def __init__(self):
        self._config = {'language_detection': {
            'enabled': True,
            'mixed_language': {'min_span_letters': 5, 'min_span_coverage': 0.1},
        }, 'general': {'verbose': False}}

    def get(self, key):
        return self._config if key == 'config' else None

    def get_or_none(self, key):
        return self.get(key)

    def has(self, key):
        return key == 'config'


async def _meta(text):
    context = ProcessingContext(message=text, adapter_name='qa')
    await LanguageDetectionStep(_Container()).process(context)
    return context.detected_language, context.language_detection_meta


@needs_backends
@pytest.mark.asyncio
@pytest.mark.parametrize("text,primary,secondary", [
    ("I need the full sales report for last quarter, pero rápido por favor", "en", ["es"]),
    ("Preciso do relatório final até sexta-feira, please don't forget", "pt", ["en"]),
    ("ممكن ترسل لي التقرير الأسبوعي قبل الاجتماع؟ thanks", "ar", ["en"]),
])
async def test_two_language_prompt_reports_the_secondary_span(text, primary, secondary):
    language, meta = await _meta(text)
    assert language == primary
    assert meta['mixed_language_detected'] is True
    assert meta['secondary_languages'] == secondary
    span = next(s for s in meta['spans'] if s['language'] == secondary[0])
    assert text[span['start']:span['end']] in text


@needs_backends
@pytest.mark.asyncio
async def test_three_language_prompt():
    text = ("Necesito el informe financiero completo antes del viernes, "
            "please send the final numbers today, "
            "und bitte vergiss die Tabellen nicht")
    language, meta = await _meta(text)
    assert language in {'es', 'en', 'de'}
    assert {language, *meta['secondary_languages']} == {'es', 'en', 'de'}


@needs_backends
@pytest.mark.asyncio
@pytest.mark.parametrize("text", [
    "The café downstairs has great croissants",                 # borrowed word
    "Das Meeting wurde wegen eines Bugs im Release verschoben",  # borrowed words
    "How far is Montréal from Québec City?",                     # foreign names
    "Can you fix this: `for (let i = 0; i < n; i++) { total += prix[i]; }` please",  # code
    "Where is my order? I placed it on Monday, and it still has not shipped.",  # several clauses
])
async def test_monolingual_prompt_is_not_mixed(text):
    _, meta = await _meta(text)
    assert meta['mixed_language_detected'] is False, meta['spans']


@needs_backends
@pytest.mark.asyncio
async def test_capitalized_name_run_is_not_a_span():
    _, meta = await _meta("東京タワーの近くにある Blue Bottle Coffee に行きたいです")
    assert meta['mixed_language_detected'] is False


@needs_backends
@pytest.mark.asyncio
async def test_no_spans_without_an_accepted_primary_language():
    _, meta = await _meta("здравей, как си?")
    assert meta['spans'] == [] and meta['mixed_language_detected'] is False


@pytest.mark.asyncio
async def test_spans_merge_only_when_consecutive():
    """A skipped segment between two same-language spans keeps them apart."""
    from unittest.mock import AsyncMock

    from inference.pipeline.steps.language_detection import DetectionResult, abstain

    step = LanguageDetectionStep(_Container())
    zh = DetectionResult('zh', 0.95, 'calibrated_ensemble', accepted=True)
    step._detect_language_ensemble_async = AsyncMock(side_effect=[zh, abstain('below_threshold'), zh])
    text = "请帮我检查一下这个 pull request 有没有问题呢"
    spans = await step._detect_spans(text, zh)
    assert [text[s['start']:s['end']] for s in spans] == ["请帮我检查一下这个", "有没有问题呢"]


@pytest.mark.asyncio
async def test_spans_do_not_merge_across_masked_content():
    """A URL between two same-language segments must not end up inside a span."""
    from unittest.mock import AsyncMock

    from inference.pipeline.steps.language_detection import DetectionResult

    step = LanguageDetectionStep(_Container())
    zh = DetectionResult('zh', 0.95, 'calibrated_ensemble', accepted=True)
    en = DetectionResult('en', 0.95, 'calibrated_ensemble', accepted=True)
    step._detect_language_ensemble_async = AsyncMock(side_effect=[zh, en, en, zh])
    text = "请帮我检查一下这个 please review this https://example.com/pr/42 carefully today 有没有问题呢"
    spans = await step._detect_spans(text, zh)
    assert [text[s['start']:s['end']] for s in spans] == [
        "请帮我检查一下这个", "please review this", "carefully today", "有没有问题呢",
    ]
    assert not any("https" in text[s['start']:s['end']] for s in spans)


def test_span_coverage_defaults_to_the_benchmarked_value():
    """Configs written before Phase 4 have no mixed_language block."""
    class Bare(_Container):
        def __init__(self):
            self._config = {'language_detection': {'enabled': True}, 'general': {'verbose': False}}

    step = LanguageDetectionStep(Bare())
    assert (step.span_min_letters, step.span_min_coverage) == (5, 0.1)
