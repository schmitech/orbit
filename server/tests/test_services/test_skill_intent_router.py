#!/usr/bin/env python3
"""
Unit tests for SkillIntentRouter (server/services/skill_intent_router.py).

Covers the two-stage hybrid detection without any live provider:
  - candidate filtering (available_skills ∩ routable backing-adapter types)
  - embedding pre-filter gating (below-threshold => None, no LLM call)
  - LLM confirm parsing (exact name, NONE, wrapped-in-sentence, out-of-list)
  - disambiguation between similar generation skills
  - the fast-path: a non-matching query never invokes the confirm LLM

The embedding client and confirm-LLM provider are mocked; the adapter_manager
is a light fake implementing only the methods the router calls.
"""

import os
import sys

import pytest

server_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(server_dir)

from services.skill_intent_router import SkillIntentRouter, _cosine


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class _FakeEmbeddingClient:
    """Deterministic embeddings driven by an explicit {text: vector} table.

    Any text not in the table maps to a fixed 'unrelated' vector so it scores
    ~0 against everything, exercising the below-threshold fast path.
    """

    def __init__(self, table):
        self.table = table
        self.initialized = True

    def _vec(self, text):
        return self.table.get(text, [0.0, 0.0, 1.0])

    async def initialize(self):
        self.initialized = True
        return True

    async def embed_query(self, text):
        return self._vec(text)

    async def embed_documents(self, texts):
        return [self._vec(t) for t in texts]


class _FakeProvider:
    """Records prompts and returns a scripted answer; counts calls."""

    def __init__(self, answer):
        self.answer = answer
        self.calls = 0
        self.last_prompt = None

    async def generate(self, prompt, **kwargs):
        self.calls += 1
        self.last_prompt = prompt
        return self.answer


class _FakeAdapterManager:
    """Minimal adapter_manager exposing only what the router touches."""

    def __init__(self, adapter_configs, skills, embedding_client, provider):
        self._configs = adapter_configs
        self._skills = skills
        self._embedding_client = embedding_client
        self._provider = provider
        self.embedding_requests = []
        self.provider_requests = []

    def get_adapter_config(self, name):
        return self._configs.get(name)

    def get_all_skills(self):
        return self._skills

    async def get_overridden_embedding(self, provider_name, adapter_name=None):
        self.embedding_requests.append(provider_name)
        return self._embedding_client

    async def get_overridden_provider(self, provider_name, adapter_name=None, explicit_model_override=None):
        self.provider_requests.append((provider_name, explicit_model_override))
        return self._provider


# ---------------------------------------------------------------------------
# Fixtures / builders
# ---------------------------------------------------------------------------

PDF_VEC = [1.0, 0.0, 0.0]
EXCEL_VEC = [0.0, 1.0, 0.0]

# Skill phrases are always anchored on their axis, so only the *query* vector
# (supplied per-test via embedding_table) decides what survives the pre-filter.
_SKILL_PHRASE_VECS = {
    "make a pdf": PDF_VEC, "export as pdf": PDF_VEC,
    "PDF": PDF_VEC, "Generate PDF documents": PDF_VEC,
    "put this in a spreadsheet": EXCEL_VEC, "make an excel file": EXCEL_VEC,
    "Excel": EXCEL_VEC, "Generate Excel spreadsheets": EXCEL_VEC,
}


def _build(embedding_table, confirm_answer, *, threshold=0.35, router_provider="cohere"):
    """Construct a router wired to fakes, plus the consumer adapter name.

    ``embedding_table`` supplies the *query* vector(s); skill phrases are
    anchored on their axes automatically (query entries win on key collision).
    """
    embedding_table = {**_SKILL_PHRASE_VECS, **embedding_table}
    adapter_configs = {
        # Consumer adapter that opts into auto-routing and lists the skills.
        "simple-chat-with-files": {
            "type": "passthrough",
            "capabilities": {"available_skills": ["PDF", "Excel", "HR"]},
        },
        # Backing skill adapters.
        "pdf-generator": {
            "type": "document_generation",
            "capabilities": {"routing_examples": ["make a pdf", "export as pdf"]},
        },
        "excel-generator": {
            "type": "document_generation",
            "capabilities": {"routing_examples": ["put this in a spreadsheet", "make an excel file"]},
        },
        # Retrieval skill — NOT routable, must be filtered out of candidates.
        "intent-sql-sqlite-hr": {
            "type": "retriever",
            "capabilities": {},
        },
    }
    skills = [
        {"name": "PDF", "description": "Generate PDF documents", "adapter_name": "pdf-generator", "enabled": True},
        {"name": "Excel", "description": "Generate Excel spreadsheets", "adapter_name": "excel-generator", "enabled": True},
        {"name": "HR", "description": "HR data assistant", "adapter_name": "intent-sql-sqlite-hr", "enabled": True},
    ]
    embedding_client = _FakeEmbeddingClient(embedding_table)
    provider = _FakeProvider(confirm_answer)
    manager = _FakeAdapterManager(adapter_configs, skills, embedding_client, provider)
    config = {
        "embedding": {"provider": "openai"},
        "skill_routing": {
            "embedding_threshold": threshold,
            "router_provider": router_provider,
            "router_model": "command-r7b-12-2024",
        },
    }
    router = SkillIntentRouter(config, manager)
    return router, manager, provider


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_cosine_edges():
    assert _cosine([1, 0, 0], [1, 0, 0]) == pytest.approx(1.0)
    assert _cosine([1, 0, 0], [0, 1, 0]) == pytest.approx(0.0)
    assert _cosine([0, 0, 0], [1, 0, 0]) == 0.0  # zero vector guarded


