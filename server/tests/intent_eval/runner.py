"""
Intent template matching eval runner.

Drives a real intent retriever directly (no HTTP, no LLM pipeline) and reports
match-rate metrics against a corpus of (query, expected_template_id) cases —
see server/tests/intent_eval/corpora/*.yaml.

Query embeddings are cached to a JSON fixture keyed by (provider, model, text)
so repeat runs over an unchanged corpus don't need a reachable embedding
provider. The cache is populated on first run against a live provider (Ollama
by default) and committed alongside the corpus; only new/changed queries need
the provider reachable again.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Any, Optional

import yaml

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

# Identity used by _CachingEmbeddingClient._key() for the real client
# default_hr_retriever_config() builds. Kept as named constants (rather than
# re-deriving from a live client) so a cache-coverage check can compose the
# exact same key without constructing a retriever — and so bumping either one
# here is the single place that keeps the check honest about what the cache
# actually covers.
HR_EMBEDDING_PROVIDER_CLASS = "OllamaEmbeddingService"
HR_EMBEDDING_MODEL = "nomic-embed-text"


def hr_cache_key(query: str) -> str:
    """The exact cache key _CachingEmbeddingClient would compute for `query`
    against the HR retriever's configured embedding provider/model."""
    return f"{HR_EMBEDDING_PROVIDER_CLASS}::{HR_EMBEDDING_MODEL}::{query}"


class _CachingEmbeddingClient:
    """Wraps a real embedding client, caching embed_query results to disk.

    Delegates every other attribute/method to the wrapped client so it's a
    drop-in replacement for retriever.embedding_client.
    """

    def __init__(self, inner, cache_path: str):
        self._inner = inner
        self._cache_path = cache_path
        self._cache = self._load_cache()
        self._dirty = False

    def _load_cache(self) -> dict[str, list[float]]:
        if os.path.exists(self._cache_path):
            with open(self._cache_path, "r") as f:
                return json.load(f)
        return {}

    def save(self):
        if not self._dirty:
            return
        os.makedirs(os.path.dirname(self._cache_path), exist_ok=True)
        with open(self._cache_path, "w") as f:
            json.dump(self._cache, f)
        self._dirty = False

    def _key(self, text: str) -> str:
        model = getattr(self._inner, "model", None) or getattr(self._inner, "model_name", "unknown")
        provider = self._inner.__class__.__name__
        return f"{provider}::{model}::{text}"

    async def embed_query(self, text: str):
        key = self._key(text)
        if key in self._cache:
            return self._cache[key]
        vector = await self._inner.embed_query(text)
        self._cache[key] = list(vector)
        self._dirty = True
        return vector

    async def embed_query_tracked(self, text: str, *args, **kwargs):
        # Contract (ai_services/services/embedding_service.py): always returns
        # just the vector, List[float] — usage is reported via the usage_sink
        # kwarg's in-place mutation, never as part of the return value.
        key = self._key(text)
        if key in self._cache:
            return self._cache[key]
        vector = await self._inner.embed_query_tracked(text, *args, **kwargs)
        self._cache[key] = list(vector)
        self._dirty = True
        return vector

    def __getattr__(self, name):
        return getattr(self._inner, name)


@dataclass
class EvalResult:
    corpus_path: str
    adapter_name: str
    total: int = 0
    top1_correct: int = 0
    recall_at_3: int = 0
    recall_at_5: int = 0
    no_match: int = 0
    errors: int = 0
    confidences: list[float] = field(default_factory=list)
    confusions: list[dict[str, Any]] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)

    @property
    def top1_match_rate(self) -> float:
        return self.top1_correct / self.total if self.total else 0.0

    @property
    def recall_at_3_rate(self) -> float:
        return self.recall_at_3 / self.total if self.total else 0.0

    @property
    def recall_at_5_rate(self) -> float:
        return self.recall_at_5 / self.total if self.total else 0.0

    @property
    def mean_top1_confidence(self) -> float:
        return sum(self.confidences) / len(self.confidences) if self.confidences else 0.0

    def summary(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter_name,
            "corpus": self.corpus_path,
            "total": self.total,
            "top1_match_rate": round(self.top1_match_rate, 4),
            "recall_at_3": round(self.recall_at_3_rate, 4),
            "recall_at_5": round(self.recall_at_5_rate, 4),
            "mean_top1_confidence": round(self.mean_top1_confidence, 4),
            "no_match": self.no_match,
            "errors": self.errors,
        }


def load_corpus(corpus_path: str) -> dict[str, Any]:
    with open(corpus_path, "r") as f:
        return yaml.safe_load(f)


