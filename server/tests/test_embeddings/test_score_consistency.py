"""
Score consistency and template embedding strategy tests.

Tests for:
- Cosine distance-to-similarity conversion across all vector stores
- Per-example embedding text generation
- Template search deduplication logic
"""

import pytest
import os
import sys

server_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(server_dir)


# ---------------------------------------------------------------------------
# Score formula tests — verify all stores return consistent cosine similarity
# ---------------------------------------------------------------------------

class TestChromaScoreConversion:
    """Test ChromaDB cosine distance → similarity conversion."""

    def _convert(self, distance: float) -> float:
        """Mirrors ChromaStore / ChromaRetriever formula."""
        return max(0.0, 1.0 - distance)

    def test_identical_vectors(self):
        assert self._convert(0.0) == 1.0

    def test_orthogonal_vectors(self):
        assert self._convert(1.0) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        # distance=2 → clamped to 0
        assert self._convert(2.0) == 0.0

    def test_typical_good_match(self):
        # distance=0.2 → similarity=0.8
        assert self._convert(0.2) == pytest.approx(0.8)

    def test_typical_moderate_match(self):
        # distance=0.5 → similarity=0.5
        assert self._convert(0.5) == pytest.approx(0.5)

    def test_score_never_negative(self):
        """Score should never go below 0 even for extreme distances."""
        assert self._convert(1.5) == 0.0
        assert self._convert(10.0) == 0.0

    def test_consistency_with_qdrant(self):
        """Verify Chroma score matches what Qdrant would return for same similarity."""
        # For cosine_similarity = 0.75:
        #   ChromaDB distance = 1 - 0.75 = 0.25
        #   Chroma score = max(0, 1 - 0.25) = 0.75
        #   Qdrant score = 0.75 (native)
        chroma_score = self._convert(0.25)
        qdrant_score = 0.75
        assert chroma_score == pytest.approx(qdrant_score)

    def test_consistency_across_range(self):
        """Scores should match Qdrant across the full [0,1] similarity range."""
        for sim in [0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0]:
            chroma_distance = 1.0 - sim
            chroma_score = self._convert(chroma_distance)
            assert chroma_score == pytest.approx(sim, abs=1e-9), \
                f"Chroma score {chroma_score} != expected similarity {sim}"


class TestFaissScoreConversion:
    """Test FAISS L2 distance → similarity conversion."""

    def _convert(self, distance: float) -> float:
        return 1.0 / (1.0 + distance)

    def test_identical_vectors(self):
        assert self._convert(0.0) == 1.0

    def test_moderate_distance(self):
        assert self._convert(1.0) == pytest.approx(0.5)

    def test_large_distance(self):
        assert self._convert(9.0) == pytest.approx(0.1)

    def test_always_positive(self):
        for d in [0, 0.01, 0.5, 1, 10, 100, 1000]:
            assert self._convert(d) > 0


class TestMilvusScoreConversion:
    """Test Milvus L2 distance → similarity conversion (same formula as FAISS)."""

    def _convert(self, distance: float) -> float:
        return 1.0 / (1.0 + distance)

    def test_identical_vectors(self):
        assert self._convert(0.0) == 1.0

    def test_matches_faiss(self):
        """Milvus and FAISS should produce identical scores for same L2 distance."""
        for d in [0, 0.1, 0.5, 1.0, 5.0, 10.0]:
            faiss_score = 1.0 / (1.0 + d)
            milvus_score = self._convert(d)
            assert milvus_score == pytest.approx(faiss_score)


class TestWeaviateScoreConversion:
    """Test Weaviate distance → similarity conversion."""

    def _convert(self, distance: float) -> float:
        return 1 - distance

    def test_identical_vectors(self):
        assert self._convert(0.0) == 1.0

    def test_consistency_with_chroma(self):
        """Weaviate uses same formula as fixed Chroma (both: 1 - distance)."""
        for d in [0.0, 0.1, 0.25, 0.5, 0.75, 1.0]:
            weaviate = self._convert(d)
            chroma = max(0.0, 1.0 - d)
            assert weaviate == pytest.approx(chroma)


# ---------------------------------------------------------------------------
# Per-example embedding text generation tests
# ---------------------------------------------------------------------------

