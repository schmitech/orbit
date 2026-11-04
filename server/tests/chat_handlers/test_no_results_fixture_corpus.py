"""
Fixture corpus for the "no results" detection heuristics in ResponseProcessor.

This is the Phase 2 audit/regression baseline from docs/roadmap/response-processor-cleanup.md:
a corpus of representative no-results and data-bearing responses, in each of the 7
supported languages, run through the combined `_response_indicates_no_results` method.
It exists so future consolidation of `_NO_RESULTS_PATTERNS`, `negative_indicators`, and
`apologetic_starters` (Phase 2 Step A/B) can be checked against a fixed, known-good
baseline instead of relying on spot-checks.
"""

import pytest
from unittest.mock import AsyncMock

from services.chat_handlers.response_processor import ResponseProcessor
from services.chat_handlers.conversation_history_handler import ConversationHistoryHandler


@pytest.fixture
def mock_conversation_handler():
    handler = AsyncMock(spec=ConversationHistoryHandler)
    handler.check_limit_warning = AsyncMock(return_value=None)
    handler.store_turn = AsyncMock(return_value=("user_msg_123", "assistant_msg_456"))
    return handler


@pytest.fixture
def processor(base_config, mock_conversation_handler, mock_logger_service):
    return ResponseProcessor(
        config=base_config,
        conversation_handler=mock_conversation_handler,
        logger_service=mock_logger_service
    )


# Each entry: (response, expected is-no-results, language)
NO_RESULTS_CORPUS = [
    # English
    ("Sorry, I couldn't find any results matching your search.", True, "en"),
    ("Unfortunately, there is no data available for that period.", True, "en"),
    ("No records found. Please try a different query.", True, "en"),
    ("Here are the top 5 products by revenue this quarter.", False, "en"),
    ("The report lists 42 open incidents across 3 teams.", False, "en"),

    # French
    ("Désolé, je n'ai trouvé aucun résultat pour cette requête.", True, "fr"),
    ("Malheureusement, pas de données correspondantes.", True, "fr"),
    ("Voici les résultats de votre recherche avec 150 contrats.", False, "fr"),

    # Spanish
    ("Lo siento, no encontré ningún resultado.", True, "es"),
    ("Lamentablemente, no hay datos disponibles.", True, "es"),
    ("Aquí están los 120 contratos encontrados este año.", False, "es"),

    # German
    ("Leider konnte ich keine Ergebnisse finden.", True, "de"),
    ("Entschuldigung, keine Daten verfügbar.", True, "de"),
    ("Hier sind die 50 gefundenen Verträge aus diesem Jahr.", False, "de"),

    # Italian
    ("Mi dispiace, non ho trovato risultati.", True, "it"),
    ("Purtroppo nessun dato disponibile per questo periodo.", True, "it"),
    ("Ecco i 75 contratti trovati nel database.", False, "it"),

    # Portuguese
    ("Desculpe, não encontrei nenhum resultado.", True, "pt"),
    ("Infelizmente, sem dados disponíveis para esse período.", True, "pt"),
    ("Aqui estão os 200 contratos encontrados este ano.", False, "pt"),

    # Dutch
    ("Helaas kon ik geen resultaten vinden voor deze zoekopdracht.", True, "nl"),
    ("Hier zijn de 30 gevonden contracten van dit jaar.", False, "nl"),

    # Documented drift case (Phase 2 audit): the regex rule scopes 'outside'/'beyond' to
    # "(my|the) (scope|knowledge|data)", but a long, data-bearing response using either
    # word in an unrelated sense must not be misread as "no results" via the keyword rule.
    (
        "Sales figures for products priced beyond $100 are shown below, "
        "alongside the full breakdown of regions outside the EU and their totals.",
        False,
        "en",
    ),

    # Regression case (Phase 2 Step A/B review): denial phrasing using "unavailable" /
    # "cannot retrieve" was previously caught by the removed bare-keyword list
    # ('unavailable', 'cannot' each counting as one of the required 2 indicators) and must
    # still be caught now that the keyword list is gone.
    ("The requested dataset is unavailable, so I cannot retrieve it.", True, "en"),
    (
        "This endpoint is unavailable for free-tier users, but here are the 50 results "
        "from the paid tier: Alpha, Beta, Gamma, Delta, and 46 more entries.",
        False,
        "en",
    ),
]


@pytest.mark.parametrize("response,expected,language", NO_RESULTS_CORPUS)
def test_no_results_fixture_corpus(processor, response, expected, language):
    """Permanent regression baseline for the three no-results heuristics combined.

    Any future consolidation of _NO_RESULTS_PATTERNS / negative_indicators /
    apologetic_starters must keep every one of these cases passing.
    """
    result = processor._response_indicates_no_results(response)
    assert result == expected, f"[{language}] unexpected result for: {response!r}"
