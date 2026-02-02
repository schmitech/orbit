# 15 Chunking Techniques

## 1. Fixed Chunking

Fixed chunking is the most straightforward way to process text by cutting it into a predetermined size of fixed chunks of text; only size matters, and any structure to the text or meaning is ignored.

```python
def fixed_chunking(text, chunk_size=1000):
    """Split text into fixed-size chunks"""
    chunks = []
    for i in range(0, len(text), chunk_size):
        chunk = text[i:i + chunk_size]
        chunks.append(chunk)
    return chunks

# Usage
text = "Your long document text here..."
chunks = fixed_chunking(text, chunk_size=500)
```

**What it does:** It cuts the text into equally sized chunks based on the character count of the text, completely ignoring both language boundaries based on sentences and the resulting semantic meaning of the sentences.

### When to consider this technique

- Prototyping and testing purposes, quickly and easily.
- When time/speed is greater than any kind of quality processing.
- To process simple applications where one does not care about retaining the context in the sentence being chunked.
- Large scale batch processing where one cares to have consistent chunking.

**Pros:** Fast, simple, and predictable sizing of chunks.

**Cons:** Breaks sentences, destroys semantic coherence.

---

## 2. Overlapping Chunking

This approach generates chunks that share a text portion at their edges, allowing important context to be retained in adjacent chunks.

```python
def overlapping_chunking(text, chunk_size=1000, overlap=200):
    """Split text with overlapping windows"""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        if end >= len(text):
            break
        start = end - overlap
    return chunks

# Usage
chunks = overlapping_chunking(text, chunk_size=800, overlap=150)
```

**What it does:** It generates chunks that share a portion of text at the edges, allowing for essential context to be repeated on each chunk edge.

### When to use

- In RAG systems where the context must be repeated across multiple chunks
- In search applications, if you believe the response could span across two boundary chunks
- Document Q&A systems
- When you don't want to lose essential context at the split across chunks

**Pros:** Provides context across chunks, minimizes information loss through the chunk boundaries as it will have the same text.

**Cons:** Increased footprint, increased information being processed (should process the same data point multiple times).

---

## 3. Semantic Chunking

Semantic chunking utilizes NLP methods to recognize meaningful breaks in a text (typically at sentence or paragraph boundaries).

```python
import nltk
from nltk.tokenize import sent_tokenize

def semantic_chunking(text, max_chunk_size=1000):
    """Split text at sentence boundaries while respecting size limits"""
    sentences = sent_tokenize(text)
    chunks = []
    current_chunk = ""
    for sentence in sentences:
        if len(current_chunk + sentence) <= max_chunk_size:
            current_chunk += sentence + " "
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = sentence + " "
    if current_chunk:
        chunks.append(current_chunk.strip())
    return chunks

# Usage
chunks = semantic_chunking(text, max_chunk_size=600)
```

**What it does:** Preserves the natural boundaries in the language by splitting the chunks on sentences (while keeping to target chunk sizes).

### When to use

- General purpose text processing where readability matters
- Education content processing (for students)
- News article processing
- Content processing where sentence integrity matters

**Pros:** Preserves sentence integrity, more readable chunks.

**Cons:** Variable chunk sizes, needs sentence detection after splitting.

---

## 4. Recursive Character Chunking

This sophisticated method attempts latent splits in a preferred order to put one split as a last resort.