class TestCreateExampleEmbeddingTexts:
    """Test the per-example embedding text generation strategy."""

    def _make_retriever_stub(self):
        """Create a minimal stub with the methods under test."""
        from retrievers.base.intent_sql_base import IntentSQLRetriever

        class Stub:
            pass

        stub = Stub()
        stub._create_example_embedding_texts = IntentSQLRetriever._create_example_embedding_texts.__get__(stub)
        stub._create_embedding_text = IntentSQLRetriever._create_embedding_text.__get__(stub)
        # Minimal domain_adapter mock for _create_embedding_text fallback
        class FakeDomainAdapter:
            def get_domain_config(self):
                return {}
        stub.domain_adapter = FakeDomainAdapter()
        return stub

    def test_one_vector_per_example(self):
        stub = self._make_retriever_stub()
        template = {
            'id': 'test_template',
            'description': 'Test description',
            'nl_examples': ['question one', 'question two', 'question three'],
            'tags': ['tag1'],
            'parameters': [],
        }
        result = stub._create_example_embedding_texts(template)
        assert len(result) == 3, "Should produce one entry per nl_example"

    def test_suffixes_are_unique(self):
        stub = self._make_retriever_stub()
        template = {
            'id': 'test_template',
            'description': 'desc',
            'nl_examples': ['q1', 'q2', 'q3'],
            'tags': [],
            'parameters': [],
        }
        result = stub._create_example_embedding_texts(template)
        suffixes = [suffix for _, suffix in result]
        assert len(suffixes) == len(set(suffixes)), "Suffixes must be unique"

    def test_example_text_is_dominant(self):
        stub = self._make_retriever_stub()
        template = {
            'id': 'test_template',
            'description': 'Hate crimes analysis',
            'nl_examples': ['Most targeted groups'],
            'semantic_tags': {'primary_entity': 'hate_crimes', 'action': 'calculate'},
            'tags': [],
            'parameters': [],
        }
        result = stub._create_example_embedding_texts(template)
        text, suffix = result[0]
        # The nl_example should appear first (dominant signal)
        assert text.startswith('Most targeted groups'), \
            f"Example should be the leading text, got: {text!r}"

    def test_includes_context(self):
        stub = self._make_retriever_stub()
        template = {
            'id': 'test_template',
            'description': 'Hate crimes by motivation',
            'nl_examples': ['Most targeted groups'],
            'semantic_tags': {'primary_entity': 'hate_crimes', 'action': 'calculate'},
            'tags': [],
            'parameters': [],
        }
        result = stub._create_example_embedding_texts(template)
        text, _ = result[0]
        assert 'Hate crimes by motivation' in text, "Should include description"
        assert 'hate_crimes' in text, "Should include primary_entity"

    def test_fallback_for_no_examples(self):
        stub = self._make_retriever_stub()
        template = {
            'id': 'test_template',
            'description': 'A template without examples',
            'nl_examples': [],
            'tags': ['tag1'],
            'parameters': [],
        }
        result = stub._create_example_embedding_texts(template)
        assert len(result) == 1, "Should fall back to single blob embedding"
        _, suffix = result[0]
        assert suffix == 'desc', "Fallback suffix should be 'desc'"

    def test_empty_examples_skipped(self):
        stub = self._make_retriever_stub()
        template = {
            'id': 'test_template',
            'description': 'desc',
            'nl_examples': ['valid question', '', '   ', 'another valid'],
            'tags': [],
            'parameters': [],
        }
        result = stub._create_example_embedding_texts(template)
        assert len(result) == 2, "Should skip empty/whitespace-only examples"


# ---------------------------------------------------------------------------
# Deduplication logic tests
# ---------------------------------------------------------------------------

class TestTemplateDeduplication:
    """Test the ::exN suffix stripping and dedup logic from _find_best_templates."""

    def _deduplicate(self, search_results):
        """Mirrors the dedup logic in _find_best_templates."""
        seen = {}
        for result in search_results:
            raw_tid = result.get('template_id', '')
            base_tid = raw_tid.rsplit('::', 1)[0] if '::' in raw_tid else raw_tid
            score = result.get('score', 0)
            if base_tid not in seen or score > seen[base_tid]['score']:
                result['template_id'] = base_tid
                seen[base_tid] = result
        return sorted(seen.values(), key=lambda r: r.get('score', 0), reverse=True)

    def test_keeps_highest_score(self):
        results = [
            {'template_id': 'tmpl_a::ex0', 'score': 0.7},
            {'template_id': 'tmpl_a::ex1', 'score': 0.9},
            {'template_id': 'tmpl_a::ex2', 'score': 0.6},
        ]
        deduped = self._deduplicate(results)
        assert len(deduped) == 1
        assert deduped[0]['score'] == 0.9
        assert deduped[0]['template_id'] == 'tmpl_a'

    def test_multiple_templates(self):
        results = [
            {'template_id': 'tmpl_a::ex0', 'score': 0.9},
            {'template_id': 'tmpl_b::ex0', 'score': 0.8},
            {'template_id': 'tmpl_a::ex1', 'score': 0.7},
            {'template_id': 'tmpl_b::ex1', 'score': 0.85},
        ]
        deduped = self._deduplicate(results)
        assert len(deduped) == 2
        assert deduped[0]['template_id'] == 'tmpl_a'
        assert deduped[0]['score'] == 0.9
        assert deduped[1]['template_id'] == 'tmpl_b'
        assert deduped[1]['score'] == 0.85

    def test_no_suffix_preserved(self):
        """Templates without ::exN suffix should pass through unchanged."""
        results = [
            {'template_id': 'old_style_id', 'score': 0.8},
        ]
        deduped = self._deduplicate(results)
        assert len(deduped) == 1
        assert deduped[0]['template_id'] == 'old_style_id'

    def test_empty_input(self):
        assert self._deduplicate([]) == []

    def test_sorted_by_score_descending(self):
        results = [
            {'template_id': 'c::ex0', 'score': 0.5},
            {'template_id': 'a::ex0', 'score': 0.9},
            {'template_id': 'b::ex0', 'score': 0.7},
        ]
        deduped = self._deduplicate(results)
        scores = [r['score'] for r in deduped]
        assert scores == sorted(scores, reverse=True)
