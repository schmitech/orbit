"""
Phase 3 contract tests: backend adapters keep full candidate distributions,
and calibrated pooling cannot turn weak agreement into certainty.

Backend outputs are fixed here, so these tests do not depend on the native
detection libraries being installed.
"""

import itertools
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from inference.pipeline.base import ProcessingContext
from inference.pipeline.prompt_builder import PromptInstructionBuilder
from inference.pipeline.steps import language_detection as ld
from inference.pipeline.steps.language_detection import (
    BackendResult,
    ConversationPrior,
    LanguageDetectionStep,
    candidate_scores,
    load_calibration,
    pool_backend_distributions,
)


class _Container:
    def __init__(self):
        self._config = {'language_detection': {'enabled': True}, 'general': {'verbose': False}}

    def get(self, key):
        return self._config if key == 'config' else None

    def get_or_none(self, key):
        return self.get(key)

    def has(self, key):
        return key == 'config'


@pytest.fixture
def step():
    return LanguageDetectionStep(_Container())


def _backends(step, *results):
    """Make the step's backends return fixed results, in order."""
    step.backends = [(r.backend, MagicMock()) for r in results]
    step._run_backend_with_timeout = AsyncMock(side_effect=list(results))
    return step


# ---------------------------------------------------------------------------
# Backend adapters
# ---------------------------------------------------------------------------

def test_langdetect_keeps_every_candidate(step, monkeypatch):
    monkeypatch.setattr(ld, 'LANGDETECT_AVAILABLE', True)
    monkeypatch.setattr(ld, 'detect_langs', lambda text: [
        SimpleNamespace(lang='zh-cn', prob=0.6), SimpleNamespace(lang='ja', prob=0.3),
        SimpleNamespace(lang='zh-tw', prob=0.1),
    ])
    result = step._detect_langdetect('text')
    assert result.backend == 'langdetect' and result.scale == 'probability'
    assert result.candidates == pytest.approx({'zh': 0.7, 'ja': 0.3})  # codes normalized, then merged


def test_langid_keeps_top_k_and_raw_log_probs(step, monkeypatch):
    codes = ['en', 'iw', 'fr', 'de', 'es', 'it', 'nl', 'pt', 'sv', 'da', 'no', 'fi', 'pl', 'cs', 'tr']
    ranked = [(code, -10.0 - i) for i, code in enumerate(codes)]  # sorted best-first, like langid
    monkeypatch.setattr(ld, 'LANGID_AVAILABLE', True)
    monkeypatch.setattr(ld, 'langid', SimpleNamespace(rank=lambda text: ranked), raising=False)
    result = step._detect_langid('text')
    top_k = step.calibration.langid_top_k
    assert result.scale == 'softmax_top_k'  # softmaxed over the top k only, not a global probability
    assert len(result.raw['log_probs']) == top_k
    assert result.raw['log_probs'][1] == ('iw', -11.0)
    assert 'he' in result.candidates and 'iw' not in result.candidates
    assert sum(result.candidates.values()) == pytest.approx(1.0)
    assert result.language == 'en'


@pytest.mark.parametrize('reliable', [True, False])
def test_pycld2_keeps_details_and_reliability(step, monkeypatch, reliable):
    details = (('HEBREW', 'iw', 61, 900.0), ('YIDDISH', 'yi', 38, 700.0), ('Unknown', 'un', 0, 0.0))
    monkeypatch.setattr(ld, 'PYCLD2_AVAILABLE', True)
    monkeypatch.setattr(ld, 'cld2', SimpleNamespace(detect=lambda text: (reliable, 120, details)), raising=False)
    result = step._detect_pycld2('text')
    assert result.scale == 'text_percent'
    assert result.reliable is reliable
    assert result.candidates == pytest.approx({'he': 0.61, 'yi': 0.38})
    assert result.raw == {'text_bytes': 120, 'details': [('iw', 61, 900.0), ('yi', 38, 700.0)]}


