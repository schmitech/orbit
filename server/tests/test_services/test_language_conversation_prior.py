"""
Phase 2: the conversation language prior.

The detected language is persisted on the user message, read back on the next
request, and used only when the current message cannot decide on its own.
Tests use the production configuration unless they construct the alternate
policy they test.
"""

import copy
import os
import shutil
import tempfile
from unittest.mock import AsyncMock, MagicMock

import pytest
from inference.pipeline.base import ProcessingContext
from inference.pipeline.steps.language_detection import (
    LANGDETECT_AVAILABLE,
    LANGID_AVAILABLE,
    PYCLD2_AVAILABLE,
    ConversationPrior,
    LanguageDetectionStep,
    language_evidence,
)
from language_eval.runner import load_canonical_config
from pytest_asyncio import fixture
from services.chat_handlers.conversation_history_handler import ConversationHistoryHandler
from services.chat_handlers.response_processor import ResponseProcessor
from services.chat_history_service import ChatHistoryService
from services.sqlite_service import SQLiteService

pytestmark = pytest.mark.skipif(
    not any([LANGDETECT_AVAILABLE, LANGID_AVAILABLE, PYCLD2_AVAILABLE]),
    reason="No language detection backend installed",
)

FRENCH = "Bonjour, pourriez-vous m'aider à réserver une table pour ce soir ?"
SPANISH = "¿Dónde está mi pedido? Necesito ayuda, por favor."


class Container:
    def __init__(self, config, **services):
        self._config = config
        self._services = services

    def get(self, key):
        return self._config if key == 'config' else self._services.get(key)

    def get_or_none(self, key):
        return self.get(key)

    def has(self, key):
        return key == 'config' or key in self._services


def production_config(**overrides):
    config = copy.deepcopy(load_canonical_config())
    config['language_detection'].update(overrides)
    return config


def evidence(language, confidence=0.95, method='ensemble_voting', abstained=False):
    return {'language': language, 'confidence': confidence, 'method': method, 'abstained': abstained}


def user_msg(ev):
    return {'role': 'user', 'content': '', 'metadata': {'language_detection': ev}}


def history(*messages):
    service = MagicMock()
    service.get_conversation_history = AsyncMock(return_value=list(messages))
    return service


def cache(data=None):
    service = MagicMock()
    service.enabled = True
    service.get_json = AsyncMock(return_value=data)
    service.store_json = AsyncMock(return_value=True)
    return service


def step(config=None, **services):
    return LanguageDetectionStep(Container(config or production_config(), **services))


async def detect(detector, message, session_id='s1'):
    context = ProcessingContext(message=message, adapter_name='chat', session_id=session_id)
    await detector.process(context)
    return context


def test_conversation_tests_use_production_stickiness_default():
    assert load_canonical_config()['language_detection']['enable_stickiness'] is False
    assert load_canonical_config()['language_detection']['use_chat_history_prior'] is True


# ---------------------------------------------------------------------------
# Gate: a persisted turn is consumed by the next request
# ---------------------------------------------------------------------------

@fixture
async def chat_history():
    temp_dir = tempfile.mkdtemp()
    config = {
        'internal_services': {'backend': {'type': 'sqlite', 'sqlite': {
            'database_path': os.path.join(temp_dir, 'orbit.db')}}},
        'chat_history': {'enabled': True, 'default_limit': 50},
    }
    db = SQLiteService(config)
    await db.initialize()
    service = ChatHistoryService(config, database_service=db)
    await service.initialize()
    yield service
    await service.close()
    db.close()
    shutil.rmtree(temp_dir, ignore_errors=True)


def response_processor(chat_history_service):
    adapter_manager = MagicMock()
    adapter_manager.get_adapter_config.return_value = {'type': 'passthrough'}
    handler = ConversationHistoryHandler({}, chat_history_service, adapter_manager)
    handler.check_limit_warning = AsyncMock(return_value=None)
    return ResponseProcessor({}, handler, logger_service=AsyncMock())


