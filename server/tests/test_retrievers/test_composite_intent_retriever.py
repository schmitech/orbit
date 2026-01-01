"""
Tests for the CompositeIntentRetriever class

Tests the composite retriever's ability to:
- Search across multiple child adapter template stores
- Find the best matching template
- Route queries to the correct child adapter
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
            'mock_score': 0.85,
            'sql': 'SELECT * FROM employees WHERE department = :dept'
        },
        {
            'id': 'hr_salary_report',
            'description': 'Get salary statistics',
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
            'mock_score': 0.9,
            'sql': 'SELECT make, COUNT(*) FROM vehicles GROUP BY make'
        },
        {
            'id': 'ev_by_city',
            'description': 'Find EVs in a city',
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
            'mock_score': 0.75,
            'sql': "db.movies.find({year: :year})"
        },
        {
            'id': 'movie_by_genre',
            'description': 'Find movies by genre',
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