```python
import re

def recursive_character_chunking(text, chunk_size=1000, separators=None):
    """Recursively split text using different separators"""
    if separators is None:
        separators = ["\n\n", "\n", ". ", " ", ""]

    def _split_text(text, separators, chunk_size):
        if len(text) <= chunk_size:
            return [text]
        for separator in separators:
            if separator in text:
                parts = text.split(separator)
                chunks = []
                current_chunk = ""
                for part in parts:
                    test_chunk = current_chunk + separator + part if current_chunk else part
                    if len(test_chunk) <= chunk_size:
                        current_chunk = test_chunk
                    else:
                        if current_chunk:
                            chunks.append(current_chunk)
                        current_chunk = part
                if current_chunk:
                    chunks.append(current_chunk)
                # Recursively split large chunks
                final_chunks = []
                for chunk in chunks:
                    if len(chunk) > chunk_size:
                        final_chunks.extend(_split_text(chunk, separators[1:], chunk_size))
                    else:
                        final_chunks.append(chunk)
                return final_chunks
        # If no separator works, split by characters
        return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]

    return _split_text(text, separators, chunk_size)

# Usage
chunks = recursive_character_chunking(text, chunk_size=800)
```

**What it does:** Tries to split text at the natural boundaries (paragraphs, sentences, words) and uses character split as a last resort.

### When to use

- If you are processing high-quality text and find it important to retain some structure
- If your document/text contains mixed content (e.g., structured and unstructured)
- For professional/official document processing
- If you want to achieve the best balance between directed chunk size and coherence of meaning

**Pros:** Intelligent split sequence, preserves document structure.

**Cons:** More complex to set up and slower to process.

---

## 5. Agentic Chunking

This method employs AI models or rule-based systems to intelligently determine content-based split locations.

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

### When to use

- Processing high-value content where quality is paramount
- When processing a complex document with multiple topics
- When you have processing resources for AI
- Processing research or academic texts

**Pros:** Intelligent context-aware chunking.

**Cons:** Computationally expensive, requires ML models, and is slower in processing.

---

## 6. Advanced Semantic Chunking

This method integrates multiple NLP capabilities (such as named entity recognition, topic modeling, and syntactic analysis) to produce rather sophisticated chunking.

```python
import spacy

def advanced_semantic_chunking(text, max_chunk_size=1000, similarity_threshold=0.5):
    """Advanced chunking using multiple NLP features"""
    nlp = spacy.load("en_core_web_sm")
    doc = nlp(text)
    sentences = [sent.text for sent in doc.sents]
    chunks = []
    current_chunk = []
    current_entities = set()
    for i, sentence in enumerate(sentences):
        sent_doc = nlp(sentence)
        sent_entities = {ent.label_ for ent in sent_doc.ents}
        # Calculate entity overlap with current chunk
        if current_entities:
            overlap = len(current_entities.intersection(sent_entities)) / len(current_entities)
        else:
            overlap = 1.0
        chunk_text = " ".join(current_chunk + [sentence])
        # Start new chunk if low similarity or size exceeded
        if overlap < similarity_threshold or len(chunk_text) > max_chunk_size:
            if current_chunk:
                chunks.append(" ".join(current_chunk))
            current_chunk = [sentence]
            current_entities = sent_entities
        else:
            current_chunk.append(sentence)
            current_entities.update(sent_entities)
    if current_chunk:
        chunks.append(" ".join(current_chunk))
    return chunks

# Example
chunks = advanced_semantic_chunking(text, max_chunk_size=800)
```

**What it does:** Analyzes named entities, topics, and semantic relationships to form chunks that encapsulate semantic coherence and entity connections.

### When to use

- Professional document review
- Processing legal or medical documentation
- Processing research manuscripts
- When the relationships of entities are significant for your usage

**Pros:** Maintains semantic coherence and entity connections, better quality chunks.

**Cons:** Due to multiple or advanced NLP libraries and processing overheads, very resource and processor intensive.

---

## 7. Context Enriched Chunking

This method provides some metadata and context information for each chunk making it more usable and searchable.

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

### When to use

- RAG systems with a need for rich provenance
- Document management systems
- Auditing and versioning systems
- Search and retrieval applications with complexity

**Pros:** Rich metadata lends itself to better retrieval options and is beneficial for debugging and analysis.

**Cons:** Higher storage requirement and data structures are more complex.

---

## 8. Paragraph Chunking

