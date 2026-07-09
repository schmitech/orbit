# Chunking Techniques — Implementation Status

This document tracks a broader toolkit of text-chunking techniques against what ORBIT actually implements today. For the strategies ORBIT ships, see `docs/chunking/chunking-architecture.md` and `server/services/file_processing/chunking/`.

## Implemented

| # | Technique | ORBIT Equivalent |
|---|-----------|------------------|
| 1 | Fixed Chunking | `FixedSizeChunker` (`fixed_chunker.py`) — character or token-based fixed-size splitting |
| 2 | Overlapping Chunking | `overlap` parameter on `FixedSizeChunker`, `TokenChunker`, and `SemanticChunker` |
| 3 | Semantic Chunking | `SemanticChunker` simple mode (`semantic_chunker.py`) — sentence-grouped chunks |
| 4 | Recursive Character Chunking | `RecursiveChunker` (`recursive_chunker.py`) — paragraphs → sentences → words |
| 6 | Advanced Semantic Chunking | `SemanticChunker` advanced mode — sentence-transformer similarity + Savitzky-Golay filtering. Note: this uses embedding similarity rather than the NER/entity-overlap approach below, but serves the same purpose (semantically coherent chunks) |
| 8 | Paragraph Chunking | Covered by `RecursiveChunker`'s paragraph level (first rule in `RecursiveRules.default()`), and by `MarkdownHeaderChunker`'s paragraph fallback |
| 10 | Token Based Chunking | `TokenChunker` (`token_chunker.py`), plus token-based mode (`use_tokens=True`) on `FixedSizeChunker` |
| 11 | Document Structure-Aware Chunking | `MarkdownHeaderChunker` (`markdown_header_chunker.py`) — splits on markdown headers (H1-H6) before falling back to paragraphs/sentences/words |
| 12 | Sliding Window Chunking | Achieved via the `overlap` parameter on `FixedSizeChunker`/`TokenChunker` (fixed step, fixed window) |

## Pending

### 5. Agentic Chunking

Uses AI models or rule-based systems to intelligently determine content-based split locations.

```python
from transformers import pipeline
from nltk.tokenize import sent_tokenize

def agentic_chunking(text, model_name="facebook/bart-large-mnli", max_chunk_size=700):
    """Use AI to determine optimal chunk boundaries"""
    classifier = pipeline("zero-shot-classification", model=model_name)
    sentences = sent_tokenize(text)
    chunks = []
    current_chunk = ""
    current_topic = None
    for sentence in sentences:
        # Classify sentence topic
        candidate_labels = ["introduction", "main_content", "conclusion", "transition"]
        result = classifier(sentence, candidate_labels)
        sentence_topic = result['labels'][0]
        # Check if we should start a new chunk
        if (current_topic and current_topic != sentence_topic) or \
           (len(current_chunk + sentence) > max_chunk_size):
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = sentence + " "
            current_topic = sentence_topic
        else:
            current_chunk += sentence + " "
            current_topic = sentence_topic
    if current_chunk:
        chunks.append(current_chunk.strip())
    return chunks

# Usage
chunks = agentic_chunking(text, max_chunk_size=700)
```

**What it does:** Uses machine learning models that learn from content to intelligently determine likely chunk boundaries where topics change or according to content structure.

**When to use:**
- Processing high-value content where quality is paramount
- When processing a complex document with multiple topics
- When you have processing resources for AI
- Processing research or academic texts

**Pros:** Intelligent context-aware chunking.

**Cons:** Computationally expensive, requires ML models, and is slower in processing.

---

### 7. Context Enriched Chunking

Provides some metadata and context information for each chunk making it more usable and searchable.

