"""
Intent template matching regression gate.

Runs the intent-eval harness against each corpus in corpora/ and asserts the
top-1 match rate and recall@3/@5 don't regress below the checked-in baseline
in baseline.json. Ratchets upward only — if you genuinely improve matching,
update the baseline (see the bottom of this file for how).

Requires a reachable embedding provider only for queries not already present
in fixtures/embeddings_cache_*.json; skips gracefully otherwise so CI doesn't
need Ollama running once the cache is warm and committed.
"""

import json
import os

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

HERE = os.path.dirname(__file__)
BASELINE_PATH = os.path.join(HERE, "baseline.json")
CORPORA_DIR = os.path.join(HERE, "corpora")


def _load_baseline():
    if not os.path.exists(BASELINE_PATH):
        return {}
    with open(BASELINE_PATH, "r") as f:
        return json.load(f)


def _ollama_reachable() -> bool:
    try:
        import httpx
        resp = httpx.get("http://localhost:11434/api/tags", timeout=2.0)
        return resp.status_code == 200
    except Exception:
        return False


def _cache_covers_corpus(adapter_name: str, corpus_path: str) -> bool:
    """True if every query in the corpus already has a cached embedding under
    the CURRENT provider/model identity, so this adapter's eval can run fully
    offline. Matching on the query text alone (ignoring the provider/model
    prefix) would report coverage from a stale cache after a provider or
    model change — those keys exist but _CachingEmbeddingClient would never
    hit them, so the run would attempt live embedding calls anyway."""
    cache_path = os.path.join(HERE, "fixtures", f"embeddings_cache_{adapter_name}.json")
    if not os.path.exists(cache_path):
        return False
    from intent_eval.runner import hr_cache_key
    import yaml
    with open(corpus_path, "r") as f:
        corpus = yaml.safe_load(f)
    with open(cache_path, "r") as f:
        cache = json.load(f)
    return all(hr_cache_key(case["query"]) in cache for case in corpus.get("cases", []))


@pytest.mark.asyncio
async def test_hr_sqlite_match_rate_meets_baseline():
    from intent_eval.runner import build_hr_retriever, run_eval

    adapter_name = "intent-sql-sqlite-hr"
    corpus_path = os.path.join(CORPORA_DIR, f"{adapter_name}.yaml")
    baseline = _load_baseline().get(adapter_name)

    if baseline is None:
        pytest.skip(f"No baseline recorded for {adapter_name} yet — see baseline.json")

    cache_path = os.path.join(HERE, "fixtures", f"embeddings_cache_{adapter_name}.json")
    if not _cache_covers_corpus(adapter_name, corpus_path) and not _ollama_reachable():
        pytest.skip(
            "Embedding cache doesn't cover the full corpus and Ollama is unreachable "
            "at localhost:11434 — run the harness once locally to populate the cache."
        )

    retriever = await build_hr_retriever(embedding_cache_path=cache_path)
    try:
        result = await run_eval(retriever, corpus_path)
    finally:
        if hasattr(retriever.embedding_client, "save"):
            retriever.embedding_client.save()
        await retriever.close()

    summary = result.summary()

    assert result.total == baseline["total"], (
        f"Corpus size changed ({result.total} vs baseline {baseline['total']}) — "
        "regenerate the baseline after reviewing the diff."
    )

    # Compare raw correct-counts against the baseline's raw counts, not
    # pre-divided rates — dividing to a rate and rounding for storage, then
    # comparing against a freshly-computed float, invites exactly the kind of
    # spurious "regression" a 1-ULP rounding difference produces.
    if result.top1_correct < baseline["top1_correct"]:
        confusion_lines = "\n".join(
            f"  {c['query']!r}: expected {c['expected']!r}, got {c['got']!r} (score {c['score']:.4f})"
            for c in result.confusions
        )
        pytest.fail(
            f"Top-1 correct count regressed: {result.top1_correct}/{result.total} < "
            f"baseline {baseline['top1_correct']}/{baseline['total']}\n\nConfusions:\n{confusion_lines}"
        )

    assert result.recall_at_3 >= baseline["recall_at_3_correct"], (
        f"recall@3 regressed: {result.recall_at_3}/{result.total} < "
        f"baseline {baseline['recall_at_3_correct']}/{baseline['total']}"
    )
    assert result.recall_at_5 >= baseline["recall_at_5_correct"], (
        f"recall@5 regressed: {result.recall_at_5}/{result.total} < "
        f"baseline {baseline['recall_at_5_correct']}/{baseline['total']}"
    )

    print(f"\n{adapter_name} eval summary: {json.dumps(summary, indent=2)}")


# To (re)generate the baseline after a genuine accuracy improvement:
#
#   PYTHONPATH=server:server/tests python -c "
#   import asyncio, json
#   from intent_eval.runner import build_hr_retriever, run_eval
#   async def main():
#       r = await build_hr_retriever(
#           embedding_cache_path='server/tests/intent_eval/fixtures/embeddings_cache_intent-sql-sqlite-hr.json')
#       result = await run_eval(r, 'server/tests/intent_eval/corpora/intent-sql-sqlite-hr.yaml')
#       await r.close()
#       print(json.dumps({'intent-sql-sqlite-hr': {
#           'total': result.total,
#           'top1_correct': result.top1_correct,
#           'recall_at_3_correct': result.recall_at_3,
#           'recall_at_5_correct': result.recall_at_5,
#       }}, indent=2))
#   asyncio.run(main())
#   " > server/tests/intent_eval/baseline.json
