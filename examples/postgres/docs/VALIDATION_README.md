# RAG System Validation Suite

This validation suite helps you verify that your RAG system's responses accurately match the actual data in your PostgreSQL database.

## 🎯 Purpose

The validation system:
- **Compares RAG responses with SQL results** to ensure accuracy
- **Identifies discrepancies** between what the system claims and what exists in the database
- **Tests parameter extraction** to verify queries are interpreted correctly
- **Validates template matching** to ensure appropriate query templates are selected
- **Measures performance** and response consistency

## 🚀 Quick Start

### Basic Usage

```bash
# Run basic validation tests (recommended first step)
python3 validate_rag_results.py

# Or use the convenient runner script
./run_validation_tests.sh basic
```

### Test Categories

```bash
# Test specific query categories
./run_validation_tests.sh customer     # Customer queries
./run_validation_tests.sh orders       # Order value/status queries  
./run_validation_tests.sh location     # Location-based queries
./run_validation_tests.sh payment      # Payment method queries
./run_validation_tests.sh analytics    # Analytics and summary queries

# Test samples
./run_validation_tests.sh sample10     # 10 random queries
./run_validation_tests.sh sample25     # 25 random queries

# Comprehensive testing
./run_validation_tests.sh full         # All categories (60+ queries)
```

### Debug Mode

```bash
# Run with detailed output to see exactly what's happening
python3 validate_rag_results.py --debug

# Test a single custom query
python3 validate_rag_results.py --custom "Show me orders from customer 123"
```

## 📊 Understanding Results

### Success Indicators ✅

```
✅ PASS | RAG:15 SQL:14 | 0.45s | Show me orders from customer 123...
```

- **PASS**: RAG and SQL results match within acceptable tolerance (10%)
- **RAG:15**: RAG system reported 15 results
- **SQL:14**: Direct SQL query returned 14 results
- **0.45s**: Query execution time

### Failure Indicators ❌

```
❌ FAIL | RAG:0 SQL:25 | 0.32s | Find orders over $500...
     Error: SQL found 25 results but RAG failed
```

Common failure types:
- **Count mismatch**: Large difference between RAG and SQL counts
- **RAG failed**: System couldn't process the query
- **SQL validation failed**: Couldn't construct equivalent SQL
- **Template matching**: Wrong template selected for query

## 🔍 Interpreting Validation Results

### Pass Rate Analysis

```
📊 Validation Summary - customer
   Total queries: 8
   Passed: 7 (87.5%)
   Failed: 1 (12.5%)
   Total time: 3.45s
   Average time: 0.43s per query
```

**Good pass rates:**
- **90%+**: Excellent system accuracy
- **80-90%**: Good accuracy with minor issues
- **70-80%**: Acceptable but needs investigation
- **<70%**: Significant issues requiring attention

### Common Issues and Solutions

#### 1. Template Matching Problems
```
❌ FAIL | Could not build SQL for template: unknown_template
```
**Solution**: Check if query patterns match existing templates

#### 2. Parameter Extraction Issues
```
❌ FAIL | RAG succeeded but SQL validation failed
```
**Solution**: Verify parameter extraction logic in `DomainAwareParameterExtractor`

#### 3. Count Mismatches
```
❌ FAIL | Count mismatch: RAG=5, SQL=15, diff=10
```
**Solution**: Check if:
- Result filtering is too aggressive
- Template SQL logic differs from validation SQL
- Plugin modifications affect result counts

## 🛠️ Troubleshooting

### Environment Setup

Ensure your environment is properly configured:

```bash
# Check database connection
python3 -c "from clients import PostgreSQLDatabaseClient; client = PostgreSQLDatabaseClient(); print('DB connection OK')"

# Check RAG system initialization  
python3 -c "from validate_rag_results import RAGValidator; validator = RAGValidator(); print('RAG system OK')"
```

### Common Setup Issues

1. **Database Connection Errors**
   - Verify `.env` file has correct PostgreSQL credentials
   - Ensure database is running and accessible

2. **Ollama Connection Errors**
   - Start Ollama server: `ollama serve`
   - Pull required models: `ollama pull nomic-embed-text` and `ollama pull gemma3:1b`

3. **Template Loading Errors**
   - Check that `shared_domain_config.py` loads correctly
   - Verify template generation completes without errors

### Performance Issues

If validation is slow:
- Use smaller sample sizes: `--sample 5`
- Test individual categories instead of `--full`
- Check database query performance with `EXPLAIN ANALYZE`

## 📈 Best Practices

### Regular Validation

1. **Run basic tests** after any system changes
2. **Test specific categories** when modifying related templates
3. **Use full test suite** before deploying to production
4. **Monitor pass rates** over time to catch regressions

### Interpreting Results

1. **Focus on large count differences** (>20% variance)
2. **Investigate failed queries** that should work
3. **Check template selection** for unexpected matches
4. **Validate parameter extraction** for complex queries

### Debugging Workflow

1. **Start with basic tests** to verify overall system health
2. **Use debug mode** for detailed query analysis
3. **Test individual queries** that are failing
4. **Check SQL validation templates** if patterns seem wrong

## 📋 Test Query Categories

The validation suite includes 60+ test queries across these categories:

- **Customer Queries** (8 queries): Customer ID lookups, name searches, customer summaries
- **Order Value** (8 queries): Amount filters, ranges, high/low value orders
- **Order Status** (8 queries): Status filtering, pending/delivered/cancelled orders
- **Location** (8 queries): City/country filters, geographic analysis
- **Payment** (8 queries): Payment method filtering and analysis
- **Analytics** (8 queries): Top customers, summaries, lifetime value calculations

## 🔧 Customization

### Adding New Test Queries

Edit `validate_rag_results.py` and add queries to the appropriate category:

```python
TEST_QUERIES = {
    "customer": [
        "Your new customer query here",
        # ... existing queries
    ]
}
```

### Custom SQL Validation

Add new SQL templates in `sql_validation_templates.py`:

```python
@staticmethod
def get_your_custom_sql(parameters: Dict[str, Any]) -> Tuple[str, List]:
    sql = "SELECT ... FROM ..."
    params = []
    # Add your logic here
    return sql, params
```

## 📞 Support

If you encounter issues:

1. Check the error messages in the validation output
2. Run individual queries with `--debug` flag for details
3. Verify your database has sufficient test data
4. Ensure all dependencies are properly installed

The validation system helps ensure your RAG system provides accurate, reliable responses that match your actual data.