def test_backend_answering_only_unknown_has_no_candidates():
    result = BackendResult('pycld2', candidate_scores([('un', 0.99)]), 'text_percent')
    assert result.abstained and result.language == 'unknown'


# ---------------------------------------------------------------------------
# Pooling
# ---------------------------------------------------------------------------

ALL_BACKENDS = ('langdetect', 'langid', 'pycld2')


def _full_pool():
    return load_calibration().for_backends(ALL_BACKENDS)


def _pool(*candidate_lists):
    results = [BackendResult(b, c, 'probability') for b, c in zip(ALL_BACKENDS, candidate_lists)]
    return pool_backend_distributions(results, _full_pool(), load_calibration().universe_size)


def test_unanimous_but_weak_backends_do_not_become_certain():
    weak = {'ru': 0.4, 'uk': 0.3, 'bg': 0.3}
    probabilities, _ = _pool(weak, weak, weak)
    assert max(probabilities, key=probabilities.get) == 'ru'
    assert probabilities['ru'] < 0.9


def test_even_unanimous_single_candidates_keep_residual_mass():
    probabilities, residual = _pool({'ru': 1.0}, {'ru': 1.0}, {'ru': 1.0})
    assert probabilities['ru'] < 1.0
    assert residual > 0


def test_disagreeing_backends_stay_below_acceptance():
    probabilities, _ = _pool({'de': 1.0}, {'nl': 1.0}, {'fr': 1.0})
    assert max(probabilities.values()) < _full_pool().accept_confidence


def test_pooled_distribution_sums_to_one_with_residual():
    probabilities, residual = _pool({'es': 0.7, 'pt': 0.3}, {'es': 0.5, 'gl': 0.5}, {'es': 1.0})
    assert sum(probabilities.values()) + residual == pytest.approx(1.0)


def test_every_backend_set_has_its_own_calibration():
    calibration = load_calibration()
    for size in range(1, len(ALL_BACKENDS) + 1):
        for backends in itertools.combinations(ALL_BACKENDS, size):
            pool = calibration.for_backends(backends)
            assert pool is not None, backends
            assert set(pool.weights) == set(backends)


# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_accepted_ensemble_result_is_calibrated(step):
    _backends(step,
              BackendResult('langdetect', {'es': 1.0}, 'probability'),
              BackendResult('langid', {'es': 0.9, 'pt': 0.1}, 'softmax_top_k'),
              BackendResult('pycld2', {'es': 0.97}, 'text_percent', reliable=True))
    result = await step._detect_language_ensemble_async('¿Dónde está mi pedido de ayer?')
    assert (result.language, result.method) == ('es', 'calibrated_ensemble')
    assert result.accepted and result.calibrated
    assert result.agreement == 1.0
    assert 0 < result.margin <= result.confidence < 1.0


@pytest.mark.asyncio
@pytest.mark.parametrize('backend', ALL_BACKENDS)
async def test_single_backend_deployment_can_accept(step, backend):
    """A deployment with one backend must not always abstain on a confident answer."""
    _backends(step, BackendResult(backend, {'nl': 1.0}, 'probability'))
    result = await step._detect_language_ensemble_async('zorgvuldig afgestemd plan')
    assert result.accepted and result.language == 'nl', result.raw_results
    assert result.raw_results['pool_backends'] == [backend]


@pytest.mark.asyncio
async def test_missing_backend_uses_the_calibration_for_those_that_answered(step):
    step.backends = [(b, MagicMock()) for b in ALL_BACKENDS]
    step._run_backend_with_timeout = AsyncMock(side_effect=[
        BackendResult('langdetect', {'es': 1.0}, 'probability'),
        BackendResult('langid', {'es': 0.9, 'pt': 0.1}, 'softmax_top_k'),
        None,  # pycld2 timed out
    ])
    result = await step._detect_language_ensemble_async('¿Dónde está mi pedido de ayer?')
    assert result.raw_results['pool_backends'] == ['langdetect', 'langid']
    assert result.accepted and result.language == 'es'