@pytest.mark.asyncio
async def test_persisted_turn_is_the_prior_for_the_next_request(chat_history):
    # Two step instances stand in for two workers sharing only the database.
    first_worker = step(chat_history_service=chat_history)
    second_worker = step(chat_history_service=chat_history)

    turn1 = await detect(first_worker, FRENCH)
    assert turn1.detected_language == 'fr'
    await response_processor(chat_history).process_response(
        response="Bien sûr !", message=FRENCH, client_ip='127.0.0.1', adapter_name='chat',
        session_id='s1', user_id=None, api_key=None, backend='test', processing_time=0.1,
        language_detection=language_evidence(turn1),
    )

    stored = await chat_history.get_conversation_history('s1', include_metadata=True)
    assert stored[0]['metadata']['language_detection'] == evidence(
        'fr', turn1.language_detection_meta['confidence'], turn1.language_detection_meta['method'])
    assert 'language_detection' not in stored[1]['metadata']

    turn2 = await detect(second_worker, "OK")
    assert turn2.detected_language == 'fr'
    assert turn2.language_detection_meta['method'] == 'chat_history_prior'
    assert turn2.language_detection_meta['raw_results']['prior_source'] == 'chat_history'


# ---------------------------------------------------------------------------
# Reading the prior
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_assistant_messages_are_excluded():
    assistant = {'role': 'assistant', 'content': '', 'metadata': {'language_detection': evidence('de')}}
    detector = step(chat_history_service=history(user_msg(evidence('fr')), assistant))
    prior = await detector._get_conversation_prior(ProcessingContext(message='OK', session_id='s1'))
    assert prior.distribution == {'fr': 1.0}


@pytest.mark.asyncio
@pytest.mark.parametrize('untrusted', [
    evidence('unknown', 0.0, 'abstained', abstained=True),
    evidence('it', 0.55, 'threshold_fallback'),
    evidence('it', 0.6, 'chat_history_prior'),
    evidence('it', 0.6, 'sticky_previous'),
    evidence('it', 0.5, 'ensemble_voting'),
    {'language': 'it'},
])
async def test_untrusted_results_do_not_poison_later_turns(untrusted):
    detector = step(chat_history_service=history(user_msg(untrusted)))
    assert await detector._get_conversation_prior(ProcessingContext(message='OK', session_id='s1')) is None

    context = await detect(detector, "OK")
    assert context.detected_language == 'unknown'


@pytest.mark.asyncio
async def test_history_is_weighted_by_recency_and_confidence():
    detector = step(chat_history_service=history(
        user_msg(evidence('en')), user_msg(evidence('en')), user_msg(evidence('fr')),
    ))
    prior = await detector._get_conversation_prior(ProcessingContext(message='OK', session_id='s1'))
    # fr: 1.0, en: 0.5 + 0.25 -> the latest language leads after a single turn
    assert prior.top()[0] == 'fr'
    assert prior.distribution['fr'] == pytest.approx(1 / 1.75)


@pytest.mark.asyncio
async def test_prior_decides_only_with_a_majority_share():
    detector = step()
    split = ConversationPrior({'fr': 0.45, 'en': 0.45, 'de': 0.1}, source='chat_history')
    assert detector._prior_result(split, reason='low_evidence') is None
    majority = ConversationPrior({'fr': 0.8, 'en': 0.2}, source='chat_history')
    result = detector._prior_result(majority, reason='low_evidence')
    assert result.language == 'fr'
    assert result.confidence < 0.7  # below retrieval_min_confidence


def test_below_threshold_prior_must_be_supported_by_the_current_votes():
    detector = step()
    prior = ConversationPrior({'fr': 1.0}, source='chat_history')
    assert detector._prior_result(prior, reason='below_threshold_or_margin', supported_by={'es': 1.0}) is None
    assert detector._prior_result(
        prior, reason='below_threshold_or_margin', supported_by={'es': 1.0, 'fr': 0.5}
    ).language == 'fr'


# ---------------------------------------------------------------------------
# The current message decides first
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_clear_language_switch_overrides_history():
    detector = step(chat_history_service=history(*[user_msg(evidence('fr'))] * 3))
    context = await detect(detector, SPANISH)
    assert context.detected_language == 'es'
    assert context.language_detection_meta['method'] not in ('chat_history_prior', 'sticky_previous')