This approach honors paragraph structure and clusters similar paragraphs together with maximum size restrictions.

```python
import re
from nltk.tokenize import sent_tokenize

def paragraph_chunking(text, max_chunk_size=1000):
    """Split text at paragraph boundaries"""
    # Split by paragraph breaks (double newlines)
    paragraphs = re.split(r'\n\s*\n', text)
    chunks = []
    current_chunk = ""
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        test_chunk = current_chunk + "\n\n" + paragraph if current_chunk else paragraph
        if len(test_chunk) <= max_chunk_size:
            current_chunk = test_chunk
        else:
            if current_chunk:
                chunks.append(current_chunk)
            # If single paragraph is too large, split it further
            if len(paragraph) > max_chunk_size:
                sentences = sent_tokenize(paragraph)
                temp_chunk = ""
                for sentence in sentences:
                    if len(temp_chunk + sentence) <= max_chunk_size:
                        temp_chunk += sentence + " "
                    else:
                        if temp_chunk:
                            chunks.append(temp_chunk.strip())
                        temp_chunk = sentence + " "
                if temp_chunk:
                    chunks.append(temp_chunk.strip())
                current_chunk = ""
            else:
                current_chunk = paragraph
    if current_chunk:
        chunks.append(current_chunk)
    return chunks

# Usage
chunks = paragraph_chunking(text, max_chunk_size=800)
```

**What it does:** Preserves paragraph structure by splitting at natural paragraph boundaries while honoring size restrictions.

### When to use

- Structured documents (e.g. articles, reports, books)
- Content where paragraph structure has meaning
- Educational materials and documentation
- Blog posts and other web content processing

**Pros:** Preserves document structure and logical flow of the document.

**Cons:** Inconsistency in chunk size may result in very small chunks or very large chunks.

---

## 9. Recursive Sentence Chunking

This strategy places a priority on sentence boundaries, and recursively processes any content that cannot fit size-wise.

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

### When to use

- When you need high quality text processing when the integrity of sentences is important
- Academic/technical documents
- Legal documents
- Content where grammatical structure could change the meaning

**Pros:** Great balance of structural preservation and size control.

**Cons:** More complex logic, and chance of receiving very small chunks of text with complex content.

---

## 10. Token Based Chunking

This method divides the text into text chunks based on token count and not character count, which is critical for any application involving language models.

```python
import tiktoken

def token_based_chunking(text, max_tokens=1000, model="gpt-3.5-turbo", overlap_tokens=0):
    """Split text based on token count for LLM processing"""
    try:
        encoding = tiktoken.encoding_for_model(model)
    except Exception:
        encoding = tiktoken.get_encoding("cl100k_base")  # Default encoding
    tokens = encoding.encode(text)
    chunks = []
    start = 0
    while start < len(tokens):
        end = start + max_tokens
        chunk_tokens = tokens[start:end]
        chunk_text = encoding.decode(chunk_tokens)
        chunks.append({
            'text': chunk_text,
            'token_count': len(chunk_tokens),
            'start_token': start,
            'end_token': min(end, len(tokens))
        })
        if end >= len(tokens):
            break
        start = end - overlap_tokens if overlap_tokens > 0 else end
    return chunks

# Alternative: Simple token counting without tiktoken
def simple_token_chunking(text, max_tokens=1000):
    """Simple approximation of token-based chunking"""
    max_chars = max_tokens * 4  # Rough approximation: 1 token ≈ 4 characters
    return fixed_chunking(text, chunk_size=max_chars)

# Usage
chunks = token_based_chunking(text, max_tokens=500, model="gpt-4")
```

**What it does:** It chunks your text based on how actual language models interpret token structure and limits so that you can create text based on their window context.

### When to use

- Integrating directly with OpenAI or other LLM APIs
- Creating RAG systems using LLM token-limited models
- Reducing cost with token-based pricing models
- Creating your own model with precise control of the input size

