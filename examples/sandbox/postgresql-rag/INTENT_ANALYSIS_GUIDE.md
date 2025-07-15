# Intent Analysis Plugin Guide

## Overview

The Intent Analysis Plugin is a high-priority plugin that transforms the RAG system from a simple "matcher" into an intelligent "reasoner." It analyzes user queries to extract structured intent information, enabling much more accurate template matching.

## Architecture

### Core Components

1. **Intent Analysis Plugin** (`intent_analysis_plugin.py`)
   - Performs structured analysis of user queries
   - Extracts intent, entities, qualifiers, and parameters
   - Uses hybrid approach: rule-based + LLM analysis

2. **Enhanced Reranking** (`customer_order_rag.py`)
   - Uses intent analysis for template scoring
   - Applies multiple bonus categories
   - Provides detailed logging for debugging

3. **Semantic Metadata** (`query_templates.yaml`)
   - Enhanced templates with semantic tags
   - Parameter aliases for better matching
   - Negative examples for disambiguation

## How It Works

### 1. Query Analysis Pipeline

```
User Query → Intent Analysis Plugin → Structured Analysis → Enhanced Reranking → Template Selection
```

### 2. Intent Analysis Process

The plugin performs a **hybrid analysis**:

1. **Rule-based Analysis**: Fast, deterministic analysis using keyword matching
2. **LLM Analysis**: Intelligent analysis using the inference model
3. **Analysis Merging**: Combines both approaches for optimal results

### 3. Structured Output

The plugin produces a structured analysis object:

```json
{
  "intent": "find_list|calculate_summary|rank_list|search_find|filter_by|compare_data",
  "primary_entity": "customer|order|amount|status|payment_method|location|time",
  "qualifiers": ["recent", "top", "high_value", "specific", "international"],
  "mentioned_parameters": {
    "customer_id": "123",
    "min_amount": 500.0,
    "days_back": 30
  },
  "confidence": 0.85,
  "analysis_method": "hybrid"
}
```

## Intent Categories

### Primary Intents

- **`find_list`**: Show me, find, list, get, display items
- **`calculate_summary`**: Total, sum, calculate, how much, lifetime value
- **`rank_list`**: Top, best, highest, most, biggest customers/orders
- **`search_find`**: Search for, find by, who has, customer with
- **`filter_by`**: Filter, only, just, specific, particular criteria
- **`compare_data`**: Compare, versus, difference between

### Entity Categories

- **`customer`**: Customer, client, buyer, user, person
- **`order`**: Order, purchase, transaction, sale, buy
- **`amount`**: Amount, total, value, price, cost, revenue
- **`status`**: Status, state, condition, stage
- **`payment_method`**: Payment, pay, method, credit card, paypal
- **`location`**: City, country, location, place, region
- **`time`**: Date, time, period, when, recent, last

## Enhanced Reranking

### Bonus Categories

The enhanced reranking applies multiple bonus categories:

1. **Intent Analysis Bonuses** (Highest Priority)
   - Action/Intent match: +0.3
   - Primary entity match: +0.2
   - Qualifier matches: +0.1 each
   - Parameter matches: +0.05 each

2. **Business Rule Bonuses**
   - Customer-related tags: +0.2
   - Location-specific matches: +0.1
   - Parameter type matches: +0.05

3. **Template Quality Bonuses**
   - Approved templates: +0.05
   - Semantic tags present: +0.05
   - Negative examples: +0.03
   - Parameter aliases: +0.02

4. **Specificity Bonuses**
   - Specific customer ID: +0.1
   - Specific amounts: +0.1
   - Specific status: +0.1
   - Specific payment method: +0.1

## Benefits

### 1. Improved Accuracy

**Before Intent Analysis:**
- Template matching based on keyword similarity
- Limited understanding of user intent
- Ambiguous matches for similar-sounding queries

**After Intent Analysis:**
- Structured understanding of user intent
- Semantic matching beyond keywords
- Better disambiguation between similar templates

### 2. Better Parameter Extraction

**Before:**
- Basic pattern matching
- Limited parameter recognition
- Poor handling of synonyms

**After:**
- LLM-powered parameter extraction
- Synonym handling through aliases
- Context-aware parameter mapping

### 3. Enhanced Debugging

**Before:**
- Limited visibility into matching decisions
- Difficult to understand why templates were chosen

**After:**
- Detailed logging of intent analysis
- Clear bonus application tracking
- Structured analysis results

## Usage Examples

### Example 1: Customer Recent Orders

**Query:** "What did customer 123 buy last week?"

**Intent Analysis:**
```json
{
  "intent": "find_list",
  "primary_entity": "order",
  "qualifiers": ["recent", "specific_customer"],
  "mentioned_parameters": {"customer_id": "123", "days_back": 7}
}
```

**Template Match:** `customer_recent_orders`
- ✅ Action match: `find_list` (+0.3)
- ✅ Entity match: `order` (+0.2)
- ✅ Qualifier match: `recent` (+0.1)
- ✅ Qualifier match: `specific_customer` (+0.1)
- ✅ Parameter match: `customer_id` (+0.05)

**Total Bonus:** +0.75

### Example 2: Customer Lifetime Value

**Query:** "What's the total revenue from customer 456?"

