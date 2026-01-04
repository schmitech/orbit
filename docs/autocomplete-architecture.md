# Autocomplete Architecture

## Overview

The autocomplete system provides query suggestions based on `nl_examples` from intent adapter templates. As users type in the chat input, they receive real-time suggestions that help discover available queries without guessing the exact phrasing.

**Key Features:**
- Query suggestions from intent template `nl_examples`
- Fuzzy matching with Levenshtein and Jaro-Winkler algorithms
- Redis caching with in-memory fallback
- Configurable via `config.yaml`
- Fast C library implementations with pure Python fallback
- Composite adapter aggregation support
- Adapter capability-based activation

## Architecture Components

### 1. Core Services

#### AutocompleteService (`server/services/autocomplete_service.py`)

Central service for fetching and filtering autocomplete suggestions.

**Responsibilities:**
- Extract `nl_examples` from adapter templates
- Cache examples in Redis or memory
- Filter and rank suggestions based on query
- Support multiple matching algorithms
- Aggregate suggestions from composite adapters

**Key Methods:**
```python
async def get_suggestions(query: str, adapter_name: str, limit: int = 5) -> List[AutocompleteSuggestion]
async def _get_adapter_nl_examples(adapter_name: str) -> List[str]
async def _get_composite_examples(adapter) -> List[str]
def _filter_and_rank(examples: List[str], query: str, limit: int) -> List[AutocompleteSuggestion]
async def invalidate_cache(adapter_name: Optional[str] = None) -> None
```

**AutocompleteSuggestion Structure:**
```python
@dataclass
class AutocompleteSuggestion:
    text: str       # The suggestion text
    score: float    # Relevance score (higher = better match)
```

#### FuzzyMatcher (`server/services/autocomplete_service.py`)

Provides string similarity algorithms for fuzzy matching.

**Algorithms:**
| Algorithm | Use Case | Performance |
|-----------|----------|-------------|
| `substring` | Exact substring matching | Fastest, no typo tolerance |
| `levenshtein` | Edit distance matching | Handles typos, moderate speed |
| `jaro_winkler` | Prefix-optimized matching | Best for autocomplete, handles typos |

**Key Methods:**
```python
@staticmethod
def levenshtein_distance(s1: str, s2: str) -> int
@staticmethod
def levenshtein_similarity(s1: str, s2: str) -> float
@staticmethod
def jaro_similarity(s1: str, s2: str) -> float
@staticmethod
def jaro_winkler_similarity(s1: str, s2: str, prefix_weight: float = 0.1) -> float
@staticmethod
def substring_match(query: str, text: str) -> tuple[bool, float]
```

**C Library Optimization:**
The service uses fast C implementations when available:
- `python-Levenshtein` (10-100x faster)
- `jarowinkler` (50-100x faster)

Falls back to pure Python if libraries are not installed.

### 2. API Layer

#### Autocomplete Endpoint (`server/routes/routes_configurator.py`)

```
GET /v1/autocomplete?q={query}&limit={limit}
```

**Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `q` | string | Yes | - | Query prefix (min 3 characters) |
| `limit` | int | No | 5 | Max suggestions (1-10) |

**Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| `X-API-Key` | Yes | API key identifying the adapter |

**Response:**
```json
{
  "suggestions": [
    {"text": "Show me movies from 2020"},
    {"text": "Show me action movies"},
    {"text": "Show me movies by director"}
  ],
  "query": "show me"
}
```

**Error Handling:**
- Returns empty suggestions on error (non-blocking)
- Logs warnings for debugging
- Gracefully handles missing adapters

### 3. Client Integration

#### useAutocomplete Hook (`clients/chat-app/src/hooks/useAutocomplete.ts`)

React hook for fetching and managing autocomplete suggestions.

**Features:**
- 300ms debounce to reduce API calls
- AbortController for request cancellation
- Keyboard navigation state management
- Automatic cleanup on unmount

**Interface:**
```typescript
interface UseAutocompleteResult {
  suggestions: AutocompleteSuggestion[];
  isLoading: boolean;
  selectedIndex: number;
  setSelectedIndex: (index: number) => void;
  selectNext: () => void;
  selectPrevious: () => void;
  clearSuggestions: () => void;
}

function useAutocomplete(
  query: string,
  options?: UseAutocompleteOptions
): UseAutocompleteResult
```

