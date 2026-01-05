"""
Tests for the CompositeIntentRetriever class

Tests the composite retriever's ability to:
- Search across multiple child adapter template stores
- Find the best matching template
- Route queries to the correct child adapter
- Multi-stage selection with reranking and string similarity
"""

import pytest
import asyncio
import sys
import os
from typing import Dict, Any, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass

# Add the server directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from retrievers.base.intent_composite_base import CompositeIntentRetriever, TemplateMatch


class MockTemplateStore:
    """Mock template store for testing."""
    
    def __init__(self, templates: List[Dict[str, Any]]):
        self.templates = templates
    
    async def search_similar_templates(
        self, 
        query_embedding: List[float], 
        limit: int = 5,
        threshold: float = 0.0
    ) -> List[Dict[str, Any]]:
        """Return mock search results."""
        results = []
        for template in self.templates:
            score = template.get('mock_score', 0.5)
            if score >= threshold:
                results.append({
                    'template_id': template['id'],
                    'score': score,
                    'description': template.get('description', '')
                })
        # Sort by score descending
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:limit]
    
    async def get_statistics(self) -> Dict[str, Any]:
        return {
            'total_templates': len(self.templates),
            'collection_name': 'mock_collection'
        }


class MockDomainAdapter:
    """Mock domain adapter for testing."""
    
    def __init__(self, templates: Dict[str, Dict[str, Any]]):
        self.templates = templates
    
    def get_template_by_id(self, template_id: str) -> Optional[Dict[str, Any]]:
        return self.templates.get(template_id)
    
    def get_domain_config(self) -> Dict[str, Any]:
        return {'domain_name': 'test'}


