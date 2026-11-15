"""
Tests for AbstractVectorRetriever._resolve_collection_name, the shared
collection/index-name fallback chain (adapter_config['collection'] else
datasource_config['collection']) hoisted out of ChromaRetriever and
QdrantRetriever's near-identical __init__ logic (Phase 6 of
docs/roadmap/retrievers-implementations-cleanup.md).
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from retrievers.implementations.vector.chroma_retriever import ChromaRetriever
from retrievers.implementations.vector.qdrant_retriever import QdrantRetriever


def _config(datasource_key: str, datasource_overrides: dict, adapter_config: dict | None = None):
    config = {
        "datasources": {
            datasource_key: {
                "type": datasource_key,
                **datasource_overrides,
            }
        },
        "embedding": {"enabled": False},
        "general": {},
    }
    if adapter_config is not None:
        config["adapter_config"] = adapter_config
    return config


class TestChromaCollectionResolution:
    def test_adapter_config_takes_precedence(self):
        config = _config(
            "chroma",
            {"collection": "datasource_collection"},
            adapter_config={"collection": "adapter_collection"},
        )
        retriever = ChromaRetriever(config=config)
        assert retriever.collection_name == "adapter_collection"

    def test_falls_back_to_datasource_config(self):
        config = _config("chroma", {"collection": "datasource_collection"})
        retriever = ChromaRetriever(config=config)
        assert retriever.collection_name == "datasource_collection"

    def test_none_when_neither_configured(self):
        config = _config("chroma", {})
        retriever = ChromaRetriever(config=config)
        assert retriever.collection_name is None


class TestQdrantCollectionResolution:
    def test_adapter_config_takes_precedence(self):
        config = _config(
            "qdrant",
            {"collection": "datasource_collection"},
            adapter_config={"collection": "adapter_collection"},
        )
        retriever = QdrantRetriever(config=config)
        assert retriever.collection_name == "adapter_collection"

    def test_falls_back_to_datasource_config(self):
        config = _config("qdrant", {"collection": "datasource_collection"})
        retriever = QdrantRetriever(config=config)
        assert retriever.collection_name == "datasource_collection"

    def test_none_when_neither_configured(self):
        config = _config("qdrant", {})
        retriever = QdrantRetriever(config=config)
        assert retriever.collection_name is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