def default_hr_retriever_config(
    db_path: str,
    domain_config_path: str,
    template_library_path: str,
    chroma_persist_dir: str,
    template_collection_name: str = "hr_intent_templates_eval",
    confidence_threshold: float = 0.4,
) -> dict[str, Any]:
    """Minimal config to construct a real IntentSQLiteRetriever, mirroring the
    shape used by server/tests/test_retrievers/test_intent_sqlite_retriever.py
    but pointed at a real embedding provider (Ollama) instead of a mock."""
    return {
        "general": {},
        "datasources": {
            "sqlite": {"database": db_path, "check_same_thread": False},
        },
        "inference": {
            "ollama": {"enabled": True, "base_url": "http://localhost:11434", "model": "gemma4:e2b"},
        },
        "inference_provider": "ollama",
        "embedding": {"provider": "ollama", "enabled": True},
        "embeddings": {
            "ollama": {"base_url": "http://localhost:11434", "model": HR_EMBEDDING_MODEL, "dimensions": 768},
        },
        "stores": {
            "vector_stores": {
                "chroma": {
                    "enabled": True,
                    "type": "chroma",
                    "connection_params": {"persist_directory": chroma_persist_dir},
                },
            },
        },
        "adapter_config": {
            "domain_config_path": domain_config_path,
            "template_library_path": [template_library_path],
            "template_collection_name": template_collection_name,
            "store_name": "chroma",
            "confidence_threshold": confidence_threshold,
            "max_templates": 5,
            "return_results": 10,
            "reload_templates_on_start": False,
            "force_reload_templates": False,
        },
    }


async def build_hr_retriever(embedding_cache_path: Optional[str] = None):
    """Constructs and initializes the real intent-sql-sqlite-hr retriever
    against the checked-in example database, with query embeddings cached."""
    from ai_services import register_all_services
    from retrievers.implementations.intent.intent_sqlite_retriever import IntentSQLiteRetriever

    hr_dir = os.path.join(
        REPO_ROOT, "examples", "intent-templates", "sql-intent-template", "sqlite", "hr"
    )
    config = default_hr_retriever_config(
        db_path=os.path.join(hr_dir, "hr.db"),
        domain_config_path=os.path.join(hr_dir, "hr-domain.yaml"),
        template_library_path=os.path.join(hr_dir, "hr-templates.yaml"),
        chroma_persist_dir=os.path.join(FIXTURES_DIR, "chroma_hr"),
    )

    register_all_services(config)
    retriever = IntentSQLiteRetriever(config=config)
    await retriever.initialize()

    if embedding_cache_path:
        retriever.embedding_client = _CachingEmbeddingClient(retriever.embedding_client, embedding_cache_path)

    return retriever


async def run_eval(retriever, corpus_path: str, max_templates: int = 5) -> EvalResult:
    from utils.template_diagnostics import diagnose_template_query

    corpus = load_corpus(corpus_path)
    result = EvalResult(corpus_path=corpus_path, adapter_name=corpus.get("adapter", "unknown"))

    for case in corpus.get("cases", []):
        query = case["query"]
        expected = case.get("expected_template_id")
        expect = case.get("expect", "match")
        result.total += 1

        try:
            diag = await diagnose_template_query(
                retriever=retriever,
                query=query,
                max_templates=max_templates,
                execute=False,
                include_all_candidates=True,
                verbose=False,
            )
        except Exception as e:
            result.errors += 1
            result.failures.append({"query": query, "expected": expected, "error": str(e)})
            continue

        search = diag.get("template_search") or {}
        candidates = search.get("candidates") or []
        candidate_ids = [c.get("template_id") for c in candidates]

        if expect == "no_match":
            if not candidate_ids:
                result.top1_correct += 1
                result.recall_at_3 += 1
                result.recall_at_5 += 1
            else:
                result.failures.append({"query": query, "expected": "no_match", "got": candidate_ids[:3]})
            continue

        if not candidate_ids:
            result.no_match += 1
            result.failures.append({"query": query, "expected": expected, "got": None})
            continue

        top1 = candidate_ids[0]
        top1_score = candidates[0].get("similarity", 0.0)
        result.confidences.append(top1_score)

        if top1 == expected:
            result.top1_correct += 1
        else:
            result.confusions.append({"query": query, "expected": expected, "got": top1, "score": top1_score})
            result.failures.append({"query": query, "expected": expected, "got": top1, "score": top1_score})

        if expected in candidate_ids[:3]:
            result.recall_at_3 += 1
        if expected in candidate_ids[:5]:
            result.recall_at_5 += 1

    return result
