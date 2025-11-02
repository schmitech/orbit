# Result Tracking Fixes - Summary (SQL & Vector Retrievers)

## Problem Identified

The system was inconsistently reporting result counts to the LLM, causing confusion when:
1. **SQL queries** returned 100+ records from the database
2. **Vector searches** returned 50+ documents from ChromaDB/Elasticsearch/MongoDB
3. Results were truncated to 3 records (default `return_results` value)
4. LLM only saw the truncated results but wasn't informed about the truncation
5. LLM responses stated "I found 3 results" when actually 100+ existed in the database/vector store

## Root Causes

### 1. Silent Truncation
- Results were truncated at multiple points without tracking the original count
- The LLM received truncated data without any indication that truncation occurred

### 2. Misleading Metadata
- `result_count` in metadata reported the truncated count, not the original
- No field existed to track the total available results from SQL

### 3. Insufficient Logging
- Truncation was logged but didn't clearly show the impact on LLM context
- No warning when LLM would only see a subset of results

## Files Modified

### SQL Retrievers

#### 1. `/server/retrievers/base/intent_sql_base.py`
**Changes:**
- Track `original_result_count` before any truncation (line 550)
- Add `was_truncated` flag to track truncation state (line 551)
- Improved logging to show original vs truncated counts (lines 554, 558)
- Update content message to indicate truncation (lines 586-589)
- Add truncation info to metadata (lines 616-618):
  - `result_count`: Actual count passed to LLM
  - `total_available`: Total records from SQL query
  - `truncated`: Boolean flag indicating if truncation occurred
- Update `_format_sql_results()` signature to accept truncation info (line 849)
- Pass truncation metadata through fallback path (lines 625-631)

#### 2. `/server/retrievers/base/sql_retriever.py`
**Changes:**
- Track original count before truncation (line 416)
- Calculate `was_truncated` flag (line 417)
- Add logging for truncation (lines 419-420)
- Add truncation metadata to all results (lines 424-430):
  - `total_available`: Total records before truncation
  - `truncated`: Boolean flag
  - `result_count`: Count passed to LLM
- Improved debug logging (lines 432-436)

### Vector Retrievers

#### 3. `/server/retrievers/base/abstract_vector_retriever.py`
**Changes:**
- Track counts at each filtering stage:
  - `vector_search_count`: Initial results from vector DB (line 324)
  - `after_confidence_filtering`: After confidence threshold (line 368)
  - `after_domain_filtering`: After domain-specific filtering (line 380)
- Add logging for each filtering stage (lines 370-371, 382-383)
- Track original count before truncation (line 386)
- Add `was_truncated` flag (line 387)
- Log truncation with clear counts (lines 389-390)
- Add comprehensive metadata to all results (lines 396-404):
  - `total_available`: Results available before final truncation
  - `truncated`: Boolean flag
  - `result_count`: Count passed to LLM
  - `vector_search_count`: Initial vector search results
  - `after_confidence_filtering`: Count after confidence filtering
  - `after_domain_filtering`: Count after domain filtering
- Improved debug logging (lines 406-410)

### Pipeline Integration

#### 4. `/server/inference/pipeline/steps/context_retrieval.py`
**Changes:**
- Extract truncation info from retrieved documents (lines 97-111)
- Log truncation information clearly (line 107)
- Pass truncation info to context formatter (line 114)
- Update `_format_context()` to accept truncation_info parameter (line 122)
- Add truncation notice to formatted context (lines 143-148):
  - Prepends "NOTE: Showing X of Y total results from database. Results have been truncated."
  - This message is included in the context that the LLM receives
- Works for both SQL and Vector retrievers

## How It Works Now

### SQL Retriever Flow with Truncation:

```
1. SQL Query Executes
   └─> Returns 100 records from database

2. Intent SQL Base (line 550)
   └─> original_result_count = 100
   └─> was_truncated = False

3. Truncation Check (line 557)
   └─> if 100 > return_results (3):
       └─> Truncate to 3 records
       └─> was_truncated = True
       └─> Log: "Truncating from 100 to 3"

4. Format Content (lines 586-589)
   └─> Message: "Showing 3 of 100 total results (truncated)"

5. Add Metadata (lines 616-618)
   └─> result_count: 3
   └─> total_available: 100
   └─> truncated: True

6. Context Retrieval (lines 97-111)
   └─> Extracts truncation info from metadata
   └─> Log: "Retrieved 3 documents (truncated from 100 total)"

7. Format Context (lines 143-148)
   └─> Prepends: "NOTE: Showing 3 of 100 total results from database."

8. LLM Receives Context
   └─> Sees truncation notice
   └─> Knows it's only seeing 3 of 100 records
   └─> Can respond accurately: "Based on the 3 results shown (out of 100 total)..."
```

### Vector Retriever Flow with Multi-Stage Filtering:

```
1. Vector Search Executes
   └─> Returns 50 documents from ChromaDB/Elasticsearch/MongoDB
   └─> Log: "Vector search returned 50 results"

2. Confidence Filtering (lines 329-366)
   └─> Filter by confidence_threshold (0.5)
   └─> 50 → 45 results pass confidence check
   └─> Log: "Confidence filtering: 50 → 45 results (threshold: 0.5)"

3. Domain Filtering (lines 377-383)
   └─> Apply domain-specific rules
   └─> 45 → 40 results pass domain filtering
   └─> Log: "Domain filtering: 45 → 40 results"

4. Truncation Check (lines 385-393)
   └─> original_count = 40
   └─> if 40 > return_results (3):
       └─> Truncate to 3 documents
       └─> was_truncated = True
       └─> Log: "Truncating vector search results from 40 to 3"

5. Add Metadata (lines 396-404)
   └─> result_count: 3
   └─> total_available: 40
   └─> truncated: True
   └─> vector_search_count: 50
   └─> after_confidence_filtering: 45
   └─> after_domain_filtering: 40

6. Context Retrieval (lines 97-111)
   └─> Extracts truncation info from metadata
   └─> Log: "Retrieved 3 documents (truncated from 40 total)"

7. Format Context (lines 143-148)
   └─> Prepends: "NOTE: Showing 3 of 40 total results from database."

8. LLM Receives Context
   └─> Sees truncation notice
   └─> Knows filtering pipeline: 50 → 45 → 40 → 3
   └─> Can respond accurately: "Based on the 3 results shown (out of 40 qualifying documents from 50 retrieved)..."
```

## Configuration

The `return_results` parameter controls truncation:

### Default Value: 3
Located in `/server/retrievers/base/sql_retriever.py:53`

### Override in Adapter Config:
```yaml
adapter_config:
  return_results: 10  # Override to show 10 results instead of 3
```

### Intent-Specific Override:
Located in `/server/retrievers/base/intent_sql_base.py:43-47`
```python
if 'return_results' in self.intent_config:
    self.return_results = self.intent_config.get('return_results')
```

## Verification Steps

### 1. Check Logs
Look for these new log messages:
```
INFO: SQL query returned 100 rows from database
INFO: Truncating result set from 100 to 3 results based on adapter config (return_results=3)
INFO: Note: LLM will only see 3 of 100 records
INFO: Retrieved 3 documents (truncated from 100 total)
```

### 2. Check LLM Context
The context passed to the LLM should start with:
```
NOTE: Showing 3 of 100 total results from database. Results have been truncated.

[1] intent (confidence: 0.95)
...
```

### 3. Check Metadata
Inspect the metadata in retrieved_docs:
```python
{
    "content": "...",
    "metadata": {
        "result_count": 3,           # Actual count shown
        "total_available": 100,      # Total from SQL
        "truncated": true            # Truncation flag
    }
}
```

### 4. Test Query
Run a query that should return many results:
```
Query: "Show me all orders from last month"
Expected SQL Result: 100 records
Expected LLM Context: "NOTE: Showing 3 of 100 total results..."
Expected LLM Response: "Based on the 3 results shown (out of 100 total available)..."
```

## Benefits

1. **Transparency**: LLM knows when it's seeing truncated data
2. **Accurate Responses**: LLM can caveat answers appropriately
3. **Better Debugging**: Clear logging of truncation at each step
4. **Metadata Tracking**: Full visibility into truncation state
5. **User Awareness**: Users understand when results are limited

## Migration Notes

### Breaking Changes: None
- All changes are backward compatible
- Added optional parameters with defaults
- New metadata fields don't break existing code

### Recommended Actions:
1. Review `return_results` settings in adapter configs
2. Update tests to check for new metadata fields
3. Monitor logs for truncation warnings
4. Consider increasing `return_results` for adapters that need it

## Example Scenarios

### Scenario 1: No Truncation
```
SQL Returns: 2 records
return_results: 3
Result: No truncation
Message: "Found 2 results"
Metadata: {result_count: 2, total_available: 2, truncated: false}
```

### Scenario 2: With Truncation (Default)
```
SQL Returns: 100 records
return_results: 3 (default)
Result: Truncated to 3
Message: "Showing 3 of 100 total results (truncated)"
Metadata: {result_count: 3, total_available: 100, truncated: true}
LLM Context: "NOTE: Showing 3 of 100 total results from database..."
```

### Scenario 3: With Custom return_results
```
SQL Returns: 100 records
return_results: 50 (custom config)
Result: Truncated to 50
Message: "Showing 50 of 100 total results (truncated)"
Metadata: {result_count: 50, total_available: 100, truncated: true}
```

## Future Improvements

1. **Pagination Support**: Add ability to fetch next N results
2. **Adaptive Limits**: Adjust `return_results` based on content size
3. **Summary Statistics**: When truncated, provide aggregates (count, sum, avg)
4. **User Control**: Allow users to request "show me all results"
5. **Smart Truncation**: Keep most relevant results, not just first N

## Testing Checklist

- [ ] Test with query returning < return_results records
- [ ] Test with query returning > return_results records
- [ ] Verify logs show original count and truncated count
- [ ] Verify LLM context includes truncation notice
- [ ] Verify metadata includes all three fields
- [ ] Test with custom return_results value
- [ ] Test fallback path (_format_sql_results)
- [ ] Test non-intent SQL retrievers
- [ ] Test file adapter (should not show truncation notice in same format)
- [ ] Verify LLM responses acknowledge truncation appropriately