@pytest.mark.asyncio
async def test_prior_does_not_change_an_accepted_detection():
    message = "How do I install the software on my computer?"
    plain = await detect(step(), message, session_id=None)
    with_prior = await detect(step(chat_history_service=history(user_msg(evidence('fr')))), message)
    assert with_prior.detected_language == plain.detected_language == 'en'
    assert with_prior.language_detection_meta['confidence'] == plain.language_detection_meta['confidence']


@pytest.mark.asyncio
@pytest.mark.parametrize('message', ["👍", "42", "https://example.com/a/b"])
async def test_letterless_follow_up_uses_the_prior(message):
    context = await detect(step(chat_history_service=history(user_msg(evidence('fr')))), message)
    assert context.detected_language == 'fr'
    assert context.language_detection_meta['method'] == 'chat_history_prior'
    assert context.language_detection_meta['raw_results']['reason'] == 'no_letters'


@pytest.mark.asyncio
async def test_letterless_message_without_a_prior_abstains():
    context = await detect(step(), "👍", session_id=None)
    assert context.detected_language == 'unknown'
    assert context.language_detection_meta['raw_results']['reason'] == 'no_letters'


# ---------------------------------------------------------------------------
# Stickiness: one policy, the session cache as a fallback source
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ok_follows_a_strong_recent_language_when_stickiness_is_enabled():
    detector = step(production_config(enable_stickiness=True), cache_service=cache(evidence('es')))
    context = await detect(detector, "OK")
    assert context.detected_language == 'es'
    assert context.language_detection_meta['method'] == 'sticky_previous'


@pytest.mark.asyncio
async def test_session_cache_is_ignored_when_stickiness_is_disabled():
    session_cache = cache(evidence('es'))
    context = await detect(step(cache_service=session_cache), "OK")
    assert context.detected_language == 'unknown'
    session_cache.get_json.assert_not_called()


@pytest.mark.asyncio
async def test_history_and_cache_are_not_combined():
    session_cache = cache(evidence('es'))
    detector = step(
        production_config(enable_stickiness=True),
        chat_history_service=history(user_msg(evidence('fr'))),
        cache_service=session_cache,
    )
    prior = await detector._get_conversation_prior(ProcessingContext(message='OK', session_id='s1'))
    assert prior == ConversationPrior({'fr': 1.0}, source='chat_history')
    session_cache.get_json.assert_not_called()


@pytest.mark.asyncio
async def test_cache_ttl_is_configurable():
    session_cache = cache()
    detector = step(production_config(enable_stickiness=True, stickiness_ttl_seconds=600),
                    cache_service=session_cache)
    await detect(detector, SPANISH)
    session_cache.store_json.assert_called_once()
    assert session_cache.store_json.call_args.kwargs['ttl'] == 600


@pytest.mark.asyncio
async def test_prior_derived_result_is_not_cached():
    session_cache = cache(evidence('es'))
    detector = step(production_config(enable_stickiness=True), cache_service=session_cache)
    await detect(detector, "OK")
    session_cache.store_json.assert_not_called()


# ---------------------------------------------------------------------------
# Degrading safely
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_history_failure_falls_back_to_the_session_cache():
    broken_history = MagicMock()
    broken_history.get_conversation_history = AsyncMock(side_effect=RuntimeError('db down'))
    detector = step(production_config(enable_stickiness=True),
                    chat_history_service=broken_history, cache_service=cache(evidence('es')))
    context = await detect(detector, "OK")
    assert context.detected_language == 'es'


@pytest.mark.asyncio
async def test_all_sources_unavailable_abstains():
    broken_cache = cache()
    broken_cache.get_json = AsyncMock(side_effect=RuntimeError('redis down'))
    broken_history = MagicMock()
    broken_history.get_conversation_history = AsyncMock(side_effect=RuntimeError('db down'))
    detector = step(production_config(enable_stickiness=True),
                    chat_history_service=broken_history, cache_service=broken_cache)
    context = await detect(detector, "OK")
    assert context.detected_language == 'unknown'
    assert context.language_detection_meta['raw_results']['reason'] == 'low_evidence'


@pytest.mark.asyncio
async def test_no_session_means_no_prior():
    service = history(user_msg(evidence('fr')))
    context = await detect(step(chat_history_service=service), "OK", session_id=None)
    assert context.detected_language == 'unknown'
    service.get_conversation_history.assert_not_called()