```python
import hashlib
from datetime import datetime
from nltk.tokenize import sent_tokenize

def context_enriched_chunking(text, chunk_size=1000, document_metadata=None):
    """Create chunks with rich context metadata"""
    document_metadata = document_metadata or {}
    sentences = sent_tokenize(text)
    chunks = []
    for i in range(0, len(sentences), 3):  # Group sentences
        sentence_group = sentences[i:i+3]
        chunk_text = " ".join(sentence_group)
        if len(chunk_text) > chunk_size:
            chunk_text = chunk_text[:chunk_size]
        # Create rich chunk object
        chunk = {
            'text': chunk_text,
            'chunk_id': hashlib.md5(chunk_text.encode()).hexdigest()[:8],
            'position': i // 3,
            'sentence_count': len(sentence_group),
            'char_count': len(chunk_text),
            'word_count': len(chunk_text.split()),
            'created_at': datetime.now().isoformat(),
            'source_document': document_metadata.get('filename') if document_metadata else None,
            'preceding_context': sentences[max(0, i-1)] if i > 0 else None,
            'following_context': sentences[min(len(sentences)-1, i+3)] if i+3 < len(sentences) else None,
        }
        chunks.append(chunk)
    return chunks

# Usage
metadata = {'filename': 'document.pdf', 'author': 'John Doe'}
chunks = context_enriched_chunking(text, chunk_size=600, document_metadata=metadata)
```

**What it does:** Creates chunks with rich metadata including positional information, contextual information, and processing statistics to support improved retrieval and analysis.

**When to use:**
- RAG systems with a need for rich provenance
- Document management systems
- Auditing and versioning systems
- Search and retrieval applications with complexity

**Pros:** Rich metadata lends itself to better retrieval options and is beneficial for debugging and analysis.

**Cons:** Higher storage requirement and data structures are more complex.

---

### 9. Recursive Sentence Chunking

This strategy places a priority on sentence boundaries, and recursively processes any content that cannot fit size-wise. Distinct from `RecursiveChunker`, which prioritizes paragraphs first — this technique starts at the sentence level and falls back to clause-level splitting (on `,`/`;`) for a single sentence too long to fit.

```python
import re
from nltk.tokenize import sent_tokenize

def recursive_sentence_chunking(text, max_chunk_size=1000, min_chunk_size=100):
    """Recursively chunk text at sentence boundaries"""
    def split_sentences(text, max_size, min_size):
        if len(text) <= max_size:
            return [text]
        sentences = sent_tokenize(text)
        if len(sentences) == 1:
            # Single long sentence - split at clause boundaries
            clauses = re.split(r'[,;]', sentences[0])
            chunks = []
            current_chunk = ""
            for clause in clauses:
                test_chunk = current_chunk + clause if current_chunk else clause
                if len(test_chunk) <= max_size:
                    current_chunk = test_chunk
                else:
                    if current_chunk and len(current_chunk) >= min_size:
                        chunks.append(current_chunk.strip())
                    current_chunk = clause
            if current_chunk:
                chunks.append(current_chunk.strip())
            return chunks
        # Multiple sentences - group them
        chunks = []
        current_chunk = ""
        for sentence in sentences:
            test_chunk = current_chunk + " " + sentence if current_chunk else sentence
            if len(test_chunk) <= max_size:
                current_chunk = test_chunk
            else:
                if current_chunk and len(current_chunk) >= min_size:
                    chunks.append(current_chunk.strip())
                if len(sentence) > max_size:
                    chunks.extend(split_sentences(sentence, max_size, min_size))
                    current_chunk = ""
                else:
                    current_chunk = sentence
        if current_chunk and len(current_chunk) >= min_size:
            chunks.append(current_chunk.strip())
        return chunks
    return split_sentences(text, max_chunk_size, min_chunk_size)

# Usage
chunks = recursive_sentence_chunking(text, max_chunk_size=700, min_chunk_size=50)
```

**What it does:** Intelligent text handling by prioritizing sentence boundaries and recursive processing of anything that cannot fit size-wise, with fallback strategies for complex sentences.

**When to use:**
- When you need high quality text processing when the integrity of sentences is important
- Academic/technical documents
- Legal documents
- Content where grammatical structure could change the meaning

**Pros:** Great balance of structural preservation and size control.

**Cons:** More complex logic, and chance of receiving very small chunks of text with complex content.

---

### 13. Hierarchical Chunking

This advanced output provides hierarchical chunks at various levels of granularity to enable multi-scale analysis and retrieval of text.