#### MessageInput Component (`clients/chat-app/src/components/MessageInput.tsx`)

Integrates autocomplete dropdown with keyboard navigation.

**Keyboard Controls:**
| Key | Action |
|-----|--------|
| `ArrowDown` | Select next suggestion |
| `ArrowUp` | Select previous suggestion |
| `Tab` / `Enter` | Accept selected suggestion |
| `Escape` | Dismiss suggestions |

### 4. Adapter Capability

#### AdapterCapabilities (`server/adapters/capabilities.py`)

```python
@dataclass
class AdapterCapabilities:
    supports_autocomplete: bool = False  # Enable autocomplete from nl_examples
```

**Enabling Autocomplete:**

In adapter YAML configuration:
```yaml
- name: "intent-mongodb-mflix"
  capabilities:
    supports_autocomplete: true
```

Autocomplete is automatically enabled for adapters with names starting with `intent-` or `composite-`.

## Configuration

### Server Configuration (`config/config.yaml`)

```yaml
autocomplete:
  enabled: true  # Master switch

  # Query matching settings
  min_query_length: 3  # Minimum characters before fetching
  max_suggestions: 5   # Maximum suggestions returned

  # Caching configuration
  cache:
    use_redis: true           # Use Redis (falls back to memory if unavailable)
    ttl_seconds: 1800         # 30 minutes cache TTL
    redis_key_prefix: "autocomplete:"

  # Fuzzy matching configuration
  fuzzy_matching:
    enabled: true             # Enable fuzzy/approximate matching
    algorithm: "jaro_winkler" # Options: substring, levenshtein, jaro_winkler
    threshold: 0.75           # Minimum similarity score (0.0-1.0)
    max_candidates: 100       # Performance guard for fuzzy matching
```

### Client Configuration

Environment variable in `.env.local`:
```
VITE_ENABLE_AUTOCOMPLETE=true
```

Or via CLI config injection:
```javascript
window.ORBIT_CHAT_CONFIG = {
  enableAutocomplete: true
};
```

## Data Flow

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   User Types    │────▶│  useAutocomplete │────▶│  300ms Debounce │
│   "show me"     │     │      Hook        │     │                 │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                          │
                                                          ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│    Dropdown     │◀────│   Parse JSON     │◀────│  GET /v1/auto   │
│    Renders      │     │    Response      │     │    complete     │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                          │
                        ┌─────────────────────────────────┘
                        ▼
            ┌───────────────────────┐
            │  AutocompleteService  │
            │   get_suggestions()   │
            └───────────┬───────────┘
                        │
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
    ┌───────────┐ ┌───────────┐ ┌───────────┐
    │   Redis   │ │  Memory   │ │  Adapter  │
    │   Cache   │ │   Cache   │ │ Templates │
    └───────────┘ └───────────┘ └───────────┘
                        │
                        ▼
            ┌───────────────────────┐
            │   FuzzyMatcher        │
            │  _filter_and_rank()   │
            └───────────────────────┘
                        │
                        ▼
            ┌───────────────────────┐
            │  Top N Suggestions    │
            │  Sorted by Score      │
            └───────────────────────┘
```

## Caching Strategy

### Cache Hierarchy

1. **Redis Cache (Primary)**
   - Distributed across server instances
   - Automatic TTL expiration
   - Persists across server restarts
   - Key format: `autocomplete:{adapter_name}`

2. **Memory Cache (Fallback)**
   - Per-instance cache
   - Used when Redis unavailable
   - Automatic TTL expiration
   - Lost on server restart

### Cache Invalidation

```python
# Invalidate specific adapter
await autocomplete_service.invalidate_cache("intent-mongodb-mflix")

# Invalidate all adapters
await autocomplete_service.invalidate_cache()
```

**When to Invalidate:**
- After updating intent templates
- After adding/removing `nl_examples`
- After changing adapter configuration

## Scoring Algorithm

### Substring Matching (Default)

```python
if query in example:
    if example.startswith(query):
        score = 100.0  # Perfect prefix match
    else:
        position = example.find(query)
        score = 50.0 - position * 0.5  # Penalize later positions