class MockChildAdapter:
    """Mock child intent adapter for testing."""
    
    def __init__(self, name: str, templates: List[Dict[str, Any]]):
        self.name = name
        self._templates = {t['id']: t for t in templates}
        self.template_store = MockTemplateStore(templates)
        self.domain_adapter = MockDomainAdapter(self._templates)
        self.get_relevant_context_called = False
        self.last_query = None
    
    async def get_relevant_context(
        self, 
        query: str, 
        api_key: Optional[str] = None,
        collection_name: Optional[str] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        self.get_relevant_context_called = True
        self.last_query = query
        return [{
            "content": f"Results from {self.name}",
            "metadata": {
                "source": self.name,
                "adapter": self.name
            },
            "confidence": 0.9
        }]


class MockAdapterManager:
    """Mock adapter manager for testing."""
    
    def __init__(self, adapters: Dict[str, MockChildAdapter]):
        self.adapters = adapters
    
    async def get_adapter(self, adapter_name: str) -> Optional[MockChildAdapter]:
        return self.adapters.get(adapter_name)


class MockEmbeddingClient:
    """Mock embedding client for testing."""
    
    def __init__(self, dimension: int = 768):
        self.dimension = dimension
        self.initialized = True
    
    async def embed_query(self, query: str) -> List[float]:
        # Return a mock embedding
        return [0.1] * self.dimension
    
    async def initialize(self):
        self.initialized = True


@pytest.fixture
def hr_templates():
    """HR database templates."""
    return [
        {
            'id': 'hr_employees_by_dept',
            'description': 'List employees by department',
            'nl_examples': [
                'Show me employees in Engineering',
                'List all employees by department',
                'Who works in the Sales department?'
            ],
            'mock_score': 0.85,
            'sql': 'SELECT * FROM employees WHERE department = :dept'
        },
        {
            'id': 'hr_salary_report',
            'description': 'Get salary statistics',
            'nl_examples': [
                'What is the average salary?',
                'Show salary statistics',
                'Get salary report'
            ],
            'mock_score': 0.7,
            'sql': 'SELECT AVG(salary) FROM employees'
        }
    ]


@pytest.fixture
def ev_templates():
    """Electric vehicle database templates."""
    return [
        {
            'id': 'ev_count_by_make',
            'description': 'Count electric vehicles by make',
            'nl_examples': [
                'How many Teslas are registered?',
                'Count vehicles by make',
                'Show EV counts per manufacturer'
            ],
            'mock_score': 0.9,
            'sql': 'SELECT make, COUNT(*) FROM vehicles GROUP BY make'
        },
        {
            'id': 'ev_by_city',
            'description': 'Find EVs in a city',
            'nl_examples': [
                'Show electric vehicles in Seattle',
                'Find EVs registered in Portland',
                'List vehicles by city'
            ],
            'mock_score': 0.65,
            'sql': 'SELECT * FROM vehicles WHERE city = :city'
        }
    ]


@pytest.fixture
def movie_templates():
    """Movie database templates."""
    return [
        {
            'id': 'movie_by_year',
            'description': 'Find movies by year',
            'nl_examples': [
                'Show movies from 2020',
                'What movies were released in 2019?',
                'List films by year'
            ],
            'mock_score': 0.75,
            'sql': "db.movies.find({year: :year})"
        },
        {
            'id': 'movie_by_genre',
            'description': 'Find movies by genre',
            'nl_examples': [
                'Show me action movies',
                'Find comedy films',
                'List movies in the horror genre'
            ],
            'mock_score': 0.6,
            'sql': "db.movies.find({genres: :genre})"
        }
    ]


@pytest.fixture
def mock_child_adapters(hr_templates, ev_templates, movie_templates):
    """Create mock child adapters."""
    return {
        'intent-sql-hr': MockChildAdapter('intent-sql-hr', hr_templates),
        'intent-duckdb-ev': MockChildAdapter('intent-duckdb-ev', ev_templates),
        'intent-mongodb-movies': MockChildAdapter('intent-mongodb-movies', movie_templates)
    }


@pytest.fixture
def mock_adapter_manager(mock_child_adapters):
    """Create mock adapter manager."""
    return MockAdapterManager(mock_child_adapters)


@pytest.fixture
def composite_config():
    """Configuration for composite retriever."""
    return {
        'adapter_config': {
            'child_adapters': [
                'intent-sql-hr',
                'intent-duckdb-ev',
                'intent-mongodb-movies'
            ],
            'confidence_threshold': 0.4,
            'max_templates_per_source': 3,
            'parallel_search': True,
            'search_timeout': 5.0,
            'verbose': False
        },
        'embedding': {
            'provider': 'mock'
        }
    }


@pytest.fixture
def multistage_config():
    """Configuration for composite retriever with multi-stage selection enabled."""
    return {
        'adapter_config': {
            'child_adapters': [
                'intent-sql-hr',
                'intent-duckdb-ev',
                'intent-mongodb-movies'
            ],
            'confidence_threshold': 0.4,
            'max_templates_per_source': 3,
            'parallel_search': True,
            'search_timeout': 5.0,
            'verbose': False
        },
        'embedding': {
            'provider': 'mock'
        },
        'composite_retrieval': {
            'reranking': {
                'enabled': True,
                'provider': 'anthropic',
                'top_candidates': 10,
                'weight': 0.4
            },
            'string_similarity': {
                'enabled': True,
                'algorithm': 'jaro_winkler',
                'weight': 0.2,
                'compare_fields': ['description', 'nl_examples'],
                'min_threshold': 0.3,
                'aggregation': 'max'
            },
            'scoring': {
                'embedding_weight': 0.4,
                'normalize_scores': True,
                'tie_breaker': 'embedding'
            },
            'performance': {
                'parallel_rerank': True,
                'cache_rerank_results': True,
                'cache_ttl_seconds': 300
            }
        }
    }


@pytest.fixture
def string_similarity_only_config():
    """Configuration with only string similarity enabled (no reranking)."""
    return {
        'adapter_config': {
            'child_adapters': [
                'intent-sql-hr',
                'intent-duckdb-ev'
            ],
            'confidence_threshold': 0.4,
            'max_templates_per_source': 3,
            'parallel_search': True,
            'search_timeout': 5.0
        },
        'embedding': {
            'provider': 'mock'
        },
        'composite_retrieval': {
            'reranking': {
                'enabled': False
            },
            'string_similarity': {
                'enabled': True,
                'algorithm': 'jaro_winkler',
                'weight': 0.3,
                'compare_fields': ['description', 'nl_examples'],
                'aggregation': 'max'
            },
            'scoring': {
                'embedding_weight': 0.7
            }
        }
    }


@pytest.fixture
def composite_retriever(composite_config, mock_adapter_manager):
    """Create composite retriever for testing."""
    retriever = CompositeIntentRetriever(
        config=composite_config,
        adapter_manager=mock_adapter_manager
    )
    return retriever


class TestCompositeIntentRetrieverInit:
    """Test composite retriever initialization."""
    
    def test_init_requires_child_adapters(self):
        """Test that child_adapters is required."""
        config = {'adapter_config': {}}
        with pytest.raises(ValueError, match="child_adapters is required"):
            CompositeIntentRetriever(config=config)
    
    def test_init_with_valid_config(self, composite_config, mock_adapter_manager):
        """Test initialization with valid config."""
        retriever = CompositeIntentRetriever(
            config=composite_config,
            adapter_manager=mock_adapter_manager
        )
        
        assert retriever.child_adapter_names == [
            'intent-sql-hr',
            'intent-duckdb-ev',
            'intent-mongodb-movies'
        ]
        assert retriever.confidence_threshold == 0.4
        assert retriever.max_templates_per_source == 3
        assert retriever.parallel_search is True


class TestTemplateMatch:
    """Test TemplateMatch dataclass."""
    
    def test_template_match_creation(self):
        """Test creating a TemplateMatch."""
        match = TemplateMatch(
            template_id='test_template',
            source_adapter='test_adapter',
            similarity_score=0.85,
            template_data={'id': 'test_template', 'sql': 'SELECT 1'},
            embedding_text='test query'
        )
        
        assert match.template_id == 'test_template'
        assert match.source_adapter == 'test_adapter'
        assert match.similarity_score == 0.85
        assert match.template_data['sql'] == 'SELECT 1'


class TestCompositeRetrieverInitialize:
    """Test composite retriever initialization."""
    
    @pytest.mark.asyncio
    async def test_initialize_resolves_child_adapters(
        self, composite_retriever, mock_adapter_manager
    ):
        """Test that initialize resolves child adapters."""
        # Mock embedding client
        with patch.object(
            composite_retriever, 
            '_initialize_embedding_client',
            new_callable=AsyncMock
        ):
            composite_retriever.embedding_client = MockEmbeddingClient()
            await composite_retriever._resolve_child_adapters()
        
        assert len(composite_retriever._child_adapters) == 3
        assert 'intent-sql-hr' in composite_retriever._child_adapters
        assert 'intent-duckdb-ev' in composite_retriever._child_adapters
        assert 'intent-mongodb-movies' in composite_retriever._child_adapters
    
    @pytest.mark.asyncio
    async def test_initialize_skips_missing_adapters(
        self, composite_config, mock_adapter_manager
    ):
        """Test that missing adapters are skipped."""
        # Add a non-existent adapter to config
        composite_config['adapter_config']['child_adapters'].append('non-existent')
        
        retriever = CompositeIntentRetriever(
            config=composite_config,
            adapter_manager=mock_adapter_manager
        )
        
        with patch.object(
            retriever, 
            '_initialize_embedding_client',
            new_callable=AsyncMock
        ):
            retriever.embedding_client = MockEmbeddingClient()
            await retriever._resolve_child_adapters()
        
        # Should still have 3 adapters (non-existent one skipped)
        assert len(retriever._child_adapters) == 3


class TestTemplateSearch:
    """Test template search functionality."""
    
    @pytest.mark.asyncio
    async def test_search_single_template_store(
        self, composite_retriever, mock_child_adapters
    ):
        """Test searching a single template store."""
        composite_retriever._child_adapters = mock_child_adapters
        composite_retriever.embedding_client = MockEmbeddingClient()
        
        query_embedding = await composite_retriever.embedding_client.embed_query("test")
        
        matches = await composite_retriever._search_single_template_store(
            'intent-duckdb-ev',
            mock_child_adapters['intent-duckdb-ev'],
            query_embedding
        )
        
        assert len(matches) >= 1
        assert all(isinstance(m, TemplateMatch) for m in matches)
        assert all(m.source_adapter == 'intent-duckdb-ev' for m in matches)
    
    @pytest.mark.asyncio
    async def test_search_all_template_stores(
        self, composite_retriever, mock_child_adapters
    ):
        """Test searching across all template stores."""
        composite_retriever._child_adapters = mock_child_adapters
        composite_retriever.embedding_client = MockEmbeddingClient()
        
        matches = await composite_retriever._search_all_template_stores("test query")
        
        # Should have matches from all 3 adapters
        assert len(matches) >= 3
        
        # Matches should be sorted by score (highest first)
        scores = [m.similarity_score for m in matches]
        assert scores == sorted(scores, reverse=True)
        
        # Should have matches from different adapters
        sources = {m.source_adapter for m in matches}
        assert len(sources) >= 2
    
    @pytest.mark.asyncio
    async def test_search_respects_threshold(
        self, composite_retriever, mock_child_adapters
    ):
        """Test that search respects confidence threshold."""
        composite_retriever._child_adapters = mock_child_adapters
        composite_retriever.embedding_client = MockEmbeddingClient()
        composite_retriever.confidence_threshold = 0.8  # High threshold
        
        matches = await composite_retriever._search_all_template_stores("test query")
        
        # Only templates with score >= 0.8 should be returned
        for match in matches:
            assert match.similarity_score >= 0.8


class TestBestMatchSelection:
    """Test best match selection logic."""
    
    def test_select_best_match_returns_highest_score(self, composite_retriever):
        """Test that best match has highest score."""
        matches = [
            TemplateMatch('t1', 'adapter1', 0.7, {}, ''),
            TemplateMatch('t2', 'adapter2', 0.9, {}, ''),
            TemplateMatch('t3', 'adapter3', 0.8, {}, ''),
        ]
        # Sort as the real implementation would
        matches.sort(key=lambda m: m.similarity_score, reverse=True)
        
        best = composite_retriever._select_best_match(matches)
        
        assert best is not None
        assert best.template_id == 't2'
        assert best.similarity_score == 0.9
    
    def test_select_best_match_returns_none_below_threshold(
        self, composite_retriever
    ):
        """Test that None is returned when all matches are below threshold."""
        composite_retriever.confidence_threshold = 0.9
        
        matches = [
            TemplateMatch('t1', 'adapter1', 0.7, {}, ''),
            TemplateMatch('t2', 'adapter2', 0.8, {}, ''),
        ]
        matches.sort(key=lambda m: m.similarity_score, reverse=True)
        
        best = composite_retriever._select_best_match(matches)
        
        assert best is None
    
    def test_select_best_match_empty_list(self, composite_retriever):
        """Test that None is returned for empty list."""
        best = composite_retriever._select_best_match([])
        assert best is None


class TestQueryRouting:
    """Test query routing to child adapters."""
    
    @pytest.mark.asyncio
    async def test_routes_to_best_matching_adapter(
        self, composite_retriever, mock_child_adapters
    ):
        """Test that query is routed to the adapter with best match."""
        composite_retriever._child_adapters = mock_child_adapters
        composite_retriever.embedding_client = MockEmbeddingClient()
        
        results = await composite_retriever.get_relevant_context("test query")
        
        # Should get results
        assert len(results) >= 1
        
        # The EV adapter has the highest scoring template (0.9)
        # so it should be the one that was called
        ev_adapter = mock_child_adapters['intent-duckdb-ev']
        assert ev_adapter.get_relevant_context_called is True
        assert ev_adapter.last_query == "test query"
        
        # Results should include composite routing metadata
        metadata = results[0].get('metadata', {})
        routing = metadata.get('composite_routing', {})
        assert routing.get('selected_adapter') == 'intent-duckdb-ev'
    
    @pytest.mark.asyncio
    async def test_returns_error_when_no_matches(
        self, composite_config, mock_adapter_manager
    ):
        """Test error response when no templates match."""
        # Create adapters with no templates
        empty_adapters = {
            'empty': MockChildAdapter('empty', [])
        }
        composite_config['adapter_config']['child_adapters'] = ['empty']
        manager = MockAdapterManager(empty_adapters)
        
        retriever = CompositeIntentRetriever(
            config=composite_config,
            adapter_manager=manager
        )
        retriever._child_adapters = empty_adapters
        retriever.embedding_client = MockEmbeddingClient()
        
        results = await retriever.get_relevant_context("test query")
        
        assert len(results) == 1
        assert results[0]['metadata']['error'] == 'no_matching_template'
    
    @pytest.mark.asyncio
    async def test_includes_routing_metadata(
        self, composite_retriever, mock_child_adapters
    ):
        """Test that results include routing metadata."""
        composite_retriever._child_adapters = mock_child_adapters
        composite_retriever.embedding_client = MockEmbeddingClient()
        
        results = await composite_retriever.get_relevant_context("test query")
        
        metadata = results[0].get('metadata', {})
        routing = metadata.get('composite_routing', {})
        
        assert 'selected_adapter' in routing
        assert 'template_id' in routing
        assert 'similarity_score' in routing
        assert 'adapters_searched' in routing
        assert 'total_matches_found' in routing


class TestParallelSearch:
    """Test parallel vs sequential search."""
    
    @pytest.mark.asyncio
    async def test_parallel_search_queries_all_adapters(
        self, composite_retriever, mock_child_adapters
    ):
        """Test that parallel search queries all adapters."""
        composite_retriever._child_adapters = mock_child_adapters
        composite_retriever.embedding_client = MockEmbeddingClient()
        composite_retriever.parallel_search = True
        
        matches = await composite_retriever._search_all_template_stores("test")
        
        # Should have matches from multiple adapters
        sources = {m.source_adapter for m in matches}
        assert len(sources) >= 2
    
    @pytest.mark.asyncio
    async def test_sequential_search_queries_all_adapters(
        self, composite_retriever, mock_child_adapters
    ):
        """Test that sequential search also queries all adapters."""
        composite_retriever._child_adapters = mock_child_adapters
        composite_retriever.embedding_client = MockEmbeddingClient()
        composite_retriever.parallel_search = False
        
        matches = await composite_retriever._search_all_template_stores("test")
        
        # Should have matches from multiple adapters
        sources = {m.source_adapter for m in matches}
        assert len(sources) >= 2


class TestCompositeRetrieverClose:
    """Test composite retriever cleanup."""
    
    @pytest.mark.asyncio
    async def test_close_cleans_up_resources(self, composite_retriever):
        """Test that close cleans up resources."""
        mock_embedding = MockEmbeddingClient()
        mock_embedding.close = AsyncMock()
        composite_retriever.embedding_client = mock_embedding
        
        await composite_retriever.close()
        
        # Should not throw, child adapters are not closed by composite


class TestGetDatasourceName:
    """Test datasource name method."""

    def test_get_datasource_name_returns_composite(self, composite_retriever):
        """Test that datasource name is 'composite'."""
        assert composite_retriever._get_datasource_name() == "composite"


class TestMultiStageConfigurationInit:
    """Test multi-stage selection configuration initialization."""

    def test_multistage_disabled_by_default(self, composite_config, mock_adapter_manager):
        """Test that multi-stage is disabled when not configured."""
        retriever = CompositeIntentRetriever(
            config=composite_config,
            adapter_manager=mock_adapter_manager
        )

        assert retriever.multistage_enabled is False
        assert retriever.reranking_enabled is False
        assert retriever.string_similarity_enabled is False

    def test_multistage_enabled_with_reranking(self, multistage_config, mock_adapter_manager):
        """Test that multi-stage is enabled when reranking is configured."""
        retriever = CompositeIntentRetriever(
            config=multistage_config,
            adapter_manager=mock_adapter_manager
        )

        assert retriever.multistage_enabled is True
        assert retriever.reranking_enabled is True
        assert retriever.reranking_provider == 'anthropic'
        assert retriever.reranking_top_candidates == 10
        assert retriever.reranking_weight == 0.4

    def test_multistage_enabled_with_string_similarity(
        self, multistage_config, mock_adapter_manager
    ):
        """Test that string similarity is configured correctly."""
        retriever = CompositeIntentRetriever(
            config=multistage_config,
            adapter_manager=mock_adapter_manager
        )

        assert retriever.string_similarity_enabled is True
        assert retriever.string_similarity_algorithm == 'jaro_winkler'
        assert retriever.string_similarity_weight == 0.2
        assert 'description' in retriever.string_similarity_fields
        assert 'nl_examples' in retriever.string_similarity_fields

    def test_scoring_weights_configured(self, multistage_config, mock_adapter_manager):
        """Test that scoring weights are configured correctly."""
        retriever = CompositeIntentRetriever(
            config=multistage_config,
            adapter_manager=mock_adapter_manager
        )

        assert retriever.embedding_weight == 0.4
        assert retriever.normalize_scores is True
        assert retriever.tie_breaker == 'embedding'

    def test_string_similarity_only_config(
        self, string_similarity_only_config, mock_adapter_manager
    ):
        """Test configuration with only string similarity enabled."""
        retriever = CompositeIntentRetriever(
            config=string_similarity_only_config,
            adapter_manager=mock_adapter_manager
        )

        assert retriever.multistage_enabled is True
        assert retriever.reranking_enabled is False
        assert retriever.string_similarity_enabled is True
        assert retriever.embedding_weight == 0.7
        assert retriever.string_similarity_weight == 0.3


class TestStringSimilarityScoring:
    """Test string similarity scoring functionality."""

    def test_calculate_string_similarity_with_description(
        self, multistage_config, mock_adapter_manager
    ):
        """Test string similarity calculation with description field."""
        retriever = CompositeIntentRetriever(
            config=multistage_config,
            adapter_manager=mock_adapter_manager
        )

        match = TemplateMatch(
            template_id='test_template',
            source_adapter='test_adapter',
            similarity_score=0.8,
            template_data={
                'description': 'List employees by department',
                'nl_examples': ['Show employees', 'List staff by dept']
            },
            embedding_text='test'
        )

        # Query that should match well
        score = retriever._calculate_string_similarity_score(
            "Show employees in Engineering",
            match
        )

        assert score > 0.0
        assert score <= 1.0

    def test_calculate_string_similarity_with_nl_examples(
        self, multistage_config, mock_adapter_manager
    ):
        """Test string similarity calculation with nl_examples field."""
        retriever = CompositeIntentRetriever(
            config=multistage_config,
            adapter_manager=mock_adapter_manager
        )

        match = TemplateMatch(
            template_id='test_template',
            source_adapter='test_adapter',
            similarity_score=0.8,
            template_data={
                'description': 'Count vehicles',
                'nl_examples': [
                    'How many Teslas are there?',
                    'Count electric vehicles by make'
                ]
            },
            embedding_text='test'
        )

        # Query that should match nl_examples well
        score = retriever._calculate_string_similarity_score(
            "How many Teslas are registered?",
            match
        )

        assert score > 0.5  # Should be a good match

    def test_calculate_string_similarity_no_match(
        self, multistage_config, mock_adapter_manager
    ):
        """Test string similarity with non-matching query."""
        retriever = CompositeIntentRetriever(
            config=multistage_config,
            adapter_manager=mock_adapter_manager
        )

        match = TemplateMatch(
            template_id='test_template',
            source_adapter='test_adapter',
            similarity_score=0.8,
            template_data={
                'description': 'Find movies by genre',
                'nl_examples': ['Show action movies', 'List comedies']
            },
            embedding_text='test'
        )

        # Query that should not match well (no overlapping words)
        score = retriever._calculate_string_similarity_score(
            "Calculate quarterly revenue",
            match
        )

        # Score should be lower for non-matching query
        assert score < 0.7

    def test_calculate_string_similarity_empty_template_data(
        self, multistage_config, mock_adapter_manager
    ):
        """Test string similarity with empty template data."""
        retriever = CompositeIntentRetriever(
            config=multistage_config,
            adapter_manager=mock_adapter_manager
        )

        match = TemplateMatch(
            template_id='test_template',
            source_adapter='test_adapter',
            similarity_score=0.8,
            template_data={},
            embedding_text='test'
        )

        score = retriever._calculate_string_similarity_score("test query", match)

        assert score == 0.0


class TestCombinedScoreCalculation:
    """Test combined score calculation with multi-stage scoring."""

    @pytest.mark.asyncio
    async def test_combined_scores_without_multistage(
        self, composite_retriever, mock_child_adapters
    ):
        """Test that combined scores equal embedding scores when multi-stage disabled."""
        composite_retriever._child_adapters = mock_child_adapters
        composite_retriever.embedding_client = MockEmbeddingClient()

        matches = [
            TemplateMatch('t1', 'adapter1', 0.9, {'description': 'test'}, ''),
            TemplateMatch('t2', 'adapter2', 0.8, {'description': 'test'}, ''),
        ]

        result = await composite_retriever._calculate_combined_scores("test", matches)

        # When multi-stage is disabled, combined_score should equal similarity_score
        for match in result:
            assert match.combined_score == match.similarity_score

    @pytest.mark.asyncio
    async def test_combined_scores_with_string_similarity_only(
        self, string_similarity_only_config, mock_adapter_manager, mock_child_adapters
    ):
        """Test combined score calculation with only string similarity enabled."""
        retriever = CompositeIntentRetriever(
            config=string_similarity_only_config,
            adapter_manager=mock_adapter_manager
        )
        retriever._child_adapters = mock_child_adapters
        retriever.embedding_client = MockEmbeddingClient()

        matches = [
            TemplateMatch(
                't1', 'adapter1', 0.9,
                {'description': 'Show employees', 'nl_examples': ['List staff']},
                ''
            ),
            TemplateMatch(
                't2', 'adapter2', 0.85,
                {'description': 'Show customers', 'nl_examples': ['List clients']},
                ''
            ),
        ]

        result = await retriever._calculate_combined_scores("Show employees", matches)

        # Combined scores should be populated
        for match in result:
            assert match.combined_score is not None
            assert match.string_similarity_score is not None
            assert match.rerank_score == 0.0  # Reranking disabled, defaults to 0.0

    @pytest.mark.asyncio
    async def test_combined_scores_sorted_correctly(
        self, string_similarity_only_config, mock_adapter_manager
    ):
        """Test that matches are sorted by combined score."""
        retriever = CompositeIntentRetriever(
            config=string_similarity_only_config,
            adapter_manager=mock_adapter_manager
        )
        retriever.embedding_client = MockEmbeddingClient()

        # Create matches where string similarity should change the order
        matches = [
            TemplateMatch(
                't1', 'adapter1', 0.85,  # Lower embedding score
                {'description': 'Show all employees in department', 'nl_examples': ['List employees']},
                ''
            ),
            TemplateMatch(
                't2', 'adapter2', 0.9,  # Higher embedding score
                {'description': 'Show all customers', 'nl_examples': ['List customers']},
                ''
            ),
        ]

        result = await retriever._calculate_combined_scores("Show employees", matches)

        # Results should be sorted by combined_score descending
        scores = [m.combined_score for m in result]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_scoring_details_populated(
        self, string_similarity_only_config, mock_adapter_manager
    ):
        """Test that scoring details are populated for debugging."""
        retriever = CompositeIntentRetriever(
            config=string_similarity_only_config,
            adapter_manager=mock_adapter_manager
        )
        retriever.embedding_client = MockEmbeddingClient()

        matches = [
            TemplateMatch(
                't1', 'adapter1', 0.85,
                {'description': 'Test template', 'nl_examples': ['Test query']},
                ''
            ),
        ]

        result = await retriever._calculate_combined_scores("Test query", matches)

        assert len(result) == 1
        details = result[0].scoring_details

        assert 'embedding_score' in details
        assert 'embedding_weight' in details
        assert 'string_similarity_score' in details
        assert 'string_similarity_weight' in details
        assert 'combined_score' in details


class TestMultiStageBestMatchSelection:
    """Test best match selection with multi-stage scoring."""

    def test_select_best_match_uses_combined_score(
        self, multistage_config, mock_adapter_manager
    ):
        """Test that best match selection uses combined_score when multi-stage enabled."""
        retriever = CompositeIntentRetriever(
            config=multistage_config,
            adapter_manager=mock_adapter_manager
        )

        # Create matches where combined_score differs from embedding score
        matches = [
            TemplateMatch('t1', 'adapter1', 0.9, {}, ''),  # High embedding
            TemplateMatch('t2', 'adapter2', 0.85, {}, ''),  # Lower embedding
        ]

        # Set combined scores to reverse the order
        matches[0].combined_score = 0.7  # Lower combined
        matches[1].combined_score = 0.8  # Higher combined

        # Sort by combined score (as _calculate_combined_scores would)
        matches.sort(key=lambda m: m.combined_score or 0, reverse=True)

        best = retriever._select_best_match(matches)

        # Should select t2 based on combined_score
        assert best.template_id == 't2'

    def test_select_best_match_threshold_uses_combined_score(
        self, multistage_config, mock_adapter_manager
    ):
        """Test that threshold comparison uses combined_score when multi-stage enabled."""
        retriever = CompositeIntentRetriever(
            config=multistage_config,
            adapter_manager=mock_adapter_manager
        )
        retriever.confidence_threshold = 0.5

        match = TemplateMatch('t1', 'adapter1', 0.9, {}, '')  # High embedding
        match.combined_score = 0.4  # But low combined score

        best = retriever._select_best_match([match])

        # Should return None because combined_score < threshold
        assert best is None


class TestTemplateMatchDataclass:
    """Test enhanced TemplateMatch dataclass with multi-stage fields."""

    def test_template_match_has_multistage_fields(self):
        """Test that TemplateMatch has multi-stage scoring fields."""
        match = TemplateMatch(
            template_id='test',
            source_adapter='adapter',
            similarity_score=0.9,
            template_data={},
            embedding_text=''
        )

        # Multi-stage fields should exist with default values
        assert match.rerank_score is None
        assert match.string_similarity_score is None
        assert match.combined_score is None
        assert match.scoring_details == {}

    def test_template_match_multistage_fields_settable(self):
        """Test that multi-stage fields can be set."""
        match = TemplateMatch(
            template_id='test',
            source_adapter='adapter',
            similarity_score=0.9,
            template_data={},
            embedding_text=''
        )

        match.rerank_score = 0.95
        match.string_similarity_score = 0.78
        match.combined_score = 0.89
        match.scoring_details = {'test': 'value'}

        assert match.rerank_score == 0.95
        assert match.string_similarity_score == 0.78
        assert match.combined_score == 0.89
        assert match.scoring_details == {'test': 'value'}


class TestMultiStageQueryRouting:
    """Test query routing with multi-stage selection."""

    @pytest.mark.asyncio
    async def test_routing_includes_multistage_metadata(
        self, string_similarity_only_config, mock_adapter_manager, mock_child_adapters
    ):
        """Test that routing includes multi-stage scoring metadata."""
        retriever = CompositeIntentRetriever(
            config=string_similarity_only_config,
            adapter_manager=mock_adapter_manager
        )
        retriever._child_adapters = {
            'intent-sql-hr': mock_child_adapters['intent-sql-hr'],
            'intent-duckdb-ev': mock_child_adapters['intent-duckdb-ev']
        }
        retriever.embedding_client = MockEmbeddingClient()

        results = await retriever.get_relevant_context("Show employees")

        assert len(results) >= 1

        metadata = results[0].get('metadata', {})
        routing = metadata.get('composite_routing', {})

        # Should include multi-stage scoring info
        assert 'multistage_scoring' in routing
        multistage = routing['multistage_scoring']
        assert multistage['enabled'] is True
        assert 'combined_score' in multistage
        assert 'embedding_score' in multistage
        assert 'string_similarity_score' in multistage


class TestRerankerIntegration:
    """Test reranker integration (with mocking)."""

    @pytest.mark.asyncio
    async def test_rerank_candidates_returns_empty_when_disabled(
        self, composite_retriever
    ):
        """Test that rerank_candidates returns empty dict when disabled."""
        composite_retriever.reranking_enabled = False

        matches = [
            TemplateMatch('t1', 'adapter1', 0.9, {}, ''),
        ]

        result = await composite_retriever._rerank_candidates("test", matches)

        assert result == {}

    @pytest.mark.asyncio
    async def test_rerank_candidates_caches_results(
        self, multistage_config, mock_adapter_manager
    ):
        """Test that rerank results are cached."""
        retriever = CompositeIntentRetriever(
            config=multistage_config,
            adapter_manager=mock_adapter_manager
        )

        # Mock the reranker
        mock_reranker = MagicMock()
        mock_reranker.rerank = AsyncMock(return_value=[
            {'index': 0, 'score': 0.95}
        ])
        retriever._reranker = mock_reranker

        matches = [
            TemplateMatch('t1', 'adapter1', 0.9, {'description': 'test'}, ''),
        ]

        # First call
        await retriever._rerank_candidates("test query", matches)

        # Second call with same query and matches
        await retriever._rerank_candidates("test query", matches)

        # Reranker should only be called once due to caching
        assert mock_reranker.rerank.call_count == 1


class TestRoutingStatisticsWithMultistage:
    """Test get_routing_statistics with multi-stage configuration."""

    @pytest.mark.asyncio
    async def test_statistics_include_multistage_config(
        self, multistage_config, mock_adapter_manager, mock_child_adapters
    ):
        """Test that statistics include multi-stage configuration."""
        # Import the implementation class for this test
        from retrievers.implementations.composite.composite_intent_retriever import (
            CompositeIntentRetriever as CompositeImpl
        )

        retriever = CompositeImpl(
            config=multistage_config,
            adapter_manager=mock_adapter_manager
        )
        retriever._child_adapters = mock_child_adapters

        stats = await retriever.get_routing_statistics()

        assert 'multistage_selection' in stats
        ms = stats['multistage_selection']

        assert ms['enabled'] is True
        assert ms['reranking']['enabled'] is True
        assert ms['reranking']['provider'] == 'anthropic'
        assert ms['string_similarity']['enabled'] is True
        assert ms['string_similarity']['algorithm'] == 'jaro_winkler'