@pytest.mark.asyncio
async def test_uncalibrated_backend_is_ignored(step):
    _backends(step,
              BackendResult('langid', {'es': 1.0}, 'softmax_top_k'),
              BackendResult('not-calibrated', {'pt': 1.0}, 'probability'))
    result = await step._detect_language_ensemble_async('¿Dónde está mi pedido de ayer?')
    assert result.raw_results['pool_backends'] == ['langid']
    assert 'pt' not in result.raw_results['pooled']


@pytest.mark.asyncio
async def test_single_script_candidate_is_not_renormalized_to_certainty(step):
    """Urdu-only letters leave one candidate; backends that prefer Persian must not make Urdu 1.0."""
    _backends(step,
              BackendResult('langdetect', {'fa': 1.0}, 'probability'),
              BackendResult('langid', {'fa': 0.9, 'ur': 0.1}, 'softmax_top_k'),
              BackendResult('pycld2', {'fa': 0.95}, 'text_percent'))
    result = await step._detect_language_ensemble_async('ٹھیک ہے، بتائیے')
    assert step._narrow_candidates('ٹھیک ہے، بتائیے', step._script_evidence('ٹھیک ہے، بتائیے')) == {'ur'}
    assert result.abstained
    assert result.raw_results['reason'] == 'below_threshold'


@pytest.mark.asyncio
async def test_weak_prior_cannot_become_high_confidence(step):
    _backends(step,
              BackendResult('langdetect', {'de': 1.0}, 'probability'),
              BackendResult('langid', {'nl': 1.0}, 'softmax_top_k'),
              BackendResult('pycld2', {'fr': 1.0}, 'text_percent'))
    prior = ConversationPrior({'fr': 1.0}, source='chat_history')
    result = await step._detect_language_ensemble_async('zorgvuldig afgestemd plan', prior=prior)
    assert (result.language, result.method) == ('fr', 'chat_history_prior')
    assert result.confidence <= ld.PRIOR_MAX_CONFIDENCE
    assert not result.accepted and not result.calibrated


@pytest.mark.asyncio
async def test_rule_path_is_accepted_but_not_calibrated(step):
    result = await step._detect_language_ensemble_async('안녕하세요')
    assert result.method == 'script_detection'
    assert result.accepted and not result.calibrated


@pytest.mark.asyncio
async def test_process_exposes_decision_fields_and_detector_version(step):
    _backends(step,
              BackendResult('langdetect', {'it': 1.0}, 'probability'),
              BackendResult('langid', {'it': 1.0}, 'softmax_top_k'),
              BackendResult('pycld2', {'it': 0.98}, 'text_percent'))
    context = ProcessingContext(message='Mi puoi aiutare con il mio ordine?', adapter_name='qa')
    await step.process(context)
    meta = context.language_detection_meta
    assert meta['accepted'] is True and meta['calibrated'] is True
    assert meta['agreement'] == 1.0 and meta['margin'] > 0
    assert meta['detector_version'] == load_calibration().version


# ---------------------------------------------------------------------------
# Downstream
# ---------------------------------------------------------------------------

def _instruction(language, **meta):
    builder = PromptInstructionBuilder(config={"language_detection": {"enabled": True}})
    context = ProcessingContext(message='x', adapter_name='qa')
    context.detected_language = language
    context.language_detection_meta = meta
    return builder.build_language_instruction(context)


@pytest.mark.parametrize('meta,named', [
    ({'accepted': True, 'confidence': 0.95}, True),
    ({'accepted': True, 'confidence': 0.7}, False),    # accepted, but below the strong-instruction bar
    ({'accepted': False, 'confidence': 0.95}, False),  # not decided by this message (e.g. a prior)
])
def test_prompt_names_language_only_for_confident_accepted_detection(meta, named):
    assert ('The user is writing in French' in _instruction('fr', **meta)) is named