```python
from typing import List, Dict, Any
from nltk.tokenize import sent_tokenize

def hierarchical_chunking(text: str, levels: List[int] = [2000, 1000, 500]) -> Dict[str, Any]:
    """Create hierarchical chunks at multiple levels"""
    def create_level_chunks(text: str, chunk_size: int, level_name: str) -> List[Dict]:
        sentences = sent_tokenize(text)
        chunks = []
        current_chunk = ""
        chunk_id = 0
        for sentence in sentences:
            test_chunk = current_chunk + " " + sentence if current_chunk else sentence
            if len(test_chunk) <= chunk_size:
                current_chunk = test_chunk
            else:
                if current_chunk:
                    chunks.append({
                        'text': current_chunk.strip(),
                        'level': level_name,
                        'chunk_id': f"{level_name}_{chunk_id}",
                        'char_count': len(current_chunk),
                        'sentence_count': len(sent_tokenize(current_chunk))
                    })
                    chunk_id += 1
                current_chunk = sentence
        if current_chunk:
            chunks.append({
                'text': current_chunk.strip(),
                'level': level_name,
                'chunk_id': f"{level_name}_{chunk_id}",
                'char_count': len(current_chunk),
                'sentence_count': len(sent_tokenize(current_chunk))
            })
        return chunks

    hierarchy = {
        'source_text': text,
        'levels': {},
        'relationships': []
    }
    level_names = ['coarse', 'medium', 'fine']
    for i, chunk_size in enumerate(levels):
        level_name = level_names[i] if i < len(level_names) else f'level_{i}'
        hierarchy['levels'][level_name] = create_level_chunks(text, chunk_size, level_name)
    # Create parent-child relationships
    for i in range(len(levels) - 1):
        parent_level = level_names[i]
        child_level = level_names[i + 1]
        for parent_chunk in hierarchy['levels'][parent_level]:
            parent_text = parent_chunk['text']
            children = []
            for child_chunk in hierarchy['levels'][child_level]:
                if child_chunk['text'] in parent_text:
                    children.append(child_chunk['chunk_id'])
            hierarchy['relationships'].append({
                'parent': parent_chunk['chunk_id'],
                'children': children,
                'relationship_type': f"{parent_level}_to_{child_level}"
            })
    return hierarchy

# Usage
hierarchy = hierarchical_chunking(text, levels=[1500, 800, 400])
```

**What it does:** Provides numerous levels of chunks with parent-child relationships to allow both broad context but also fine-grained detail in one system.

**When to use:**
- Your analysis of documents is complex and requires multiple levels of detail
- You are working with a multi-scale search system (able to query for broad overview and more specific detail)
- You are designing a summarization system that requires context at a hierarchical level
- Research applications that analyze text at various levels of granularity
- A need for both global and specific local context is needed

**Pros:** Multi-level context; flexible options for retrieval; complex analysis; preservation of parent-child relationships.

**Cons:** Complex data structure; potentially larger storage demands; more computational overhead needs.

---

### 14. Density-Based Chunking

This method evaluates information density and fullness within text so that comparable density sections can be clustered together.

```python
import re
from nltk.tokenize import sent_tokenize

def density_based_chunking(text: str, target_density: float = 0.7, max_chunk_size: int = 1000):
    """Chunk text based on information density"""
    def calculate_density(text_segment: str) -> float:
        """Calculate information density of a text segment"""
        words = re.findall(r'\b\w+\b', text_segment.lower())
        if not words:
            return 0.0
        unique_words = len(set(words))
        total_words = len(words)
        avg_word_length = sum(len(word) for word in words) / total_words
        lexical_diversity = unique_words / total_words
        density = (lexical_diversity * avg_word_length) / 10  # Normalized
        return min(density, 1.0)

    sentences = sent_tokenize(text)
    chunks = []
    current_chunk = ""
    current_density = 0.0
    for sentence in sentences:
        test_chunk = current_chunk + " " + sentence if current_chunk else sentence
        test_density = calculate_density(test_chunk)
        density_diff = abs(test_density - target_density)
        current_diff = abs(current_density - target_density)
        if len(test_chunk) <= max_chunk_size and (density_diff <= current_diff or len(current_chunk) < 100):
            current_chunk = test_chunk
            current_density = test_density
        else:
            if current_chunk:
                chunks.append({
                    'text': current_chunk.strip(),
                    'density': current_density,
                    'char_count': len(current_chunk),
                    'density_score': f"{current_density:.3f}"
                })
            current_chunk = sentence
            current_density = calculate_density(sentence)
    if current_chunk:
        chunks.append({
            'text': current_chunk.strip(),
            'density': current_density,
            'char_count': len(current_chunk),
            'density_score': f"{current_density:.3f}"
        })
    return chunks

# Usage
chunks = density_based_chunking(text, target_density=0.6, max_chunk_size=800)
```