@pytest.mark.asyncio
async def test_positive_routes_to_pdf():
    # Query embeds onto the PDF axis (skill phrases are anchored there by _build).
    router, manager, provider = _build({"make a pdf of this": PDF_VEC}, confirm_answer="PDF")
    result = await router.detect("make a pdf of this", [], "simple-chat-with-files")
    assert result == "PDF"
    assert provider.calls == 1  # confirm ran because a candidate survived


@pytest.mark.asyncio
async def test_negative_no_llm_call():
    # Ordinary question: query maps to the 'unrelated' vector, nothing crosses threshold.
    router, manager, provider = _build(embedding_table={}, confirm_answer="PDF")
    result = await router.detect("what is retrieval-augmented generation?", [], "simple-chat-with-files")
    assert result is None
    assert provider.calls == 0  # fast path: confirm LLM never invoked


@pytest.mark.asyncio
async def test_disambiguation_prefers_excel():
    # Query leans toward Excel but overlaps PDF enough that both survive the
    # permissive pre-filter; the confirm LLM then picks Excel.
    router, manager, provider = _build(
        {"put this in a spreadsheet": [0.6, 0.8, 0.0]}, confirm_answer="Excel"
    )
    result = await router.detect("put this in a spreadsheet", [], "simple-chat-with-files")
    assert result == "Excel"
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_confirm_none_returns_none():
    router, manager, provider = _build({"draft an email about pdfs": PDF_VEC}, confirm_answer="NONE")
    result = await router.detect("draft an email about pdfs", [], "simple-chat-with-files")
    assert result is None
    assert provider.calls == 1  # candidate survived, but confirm declined


@pytest.mark.asyncio
async def test_confirm_wrapped_answer_parsed():
    router, manager, provider = _build({"q": PDF_VEC}, confirm_answer="The skill is PDF.")
    result = await router.detect("q", [], "simple-chat-with-files")
    assert result == "PDF"


@pytest.mark.asyncio
async def test_confirm_out_of_list_answer_rejected():
    router, manager, provider = _build({"q": PDF_VEC}, confirm_answer="Klingon")
    result = await router.detect("q", [], "simple-chat-with-files")
    assert result is None


@pytest.mark.asyncio
async def test_retrieval_skill_filtered_from_candidates():
    # HR is in available_skills but its backing adapter type is 'retriever' (not routable).
    router, manager, provider = _build(embedding_table={}, confirm_answer="HR")
    candidates = router._candidate_skills("simple-chat-with-files")
    names = {c["name"] for c in candidates}
    assert "HR" not in names
    assert names == {"PDF", "Excel"}


@pytest.mark.asyncio
async def test_empty_message_returns_none():
    router, manager, provider = _build(embedding_table={}, confirm_answer="PDF")
    assert await router.detect("   ", [], "simple-chat-with-files") is None
    assert provider.calls == 0


@pytest.mark.asyncio
async def test_adapter_without_available_skills_returns_none():
    router, manager, provider = _build(embedding_table={"q": PDF_VEC}, confirm_answer="PDF")
    # Adapter with no available_skills => no candidates.
    manager._configs["bare"] = {"type": "passthrough", "capabilities": {}}
    assert await router.detect("q", [], "bare") is None


@pytest.mark.asyncio
async def test_uses_global_embedding_provider_by_default():
    router, manager, provider = _build({"make a pdf of this": PDF_VEC}, confirm_answer="PDF")
    await router.detect("make a pdf of this", [], "simple-chat-with-files")
    # No adapter embedding_provider override => global embedding.provider ("openai").
    assert manager.embedding_requests == ["openai"]


@pytest.mark.asyncio
async def test_prefers_adapter_embedding_provider_override():
    router, manager, provider = _build({"make a pdf of this": PDF_VEC}, confirm_answer="PDF")
    manager._configs["simple-chat-with-files"]["embedding_provider"] = "cohere"
    await router.detect("make a pdf of this", [], "simple-chat-with-files")
    # Adapter override wins over the global default.
    assert manager.embedding_requests == ["cohere"]


@pytest.mark.asyncio
async def test_auto_routable_skills_is_candidate_source():
    # available_skills empty (no explicit user invocation), but ORBIT may still
    # auto-route to the skills listed in auto_routable_skills.
    router, manager, provider = _build({"make a pdf of this": PDF_VEC}, confirm_answer="PDF")
    caps = manager._configs["simple-chat-with-files"]["capabilities"]
    caps["available_skills"] = []
    caps["auto_routable_skills"] = ["PDF", "Excel"]
    candidates = {c["name"] for c in router._candidate_skills("simple-chat-with-files")}
    assert candidates == {"PDF", "Excel"}
    result = await router.detect("make a pdf of this", [], "simple-chat-with-files")
    assert result == "PDF"


@pytest.mark.asyncio
async def test_falls_back_to_available_skills_when_no_auto_routable():
    router, manager, provider = _build({"make a pdf of this": PDF_VEC}, confirm_answer="PDF")
    # No auto_routable_skills => candidates come from available_skills.
    candidates = {c["name"] for c in router._candidate_skills("simple-chat-with-files")}
    assert candidates == {"PDF", "Excel"}