**Pros:** Perfect integration for LLMs, precise token control and cost effective.

**Cons:** Must use tokenization libraries and then implement them differently for each model.

---

## 11. Document Structure-Aware Chunking

This method takes advantage of a document's structure, such as headers, sections, and any form of markup in order to build coherent chunks that follow the document's hierarchy.

```python
import re
from typing import List, Dict

def document_structure_chunking(text: str, max_chunk_size: int = 1000) -> List[Dict]:
    """Chunk text based on document structure markers"""
    structure_markers = [
        (r'^# .+', 'h1'),           # Markdown H1
        (r'^## .+', 'h2'),          # Markdown H2
        (r'^### .+', 'h3'),        # Markdown H3
        (r'^\d+\.\s+', 'numbered'), # Numbered sections
        (r'^\* .+', 'bullet'),      # Bullet points
        (r'\n\n', 'paragraph')      # Paragraph breaks
    ]
    chunks = []
    lines = text.split('\n')
    current_chunk = []
    current_level = None
    for line in lines:
        line_type = None
        for pattern, level in structure_markers:
            if re.match(pattern, line):
                line_type = level
                break
        if line_type and line_type in ['h1', 'h2', 'h3', 'numbered']:
            if current_chunk and len('\n'.join(current_chunk)) > 50:
                chunks.append({
                    'text': '\n'.join(current_chunk).strip(),
                    'structure_level': current_level,
                    'char_count': len('\n'.join(current_chunk))
                })
            current_chunk = [line]
            current_level = line_type
        else:
            current_chunk.append(line)
        if len('\n'.join(current_chunk)) > max_chunk_size:
            if len(current_chunk) > 1:
                chunks.append({
                    'text': '\n'.join(current_chunk[:-1]).strip(),
                    'structure_level': current_level,
                    'char_count': len('\n'.join(current_chunk[:-1]))
                })
                current_chunk = [current_chunk[-1]]
    if current_chunk:
        chunks.append({
            'text': '\n'.join(current_chunk).strip(),
            'structure_level': current_level,
            'char_count': len('\n'.join(current_chunk))
        })
    return chunks

# Usage
chunks = document_structure_chunking(text, max_chunk_size=800)
```

**What it does:** It takes advantage of the document structure such as headers, labelled sections, and markup, in order to build meaningful chunks that follow the logical structure of the content.

### When to use

- When processing structured documents such as technical manuals, wikis, and documentation
- When processing content with markup such as Markdown or HTML
- When processing academic papers and research documents
- When processing a legal document that has labelled sections
- When processing any content in which hierarchy is important to the understanding of the document text

**Pros:** Built-in logical document flow, preserves contextual relationship, effective for structured content.

**Cons:** Relies on structured input, has variable size chunks, less effective for unstructured text.

---

## 12. Sliding Window Chunking

This method utilizes a systematic sliding window technique to create chunks, guaranteeing uniform coverage of the entire document.

```python
def sliding_window_chunking(text: str, window_size: int = 1000, step_size: int = 500):
    """Create chunks using a sliding window approach"""
    chunks = []
    text_length = len(text)
    position = 0
    chunk_id = 0
    while position < text_length:
        end_position = min(position + window_size, text_length)
        chunk_text = text[position:end_position]
        if end_position < text_length:
            last_space = chunk_text.rfind(' ')
            if last_space > window_size * 0.8:
                chunk_text = chunk_text[:last_space]
                end_position = position + last_space
        chunks.append({
            'text': chunk_text,
            'chunk_id': chunk_id,
            'start_pos': position,
            'end_pos': end_position,
            'window_size': len(chunk_text),
            'overlap_with_previous': max(0, (position + window_size) - end_position) if chunk_id > 0 else 0
        })
        position += step_size
        chunk_id += 1
        if end_position >= text_length:
            break
    return chunks

# Usage
chunks = sliding_window_chunking(text, window_size=800, step_size=400)
```

