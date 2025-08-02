# Template Generator Usage Examples

This document provides examples of how to use the template generator utilities.

## Prerequisites

1. **Inference Provider Running**: Ensure your inference provider is running (e.g., `ollama serve`)
2. **Configuration**: Have your `config/config.yaml` file properly configured
3. **Schema File**: A SQL schema file with CREATE TABLE statements
4. **Test Queries**: A file with natural language queries to analyze

## Quick Start

### 1. Basic Template Generation

Generate templates from the PostgreSQL example:

```bash
# Navigate to project root
cd /Users/remsyschmilinsky/Downloads/orbit

# Run template generator
python utils/template_generator.py \
    --schema examples/postgres/customer-order.sql \
    --queries examples/postgres/test/test_queries.md \
    --output examples/postgres/generated_templates.yaml
```

### 2. Using Different AI Providers

```bash
# Using OpenAI (requires OPENAI_API_KEY)
python utils/template_generator.py \
    --schema examples/postgres/customer-order.sql \
    --queries examples/postgres/test/test_queries.md \
    --output generated_templates_openai.yaml \
    --provider openai

# Using Anthropic (requires ANTHROPIC_API_KEY)
python utils/template_generator.py \
    --schema examples/postgres/customer-order.sql \
    --queries examples/postgres/test/test_queries.md \
    --output generated_templates_anthropic.yaml \
    --provider anthropic
```

### 3. Testing with Limited Queries

```bash
# Generate templates for only the first 10 queries
python utils/template_generator.py \
    --schema examples/postgres/customer-order.sql \
    --queries examples/postgres/test/test_queries.md \
    --output test_templates.yaml \
    --limit 10
```

### 4. Including Domain Configuration

```bash
# Use domain config for better context
python utils/template_generator.py \
    --schema examples/postgres/customer-order.sql \
    --queries examples/postgres/test/test_queries.md \
    --output enhanced_templates.yaml \
    --domain examples/postgres/customer_order_domain.yaml
```

## Running Tests

### Basic Test
```bash
# Run the test script
python utils/test_template_generator.py
```

### Custom Test with Your Data
```python
import asyncio
from utils.template_generator import TemplateGenerator

async def test_with_my_data():
    generator = TemplateGenerator("config/config.yaml", "ollama")
    await generator.initialize()
    
    generator.parse_schema("my_schema.sql")
    queries = generator.parse_test_queries("my_queries.md")
    templates = await generator.generate_templates(queries)
    generator.save_templates(templates, "my_templates.yaml")

asyncio.run(test_with_my_data())
```

## Working with Generated Templates

### 1. Review Generated Templates

```bash
# View the generated templates
cat examples/postgres/generated_templates.yaml

# Count templates
grep -c "^  - id:" examples/postgres/generated_templates.yaml
```

### 2. Validate Templates

The generator automatically validates templates, but you can check validation errors:

```python
import yaml
from utils.template_generator import TemplateGenerator

# Load generated templates
with open('generated_templates.yaml', 'r') as f:
    data = yaml.safe_load(f)

generator = TemplateGenerator()
for template in data['templates']:
    errors = generator.validate_template(template)
    if errors:
        print(f"Template {template['id']} has errors: {errors}")
    else:
        print(f"Template {template['id']} is valid ✓")
```

### 3. Merge with Existing Templates

```bash
# Backup existing templates
cp examples/postgres/custom_templates.yaml examples/postgres/custom_templates.yaml.backup

# Manually merge approved templates from generated_templates.yaml
# (Review each template before adding)
```

## Common Workflows

### When Schema Changes

```bash
# 1. Update your schema file
vim examples/postgres/customer-order.sql

# 2. Regenerate templates
python utils/template_generator.py \
    --schema examples/postgres/customer-order.sql \
    --queries examples/postgres/test/test_queries.md \
    --output updated_templates.yaml

# 3. Review and merge changes
diff examples/postgres/custom_templates.yaml updated_templates.yaml
```

### Adding New Query Types

