# SQL Template Generator

An AI-powered tool that automatically generates SQL templates from natural language test queries for the Intent PostgreSQL retriever.

## Overview

The Template Generator analyzes natural language queries and database schemas to automatically create parameterized SQL templates. This helps maintain consistency and reduces manual effort when schema changes occur or new query patterns are needed.

## Features

- **Automatic Schema Parsing**: Extracts table structure and relationships from SQL schema files
- **AI-Powered Query Analysis**: Uses inference providers to understand query intent and parameters
- **Smart Query Grouping**: Groups similar queries to avoid duplicate templates
- **Template Validation**: Validates generated templates for completeness and correctness
- **Multiple Provider Support**: Works with various AI providers (Ollama, OpenAI, Anthropic, etc.)

## Installation

The template generator is included in the Orbit server utilities. No additional installation is needed.

## Usage

### Basic Command

```bash
python server/utils/template_generator.py \
  --schema examples/postgres/customer-order.sql \
  --queries examples/postgres/test/test_queries.md \
  --output examples/postgres/generated_templates.yaml
```

### Full Command with Options

```bash
python server/utils/template_generator.py \
  --schema path/to/schema.sql \
  --queries path/to/test_queries.md \
  --output path/to/output_templates.yaml \
  --domain path/to/domain_config.yaml \
  --config config/config.yaml \
  --provider ollama \
  --limit 50
```

### Command Line Arguments

- `--schema` (required): Path to SQL schema file containing CREATE TABLE statements
- `--queries` (required): Path to markdown file containing test queries
- `--output` (required): Path where generated templates will be saved
- `--domain`: Path to domain configuration file (optional, provides additional context)
- `--config`: Path to main configuration file (default: `config/config.yaml`)
- `--provider`: Inference provider to use (default: `ollama`)
- `--limit`: Limit the number of queries to process (useful for testing)

## How It Works

### 1. Schema Parsing

The generator parses SQL schema files to extract:
- Table names and structures
- Column names and types
- Foreign key relationships
- Indexes and constraints

### 2. Query Analysis

For each test query, the AI analyzes:
- **Intent**: The main action (find, calculate, filter, etc.)
- **Entities**: Primary and secondary entities involved
- **Filters**: Conditions and parameters needed
- **Aggregations**: Any calculations required
- **Time Ranges**: Date/time based filters
- **Sorting**: Order by requirements

### 3. Query Grouping

Similar queries are grouped together based on:
- Same intent and entities
- Similar filter patterns
- Common aggregations
- Shared time range patterns

### 4. Template Generation

For each group of queries, the generator creates:
- Parameterized SQL with `%(param_name)s` placeholders
- Parameter definitions with types and descriptions
- Natural language examples
- Semantic tags for better matching

### 5. Validation

Each template is validated for:
- Required fields presence
- SQL syntax correctness
- Parameter placeholder matching
- Minimum example count

## Example Workflow

### 1. When Schema Changes

If you modify the database schema:

```bash
# Update the schema file
vim examples/postgres/customer-order.sql

# Regenerate templates
python server/utils/template_generator.py \
  --schema examples/postgres/customer-order.sql \
  --queries examples/postgres/test/test_queries.md \
  --output examples/postgres/updated_templates.yaml

# Review and merge with existing templates
```

### 2. Adding New Query Patterns

When adding new query types:

```bash
# Add new test queries
echo '"Show me orders with express shipping"' >> examples/postgres/test/test_queries.md
echo '"Find customers who ordered multiple times today"' >> examples/postgres/test/test_queries.md

# Generate templates for new queries
python server/utils/template_generator.py \
  --schema examples/postgres/customer-order.sql \
  --queries examples/postgres/test/test_queries.md \
  --output examples/postgres/new_templates.yaml \
  --limit 2
```

### 3. Testing Template Generation

```bash
# Run the test script
python server/utils/test_template_generator.py

# Check generated test templates
cat test_generated_templates.yaml
```

## Generated Template Format

```yaml
templates:
  - id: find_order_by_customer_name
    version: "1.0.0"
    description: "Find orders for a customer by their name"
    nl_examples:
      - "Show me orders from John Smith"
      - "What did Jane Doe order?"
      - "Find all orders from customer Bob Johnson"
    parameters:
      - name: customer_name
        type: string
        description: "Customer name to search for"
        required: true
    sql_template: |
      SELECT o.*, c.name as customer_name, c.email as customer_email
      FROM orders o
      JOIN customers c ON o.customer_id = c.id
      WHERE LOWER(c.name) LIKE LOWER(%(customer_name)s)
      ORDER BY o.order_date DESC
      LIMIT 100
    result_format: "table"
    tags: ["order", "customer", "name", "search"]
    semantic_tags:
      action: "find"
      primary_entity: "order"
      secondary_entity: "customer"
    approved: false
    created_at: "2024-01-15T10:30:00Z"
    created_by: "template_generator"
```

## Configuration

The generator can be configured using `template_generator_config.yaml`:

```yaml
generation:
  max_examples_per_template: 10
  similarity_threshold: 0.8
  defaults:
    version: "1.0.0"
    approved: false
    result_format: "table"

validation:
  required_fields:
    - id
    - description
    - sql_template
    - parameters
    - nl_examples
  min_examples: 3
  max_sql_length: 5000
```

## Best Practices

### 1. Review Generated Templates

Always review AI-generated templates before using them:
- Check SQL correctness
- Verify parameter names and types
- Ensure proper table joins
- Validate security (no SQL injection risks)

### 2. Maintain Test Queries

Keep test queries comprehensive and up-to-date:
- Cover all common use cases
- Include edge cases
- Add new patterns as they emerge
- Remove obsolete queries

### 3. Incremental Generation

Generate templates incrementally:
- Process new queries separately
- Review and approve before merging
- Keep manual customizations

### 4. Provider Selection

Choose appropriate AI providers:
- **Ollama**: Good for local development
- **OpenAI/Anthropic**: Better for complex queries
- **Gemini/Groq**: Fast and cost-effective

## Troubleshooting

### Common Issues

1. **No JSON found in response**
   - Check if the AI provider is running
   - Verify API keys are configured
   - Try a different provider

2. **Schema parsing errors**
   - Ensure SQL file has valid CREATE TABLE statements
   - Check for syntax errors in SQL
   - Remove comments that might interfere

3. **Template validation failures**
   - Review parameter placeholders
   - Check SQL syntax
   - Ensure all required fields are present

### Debug Mode

Run with verbose logging:

```bash
# Set logging level
export LOG_LEVEL=DEBUG

# Run generator
python server/utils/template_generator.py --schema ... --queries ... --output ...
```

## Integration with Intent Retriever

Generated templates can be used with the Intent PostgreSQL retriever:

1. Copy approved templates to your template library:
   ```bash
   cp generated_templates.yaml examples/postgres/custom_templates.yaml
   ```

2. Reload templates in the retriever:
   ```python
   # The retriever will automatically load templates on initialization
   retriever = IntentPostgreSQLRetriever(config)
   await retriever.initialize()
   ```

3. Test with natural language queries:
   ```python
   results = await retriever.get_relevant_context("Show me orders from John Smith")
   ```

## Future Enhancements

- Automatic template testing against database
- Template versioning and migration
- Integration with CI/CD pipelines
- Template performance optimization
- Multi-language query support

## Contributing

When contributing to the template generator:

1. Add test cases for new features
2. Update documentation
3. Ensure backward compatibility
4. Run validation tests
5. Submit PR with examples

## License

Same as the Orbit project license.