```

### Fuzzy Matching (Levenshtein/Jaro-Winkler)

```python
# Calculate similarity against whole string
similarity = algorithm(query, example)

# Also check against individual words
for word in example.split():
    word_sim = algorithm(query, word)
    similarity = max(similarity, word_sim * 0.9)

if similarity >= threshold:
    score = similarity * 100

# Also include exact substring matches
elif query in example:
    score = 80 if prefix_match else 60 - position * 0.5
```

### Final Score Adjustment

```python
# Prefer shorter, more concise suggestions
score -= len(example) * 0.05
```

## Performance Considerations

### Query Limits

| Setting | Value | Purpose |
|---------|-------|---------|
| `min_query_length` | 3 | Prevent noisy short queries |
| `max_suggestions` | 5 | Limit response size |
| `max_candidates` | 100 | Limit fuzzy comparison count |

### Debouncing

Client-side 300ms debounce prevents excessive API calls while typing.

### Caching

- 30-minute default TTL
- Templates rarely change, so cache hit rate is high
- Redis reduces database/adapter queries

### C Library Usage

When `Levenshtein` and `jarowinkler` packages are installed:
- 10-100x faster similarity calculations
- Significant improvement for fuzzy matching

## Logging and Debugging

### Enable Debug Logging

In `config/config.yaml`:
```yaml
logging:
  level: "DEBUG"
```

### Log Output Examples

```
[Autocomplete] get_suggestions called: query='show me', adapter=composite-intent-retriever, limit=5
[Autocomplete] Cache hit: 45 examples for composite-intent-retriever
[Autocomplete] Filtering 45 examples with algorithm=jaro_winkler, query='show me', limit=5
[Autocomplete] Found 12 matches, returning top 5
[Autocomplete] Top scores: [95.2, 89.1, 85.7]
[Autocomplete] Returning 5 suggestions for 'show me' in 2.34ms
```

### Startup Configuration Log

```
🔍 Autocomplete: enabled
  Min query length: 3 chars
  Max suggestions: 5
  Cache: Redis (TTL: 1800s)
  Fuzzy matching: jaro_winkler (threshold: 0.75)
```

## Dependencies

### Server-Side

```toml
# install/dependencies.toml [default]
"Levenshtein==0.27.3",  # Fast C-based Levenshtein distance
"jarowinkler==2.0.1",   # Fast C-based Jaro-Winkler similarity
```

### Client-Side

No additional dependencies required.

## Testing

### Unit Tests

Located at `server/tests/test_services/test_autocomplete_service.py`

**Test Coverage:**
- FuzzyMatcher algorithms (Levenshtein, Jaro, Jaro-Winkler, substring)
- AutocompleteService initialization
- Suggestion filtering and ranking
- Memory and Redis caching
- Cache invalidation
- Edge cases (Unicode, special characters, long strings)
- C library availability detection

**Running Tests:**
```bash
cd server
source ../venv/bin/activate
python -m pytest tests/test_services/test_autocomplete_service.py -v
```

## Security Considerations

1. **API Key Required**: Autocomplete endpoint requires valid API key
2. **No Sensitive Data**: Only returns template examples, not user data
3. **Rate Limiting**: Subject to standard API rate limits
4. **Input Validation**: Query minimum length enforced

## Troubleshooting

### No Suggestions Returned

1. Check if autocomplete is enabled in `config.yaml`
2. Verify adapter has `supports_autocomplete: true`
3. Ensure adapter has templates with `nl_examples`
4. Check query meets minimum length (3 chars)
5. Review debug logs for errors

### Slow Response Times

1. Ensure C libraries are installed (`pip install Levenshtein jarowinkler`)
2. Check Redis connection
3. Reduce `max_candidates` if fuzzy matching is slow
4. Consider using `substring` algorithm instead of fuzzy

### Cache Not Working

1. Verify Redis is enabled and connected
2. Check `cache.use_redis` setting
3. Review Redis connection logs
4. Ensure `ttl_seconds` is set correctly

## Future Enhancements

1. **Personalization**: Rank suggestions based on user's query history
2. **Analytics**: Track which suggestions are selected
3. **Synonyms**: Match queries against synonym mappings
4. **Multi-language**: Support suggestions in detected language
5. **Partial Word Matching**: Match incomplete words at end of query