```bash
# 1. Add new queries to test file
echo '"Show me orders with express shipping"' >> examples/postgres/test/test_queries.md
echo '"Find customers who never placed an order"' >> examples/postgres/test/test_queries.md

# 2. Generate templates for new queries
python utils/template_generator.py \
    --schema examples/postgres/customer-order.sql \
    --queries examples/postgres/test/test_queries.md \
    --output new_query_templates.yaml \
    --limit 2  # Only process new queries

# 3. Review and add to existing templates
```

### Batch Processing Multiple Domains

```bash
#!/bin/bash
# Process multiple domains
for domain in ecommerce crm inventory; do
    echo "Processing $domain..."
    python utils/template_generator.py \
        --schema "examples/$domain/schema.sql" \
        --queries "examples/$domain/test_queries.md" \
        --output "examples/$domain/generated_templates.yaml" \
        --domain "examples/$domain/domain_config.yaml"
done
```

## Troubleshooting

### Common Issues

1. **"No inference provider found"**
   ```bash
   # Check if ollama is running
   curl http://localhost:11434/api/tags
   
   # Or start ollama
   ollama serve
   ```

2. **"Schema parsing failed"**
   ```bash
   # Check SQL syntax
   psql < examples/postgres/customer-order.sql
   ```

3. **"No queries found"**
   ```bash
   # Check query file format
   head -20 examples/postgres/test/test_queries.md
   ```

### Debug Mode

```bash
# Enable debug logging
export LOG_LEVEL=DEBUG
python utils/template_generator.py [options]
```

### Test Individual Components

```python
import asyncio
from utils.template_generator import TemplateGenerator

async def debug_analysis():
    generator = TemplateGenerator()
    await generator.initialize()
    
    # Test schema parsing
    schema = generator.parse_schema("examples/postgres/customer-order.sql")
    print("Schema:", schema)
    
    # Test query analysis
    analysis = await generator.analyze_query("Show me orders from John Smith")
    print("Analysis:", analysis)

asyncio.run(debug_analysis())
```

## Configuration Options

### Custom Configuration

Create a custom config file:

```yaml
# custom_template_config.yaml
generation:
  max_examples_per_template: 15
  similarity_threshold: 0.9

inference:
  analysis:
    temperature: 0.05  # More deterministic
  sql_generation:
    temperature: 0.1

validation:
  min_examples: 5
```

Use with:
```bash
python utils/template_generator.py \
    --config custom_template_config.yaml \
    [other options]
```

## Integration with Orbit

### Using Generated Templates

1. Copy approved templates:
   ```bash
   # Extract approved templates only
   python -c "
   import yaml
   with open('generated_templates.yaml', 'r') as f:
       data = yaml.safe_load(f)
   approved = [t for t in data['templates'] if t.get('approved', False)]
   with open('approved_templates.yaml', 'w') as f:
       yaml.dump({'templates': approved}, f)
   "
   ```

2. Add to your template library:
   ```bash
   cat approved_templates.yaml >> examples/postgres/custom_templates.yaml
   ```

3. Restart your Intent retriever to load new templates

### Performance Tips

- Use `--limit` for testing to avoid long generation times
- Start with a smaller set of diverse queries
- Use local providers (ollama) for development, cloud providers for production
- Cache generated templates and only regenerate when schema changes

## Advanced Usage

### Custom Query Parsing

```python
def parse_custom_queries(file_path):
    """Parse queries from custom format"""
    queries = []
    with open(file_path, 'r') as f:
        for line in f:
            if line.startswith('Q:'):
                queries.append(line[2:].strip())
    return queries

# Use with template generator
generator = TemplateGenerator()
queries = parse_custom_queries("my_custom_queries.txt")
templates = await generator.generate_templates(queries)
```

### Template Post-Processing

```python
def enhance_templates(templates):
    """Add custom enhancements to generated templates"""
    for template in templates:
        # Add custom tags
        if 'customer' in template['id']:
            template['tags'].append('crm')
        
        # Set approval status based on confidence
        if len(template['nl_examples']) > 5:
            template['approved'] = True
    
    return templates
```