**What it does:** Evaluates the information density of segments of text and clusters text with similar densities, ensuring text diversity in replication and consistency in meeting information density characteristic.

**When to use:**
- When dealing with mixed text density
- For academic and technical documents that have both dense and sparse sections
- When curating content that you care about density and fullness
- For research purposes, when examining complexity of text
- To provide consistency in cognitive load across chunks

**Pros:** Consistency in information levels, works well with mixed content, intelligent organization.

**Cons:** Density is complex to calculate, might not adhere to guided semantic boundaries, more computationally intensive.

---

### 15. Adaptive Threshold Chunking

This technique dynamically adjusts chunking thresholds based on content characteristics and context.

```python
import re
import statistics
from typing import Dict
from nltk.tokenize import sent_tokenize

def adaptive_threshold_chunking(text: str, base_chunk_size: int = 1000, adaptation_factor: float = 0.3):
    """Dynamically adapt chunk size based on content characteristics"""
    def analyze_text_characteristics(text_segment: str) -> Dict[str, float]:
        sentences = sent_tokenize(text_segment)
        words = text_segment.split()
        return {
            'avg_sentence_length': statistics.mean([len(s.split()) for s in sentences]) if sentences else 0,
            'sentence_count': len(sentences),
            'avg_word_length': statistics.mean([len(w) for w in words]) if words else 0,
            'punctuation_density': len(re.findall(r'[.!?;:]', text_segment)) / len(text_segment) if text_segment else 0
        }

    def calculate_adaptive_threshold(characteristics: Dict[str, float], base_size: int) -> int:
        sentence_factor = min(characteristics['avg_sentence_length'] / 15, 2.0)
        word_factor = min(characteristics['avg_word_length'] / 5, 1.5)
        punctuation_factor = min(characteristics['punctuation_density'] * 100, 1.0)
        complexity_score = (sentence_factor + word_factor + punctuation_factor) / 3
        adjustment = 1 + (complexity_score - 1) * adaptation_factor
        return int(base_size * adjustment)

    sentences = sent_tokenize(text)
    chunks = []
    current_chunk = ""
    window_start = 0
    while window_start < len(sentences):
        window_end = min(window_start + 5, len(sentences))
        window_text = " ".join(sentences[window_start:window_end])
        local_characteristics = analyze_text_characteristics(window_text)
        adaptive_size = calculate_adaptive_threshold(local_characteristics, base_chunk_size)
        for i in range(window_start, len(sentences)):
            test_chunk = current_chunk + " " + sentences[i] if current_chunk else sentences[i]
            if len(test_chunk) <= adaptive_size:
                current_chunk = test_chunk
            else:
                if current_chunk:
                    chunk_characteristics = analyze_text_characteristics(current_chunk)
                    chunks.append({
                        'text': current_chunk.strip(),
                        'adaptive_size_used': adaptive_size,
                        'actual_size': len(current_chunk),
                        'complexity_score': (local_characteristics['avg_sentence_length'],
                                            local_characteristics['avg_word_length'],
                                            local_characteristics['punctuation_density']),
                        'characteristics': chunk_characteristics
                    })
                current_chunk = sentences[i]
                window_start = i
                break
        else:
            window_start = len(sentences)
        if current_chunk and window_start >= len(sentences):
            chunks.append({
                'text': current_chunk.strip(),
                'adaptive_size_used': adaptive_size,
                'actual_size': len(current_chunk),
                'complexity_score': 0,
                'characteristics': analyze_text_characteristics(current_chunk)
            })
    return chunks

# Usage
chunks = adaptive_threshold_chunking(text, base_chunk_size=800, adaptation_factor=0.3)
```

**What it does:** Adapts the chunk size dynamically, dependent on richness of content (e.g., complexity, sentence structure, and other textual characteristics), so that chunks are optimally sized for the content.

