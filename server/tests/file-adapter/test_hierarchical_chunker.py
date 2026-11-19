"""
Tests for HierarchicalChunker (2-level default and N-level generalization).
"""

import sys
from collections import defaultdict
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

from services.file_processing.chunking.hierarchical_chunker import HierarchicalChunker

TEXT = (
    "Section sentence A. Sentence B. Sentence C.\n\n"
    "Section sentence D. Sentence E.\n\n"
    "Section sentence F. Sentence G. Sentence H.\n\n"
    "Section sentence I. Sentence J. Sentence K. Sentence L."
)


def _normalize(text: str) -> str:
    return text.replace(' ', '').replace('\n', '')


def test_two_level_default_is_unchanged():
    chunker = HierarchicalChunker(parent_chunk_size=40, leaf_chunk_size=10)
    chunks = chunker.chunk_text(TEXT, "file1", {})

    levels = {c.metadata.get('level') for c in chunks}
    assert levels == {'parent', 'leaf'}

    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids))

    parents = [c for c in chunks if c.metadata['level'] == 'parent']
    leaves = [c for c in chunks if c.metadata['level'] == 'leaf']
    parent_ids = {p.chunk_id for p in parents}

    # Top-level parents never carry a hierarchy_parent_id of their own.
    assert all('hierarchy_parent_id' not in p.db_metadata for p in parents)

    for leaf in leaves:
        assert leaf.db_metadata['hierarchy_parent_id'] in parent_ids


def test_short_text_yields_one_parent_one_leaf():
    chunks = HierarchicalChunker().chunk_text("Just a short sentence.", "file2", {})
    assert len(chunks) == 2
    assert [c.metadata['level'] for c in chunks] == ['parent', 'leaf']


def test_three_level_hierarchy():
    chunker = HierarchicalChunker(parent_chunk_size=80, intermediate_chunk_sizes=[30], leaf_chunk_size=10)
    chunks = chunker.chunk_text(TEXT, "file1", {})

    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids)), "duplicate ids across all levels"

    parents = [c for c in chunks if c.metadata.get('level') == 'parent']
    leaves = [c for c in chunks if c.metadata.get('level') == 'leaf']
    assert {c.metadata.get('level') for c in chunks} == {'parent', 'leaf'}

    roots = [p for p in parents if 'hierarchy_parent_id' not in p.db_metadata]
    mids = [p for p in parents if 'hierarchy_parent_id' in p.db_metadata]
    assert roots and mids and leaves

    root_ids = {r.chunk_id for r in roots}
    mid_ids = {m.chunk_id for m in mids}

    for mid in mids:
        assert mid.db_metadata['hierarchy_parent_id'] in root_ids
    for leaf in leaves:
        assert leaf.db_metadata['hierarchy_parent_id'] in mid_ids

    # Each level's own children reconstruct that chunk's text exactly.
    mids_by_root = defaultdict(list)
    for m in mids:
        mids_by_root[m.db_metadata['hierarchy_parent_id']].append(m.text)
    for r in roots:
        assert _normalize(''.join(mids_by_root[r.chunk_id])) == _normalize(r.text)

    leaves_by_mid = defaultdict(list)
    for leaf in leaves:
        leaves_by_mid[leaf.db_metadata['hierarchy_parent_id']].append(leaf.text)
    for m in mids:
        assert _normalize(''.join(leaves_by_mid[m.chunk_id])) == _normalize(m.text)


def test_four_level_hierarchy_chunk_index_is_globally_sequential():
    chunker = HierarchicalChunker(parent_chunk_size=200, intermediate_chunk_sizes=[80, 30], leaf_chunk_size=10)
    chunks = chunker.chunk_text(TEXT, "file1", {})

    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    assert [c.chunk_id for c in chunks] == [f"file1_chunk_{i}" for i in range(len(chunks))]


def test_rejects_increasing_intermediate_sizes():
    with pytest.raises(ValueError):
        HierarchicalChunker(parent_chunk_size=100, intermediate_chunk_sizes=[200], leaf_chunk_size=10)


def test_rejects_intermediate_smaller_than_leaf():
    with pytest.raises(ValueError):
        HierarchicalChunker(parent_chunk_size=100, intermediate_chunk_sizes=[50], leaf_chunk_size=60)