**What it does:** Systematically moves a fixed-size window across the text, while keeping steps consistent to guarantee predictable overlaps and comprehensive coverage.

### When to use

- Systematic text analyses where uniform coverage is important
- Textual features with time-series-like analysis
- Research applications where statistical consistency is important
- When you want to know exactly where overlaps will occur
- Large-scale text processing where uniformity matters

**Pros:** Predictable and systematic, consistent coverage, adequate for statistical analyses, predictable overlap.

**Cons:** May not respect sentence boundaries, may create spontaneous splitting of segments, overhead of computational processing when you make steps small.

---

## 13. Hierarchical Chunking

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

### When to use

- Your analysis of documents is complex and requires multiple levels of detail
- You are working with a multi-scale search system (able to query for broad overview and more specific detail)
- You are designing a summarization system that requires context at a hierarchical level
- Research applications that analyze text at various levels of granularity
- A need for both global and specific local context is needed

**Pros:** Multi-level context; flexible options for retrieval; complex analysis; preservation of parent-child relationships.

**Cons:** Complex data structure; potentially larger storage demands; more computational overhead needs.

---

## 14. Density-Based Chunking

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

### When to use

- When dealing with mixed text density
- For academic and technical documents that have both dense and sparse sections
- When curating content that you care about density and fullness
- For research purposes, when examining complexity of text
- To provide consistency in cognitive load across chunks

**Pros:** Consistency in information levels, works well with mixed content, intelligent organization.

**Cons:** Density is complex to calculate, might not adhere to guided semantic boundaries, more computationally intensive.

---

## 15. Adaptive Threshold Chunking

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

### When to use

- When processing various content types in a single pipeline
- When the content complexity varies widely from one document to the next
- In adaptive systems where content types may be unknown
- In research-oriented contexts of text complexity
- In systems that require different content speculating an optimal chunk size

**Pros:** Intelligent adaptation to size, can process diverse content appropriately, optimally suited for varied content types.

**Cons:** Complex implementation, computationally intensive, requires parameter tuning for adaptive nature.

---

## Choosing the Right Chunking Strategy

The selection of chunking techniques depends on a variety of factors.

- **For RAG systems:** The best retrieval quality outcomes will be seen from using Overlapping Chunking, Context Enriched Chunking, or Hierarchical Chunking.

- **For LLM integrated applications:** When using an API, Token Based Chunking provides a standard chunking technique that is optimal for minimizing costs associated with tokens.

- **For document analysis:** To obtain the highest quality results, the best chunking techniques are Advanced Semantic Chunking, Agentic Chunking, or Document Structure Aware Chunking.

- **For simpler applications:** Simple applications can make use of Fixed Chunking or Semantic Chunking to achieve decent quality without introducing too much complexity.

- **For structured content:** If your content is of some structured form, the ability of paragraph chunking, recursive character chunking, or document structure aware chunking to maintain structure is more effective.

- **For research and analysis:** The systematic aspect of Hierarchical Chunking, Density-Based Chunking, or Sliding Window Chunking has its value in qualitative research and analysis.

- **For adaptive systems:** Adaptive Threshold Chunking handles a diverse set of content types intelligently.

It is important to remember that chunking is often the basis of your NLP pipeline; time spent determining the correct type of chunk and setting it up properly for your specific use case is well worth the cost and effort when you consider potential downstream applications.

Despite the current context or task, there is a chunking approach that belongs to the modern-day NLP toolkit, and which is the best fit for your specific situation depends on the context-type and desired qualities related to the output (quality, performance, computational resources, and type of content). With the variety of approaches, the future of your text-processing tasks is not limited.

---

*Source: The Ultimate Text Chunking Toolkit: 15 Methods with Python Code | by Harish K | Data Science Collective | Medium*

https://medium.com/data-science-collective/the-ultimate-text-chunking-toolkit-15-methods-with-python-code-9ef9d8f6a898