**When to use:**
- When processing various content types in a single pipeline
- When the content complexity varies widely from one document to the next
- In adaptive systems where content types may be unknown
- In research-oriented contexts of text complexity
- In systems that require different content speculating an optimal chunk size

**Pros:** Intelligent adaptation to size, can process diverse content appropriately, optimally suited for varied content types.

**Cons:** Complex implementation, computationally intensive, requires parameter tuning for adaptive nature.

---

## Suggested Implementation Sequence

Ordered by effort-to-value ratio, given ORBIT's existing chunker infrastructure (`TextChunker` base class, `RecursiveRules`/`RecursiveLevel` hierarchical splitting, and the `chunking_strategy` if/elif dispatch in `file_processing_service.py:_init_chunker`):

1. **Context Enriched Chunking (7)** — Lowest effort, highest immediate value. No new chunker class needed: `Chunk.metadata` already exists on every strategy, so this is a post-processing pass applied after any existing chunker runs (add `preceding_context`/`following_context`/word counts into `metadata`). Works across all 5 current strategies at once instead of being its own strategy.
2. **Recursive Sentence Chunking (9)** — Medium effort. Same pattern used for `MarkdownHeaderChunker`: a thin `RecursiveChunker` subclass with a custom `RecursiveRules` that puts sentences ahead of paragraphs, plus a clause-level (`,`/`;`) fallback level for the rare oversized single sentence. No changes to the base `RecursiveChunker` needed beyond what already exists.
3. **Hierarchical Chunking (13)** — Medium-high effort, biggest design decision of the pending set. The current `Chunk` dataclass and `chunk_index` model a flat list, not a tree — this needs either a new output shape (parent/child chunk IDs in metadata) or a wrapper that runs the same chunker at multiple `chunk_size` values and links results by containment. Worth scoping deliberately before starting, since it's the one technique that doesn't fit the existing single-chunker/single-output contract.
4. **Density-Based Chunking (14)** — Medium effort, uncertain ROI. Straightforward to implement as a standalone chunker (lexical diversity + word length heuristic), but the "when to use" cases are narrower (mixed-density academic/technical text) and the density heuristic itself is unproven relative to ORBIT's current retrieval quality bar. Prototype and evaluate before committing to production use.
5. **Adaptive Threshold Chunking (15)** — Higher effort, narrow benefit over `RecursiveChunker`'s existing size/merge logic. The complexity-scoring formula needs tuning per content type, which cuts against ORBIT's "works out of the box, no required deps" design principle for the other chunkers.
6. **Agentic Chunking (5)** — Highest cost, lowest priority. Requires a classifier or LLM call per sentence, which is slow and expensive at file-upload scale (ORBIT already has an LLM inference pipeline, but running it per-sentence during chunking would be a very different cost profile than the current chunkers, all of which are dependency-optional and run in milliseconds). Only worth it if a specific customer need for topic-aware chunking outweighs the added latency/cost.

## Choosing the Right Chunking Strategy

- **For RAG systems:** Context Enriched Chunking or Hierarchical Chunking give the best retrieval-quality upside among the pending techniques; Overlapping Chunking (already implemented) covers most of what's needed today.
- **For LLM integrated applications:** Token Based Chunking (already implemented as `TokenChunker`) remains the standard for minimizing token costs.
- **For document analysis:** Advanced Semantic Chunking (already implemented as `SemanticChunker` advanced mode) and Document Structure-Aware Chunking (already implemented as `MarkdownHeaderChunker`) cover the highest-quality cases; Agentic Chunking is the only one left unimplemented here, and it's the most expensive.
- **For structured content:** Paragraph Chunking and Recursive Character Chunking (already implemented) cover most structured/mixed content; Document Structure-Aware Chunking adds markdown-header awareness on top.
- **For research and analysis:** Hierarchical Chunking and Density-Based Chunking remain pending and are the ones to prioritize for multi-scale or density-sensitive analysis use cases.
- **For adaptive systems:** Adaptive Threshold Chunking is pending and the lowest-priority item for this use case today.

It is important to remember that chunking is often the basis of your NLP pipeline; time spent determining the correct type of chunk and setting it up properly for your specific use case is well worth the cost and effort when you consider potential downstream applications.
