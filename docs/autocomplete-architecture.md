# Autocomplete Architecture

## Overview

The autocomplete system provides query suggestions based on `nl_examples` from intent adapter templates. As users type in the chat input, they receive real-time suggestions that help discover available queries without guessing the exact phrasing.

Conversational adapters with no retriever templates of their own (e.g. `simple-chat`) can also opt in: autocomplete then draws on `capabilities.routing_examples` from the skills reachable via that adapter's `auto_routable_skills`/`available_skills` (the same phrases the [automatic skill router](adapters/auto-skill-intent-detection.md) matches against), merged with any template examples.

**Key Features:**
- Query suggestions from intent template `nl_examples`
- Query suggestions from skill `routing_examples` (auto skill routing phrases)
- Fuzzy matching with Levenshtein and Jaro-Winkler algorithms
- Distributed caching via ORBIT's shared cache provider (SQLite, Redis, or Memcached), with in-memory fallback
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
- Collect `routing_examples` from skills reachable via `auto_routable_skills`/`available_skills`
- Cache examples (templates + skill phrases, merged) via the configured cache provider, or in-memory
- Filter and rank suggestions based on query
- Support multiple matching algorithms
- Aggregate suggestions from composite adapters

**Key Methods:**
```python
async def get_suggestions(query: str, adapter_name: str, limit: int = 5) -> List[AutocompleteSuggestion]
async def _get_adapter_nl_examples(adapter_name: str) -> List[str]
async def _get_composite_examples(adapter) -> List[str]
async def _get_skill_routing_examples(adapter_name: str) -> List[str]
def _filter_and_rank(examples: List[str], query: str, limit: int) -> List[AutocompleteSuggestion]
async def invalidate_cache(adapter_name: Optional[str] = None) -> None
```

**Skill routing examples (`_get_skill_routing_examples`):**