**Intent Analysis:**
```json
{
  "intent": "calculate_summary",
  "primary_entity": "customer",
  "qualifiers": ["total", "revenue"],
  "mentioned_parameters": {"customer_id": "456"}
}
```

**Template Match:** `customer_lifetime_value`
- ✅ Action match: `calculate_summary` (+0.3)
- ✅ Entity match: `customer` (+0.2)
- ✅ Qualifier match: `total` (+0.1)
- ✅ Parameter match: `customer_id` (+0.05)

**Total Bonus:** +0.65

### Example 3: Top Customers

**Query:** "Who are our top 10 customers?"

**Intent Analysis:**
```json
{
  "intent": "rank_list",
  "primary_entity": "customer",
  "qualifiers": ["top", "ranking"],
  "mentioned_parameters": {"limit": "10"}
}
```

**Template Match:** `top_customers`
- ✅ Action match: `rank_list` (+0.3)
- ✅ Entity match: `customer` (+0.2)
- ✅ Qualifier match: `top` (+0.1)
- ✅ Qualifier match: `ranking` (+0.1)
- ✅ Parameter match: `limit` (+0.05)

**Total Bonus:** +0.75

## Configuration

### Plugin Registration

The Intent Analysis Plugin is automatically registered with high priority:

```python
# In SemanticRAGSystem._register_default_plugins()
default_plugins = [
    SecurityPlugin(),
    IntentAnalysisPlugin(self.inference_client),  # High priority
    QueryNormalizationPlugin(),
    # ... other plugins
]
```

### Plugin Priority

The plugin runs at `PluginPriority.HIGH` to ensure intent analysis happens early in the pipeline, before template matching.

### Inference Client Integration

The plugin requires an inference client for LLM analysis:

```python
# The plugin uses the same inference client as the RAG system
plugin = IntentAnalysisPlugin(inference_client)
```

## Testing

### Test Script

Run the comprehensive test suite:

```bash
python test_intent_analysis.py
```

The test script includes:

1. **Direct Plugin Testing**: Tests the plugin in isolation
2. **Enhanced RAG Testing**: Tests the full system with intent analysis
3. **Accuracy Testing**: Measures template matching accuracy

### Expected Results

With intent analysis, you should see:

- **Higher accuracy**: 80-95% correct template matches
- **Better parameter extraction**: More accurate parameter values
- **Improved disambiguation**: Better handling of ambiguous queries
- **Detailed logging**: Clear visibility into matching decisions

## Debugging

### Enable Debug Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Key Log Messages

Look for these debug messages:

```
Intent match: find_list -> find_list (+0.3)
Entity match: order -> order (+0.2)
Qualifier match: recent (+0.1)
Parameter match: customer_id (+0.05)
```

### Analysis Results

Check the context metadata for analysis results:

```python
intent_analysis = context.metadata.get('intent_analysis')
print(f"Intent: {intent_analysis['intent']}")
print(f"Entity: {intent_analysis['primary_entity']}")
print(f"Confidence: {intent_analysis['confidence']}")
```

## Performance Considerations

### Caching

The plugin doesn't implement caching, but the analysis is fast:

- **Rule-based analysis**: ~1ms
- **LLM analysis**: ~100-500ms (depending on model)
- **Total analysis time**: ~100-500ms per query

### Optimization Tips

1. **Use smaller models** for faster LLM analysis
2. **Adjust temperature** (0.1 for consistency)
3. **Limit analysis depth** for simple queries
4. **Cache common patterns** if needed

## Future Enhancements

### Planned Features

1. **Intent Confidence Thresholds**: Skip LLM analysis for high-confidence rule-based results
2. **Context-Aware Analysis**: Consider conversation history
3. **Multi-language Support**: Support for non-English queries
4. **Custom Intent Categories**: User-defined intent types
5. **Analysis Caching**: Cache analysis results for similar queries

### Integration Opportunities

1. **Conversation Memory**: Use intent analysis for conversation context
2. **Query Suggestions**: Suggest related queries based on intent
3. **Template Generation**: Auto-generate templates from intent patterns
4. **Performance Analytics**: Track intent analysis accuracy over time

## Troubleshooting

### Common Issues

1. **LLM Analysis Fails**
   - Check inference client configuration
   - Verify model availability
   - Check network connectivity

2. **Low Confidence Scores**
   - Review intent categories
   - Check entity mappings
   - Verify qualifier definitions

3. **Template Mismatches**
   - Check semantic tags in templates
   - Verify intent-to-action mappings
   - Review negative examples

### Error Handling

The plugin is designed to be resilient:

- **LLM failures**: Falls back to rule-based analysis
- **JSON parsing errors**: Uses default analysis
- **Missing fields**: Provides sensible defaults
- **Plugin errors**: Logs errors but doesn't fail queries

## Conclusion

The Intent Analysis Plugin significantly enhances the RAG system's ability to understand and match user queries. By providing structured intent analysis, it enables more accurate template matching, better parameter extraction, and improved overall system performance.

The hybrid approach (rule-based + LLM) ensures both speed and accuracy, while the detailed logging provides excellent debugging capabilities. The plugin integrates seamlessly with the existing plugin architecture and can be easily extended for future enhancements. 