For adapters with `supports_autocomplete: true`, this reads the calling adapter's
`capabilities.auto_routable_skills` and `capabilities.available_skills` (their union),
looks up each matching skill via `adapter_manager.get_all_skills()`, and pulls
`capabilities.routing_examples` from that skill's *backing* adapter config — the same
phrases the [skill intent router](adapters/auto-skill-intent-detection.md) embeds for
detection (e.g. `config/adapters/web-search.yaml`'s `routing_examples: ["search the web
for", ...]`). Disabled skills and skills outside the allowlist are excluded. These
phrases are typically sentence stems rather than full queries — accepting one fills the
stem and leaves the caret at the end for the user to finish typing.

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
| `X-API-Key` | Yes | API key used by the server to resolve the active adapter |

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

#### useAutocomplete Hook (`clients/orbitchat/src/hooks/useAutocomplete.ts`)

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

#### MessageInput Component (`clients/orbitchat/src/components/MessageInput.tsx`)

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

On a conversational adapter with no retriever templates (e.g. `simple-chat`),
`supports_autocomplete: true` instead publishes the `routing_examples` of whatever
skills that adapter can reach — see [`config/adapters/passthrough.yaml`](../config/adapters/passthrough.yaml):
```yaml
- name: "simple-chat"
  capabilities:
    auto_routable_skills: ["Image", "PDF", "web-search", ...]
    available_skills: ["mcp-agent", "HR", ...]
    supports_autocomplete: true   # suggestions come from the skills above
```

## Configuration

### Server Configuration (`config/config.yaml`)

```yaml
autocomplete:
  enabled: true  # Master switch

  # Query matching settings
  min_query_length: 3  # Minimum characters before fetching
  max_suggestions: 10  # Server-side ceiling for returned suggestions

  # Caching configuration
  cache:
    use_cache: true           # Use the configured cache provider (see below) when available; otherwise use memory cache
    ttl_seconds: 1800         # 30 minutes cache TTL
    cache_key_prefix: "autocomplete:"

  # Fuzzy matching configuration
  fuzzy_matching:
    enabled: true             # Enable fuzzy/approximate matching
    algorithm: "jaro_winkler" # Options: substring, levenshtein, jaro_winkler
    threshold: 0.75           # Minimum similarity score (0.0-1.0)
    max_candidates: 250       # Fuzzy ranking shortlist after cheap relevance prefilter
```

`cache.use_cache` does not pick a specific backend itself — it toggles whether autocomplete
uses ORBIT's shared cache provider at all. Which backend that provider actually is comes
from `internal_services.cache.provider` (`config/config.yaml`):

```yaml
internal_services:
  cache:
    enabled: true
    provider: "sqlite"  # sqlite | redis | memcached
```

- **`sqlite`** (default) — file-backed (`internal_services.sqlite_cache.database_path`), no
  external service required; fine for single-instance deployments.
- **`redis`** — distributed, shared across instances; needs `internal_services.redis.*`
  configured and a running Redis server.
- **`memcached`** — lighter-weight distributed alternative; no key-pattern matching, so
  `invalidate_cache()` (see [Cache Invalidation](#cache-invalidation)) falls back to a full
  flush instead of a targeted delete.

Autocomplete is provider-agnostic: `AutocompleteService` calls the injected `cache_service`
(`get`/`set`/`delete`/`clear_by_pattern`), and whichever backend is configured serves those
calls. If `internal_services.cache.enabled: false`, or `autocomplete.cache.use_cache: false`,
autocomplete transparently falls back to the in-memory cache described below.

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
          ┌───────────────┼─────────────┐
          ▼               ▼             ▼
    ┌────────────────┐ ┌───────────┐ ┌───────────────────┐
    │ Cache Provider  │ │  Memory   │ │ Templates + Skill │
    │ (SQLite/Redis/  │ │   Cache   │ │      Phrases       │
    │   Memcached)    │ │(fallback) │ │                     │
    └────────────────┘ └───────────┘ └───────────────────┘
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

1. **Cache Provider (Primary)** — whichever backend `internal_services.cache.provider`
   selects:
   - **SQLite** (default) — file-backed, single-instance; no external service to run.
   - **Redis** — distributed across server instances, needs a running Redis server.
   - **Memcached** — distributed, lighter-weight than Redis; no key-pattern matching
     (see Cache Invalidation below).

   All three share the same behavior from `AutocompleteService`'s point of view:
   - Automatic TTL expiration (`autocomplete.cache.ttl_seconds`)
   - Persists across server restarts (SQLite/Redis/Memcached are all external to the
     process — only the in-memory fallback below is lost on restart)
   - Key format: `autocomplete:{adapter_name}`

2. **Memory Cache (Fallback)**
   - Per-instance, in-process cache
   - Used when the cache provider is disabled/unavailable, or `autocomplete.cache.use_cache: false`
   - Automatic TTL expiration
   - Lost on server restart

### Cache Invalidation

```python
# Invalidate specific adapter
await autocomplete_service.invalidate_cache("intent-mongodb-mflix")

# Invalidate all adapters
await autocomplete_service.invalidate_cache()
```

With SQLite or Redis, "invalidate all" deletes only autocomplete's own keys via
pattern matching (`autocomplete:*`). Memcached has no pattern-matching primitive, so
the same call falls back to a full cache flush there — see
`CacheProvider.clear_by_pattern` (`server/services/cache_backends/base.py`).

**When to Invalidate:**
- After updating intent templates
- After adding/removing `nl_examples`
- After changing adapter configuration
- After adding/removing/editing skill `capabilities.routing_examples`

**Known gap:** none of the above currently happen automatically — `invalidate_cache()`
is called from the test suite but not from production code (e.g. the adapter hot-reload
path). Until that's wired up, edited templates/`routing_examples` only take effect after
`ttl_seconds` elapses or the server restarts.

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
| `max_suggestions` | 10 | Server-side response ceiling |
| `max_candidates` | 250 | Limit fuzzy comparison shortlist |

### Debouncing

Client-side 300ms debounce prevents excessive API calls while typing.

### Caching

- 30-minute default TTL
- Templates and `routing_examples` rarely change, so cache hit rate is high
- A distributed provider (Redis/Memcached) avoids re-extracting templates/skills on
  every instance in a multi-node deployment; SQLite still avoids re-extraction on a
  single instance across requests, just without cross-instance sharing

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
  Max suggestions: 10
  Cache: Memory (TTL: 1800s)
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
- Memory and cache-provider (Redis-backed) caching
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
3. Ensure adapter has templates with `nl_examples`, and/or (for conversational adapters)
   reachable skills whose backing adapter defines `capabilities.routing_examples`
4. Check query meets minimum length (3 chars)
5. Review debug logs for errors

### Slow Response Times

1. Ensure C libraries are installed (`pip install Levenshtein jarowinkler`)
2. Check the configured cache provider's connection (Redis/Memcached) or disk I/O (SQLite)
3. Reduce `max_candidates` if fuzzy matching is slow
4. Consider using `substring` algorithm instead of fuzzy

### Cache Not Working

1. Verify `internal_services.cache.enabled: true` and check which `provider` is selected
2. Check `autocomplete.cache.use_cache` setting
3. Review connection/health logs for the selected provider (Redis/Memcached), or confirm
   the SQLite cache file (`internal_services.sqlite_cache.database_path`) is writable
4. Ensure `ttl_seconds` is set correctly
5. Remember edited templates/`routing_examples` only refresh after the TTL lapses or a
   restart — see the invalidation gap noted under [Cache Invalidation](#cache-invalidation)

## Future Enhancements

1. **Personalization**: Rank suggestions based on user's query history
2. **Analytics**: Track which suggestions are selected
3. **Synonyms**: Match queries against synonym mappings
4. **Multi-language**: Support suggestions in detected language
5. **Partial Word Matching**: Match incomplete words at end of query
