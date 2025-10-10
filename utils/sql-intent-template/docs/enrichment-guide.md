# Template Enrichment Guide for Contact Example

This guide explains how to generate diverse, high-quality SQL templates for the contact example.

## Problem: Generic Templates

The original template generation produced only 2 generic templates because:
- All queries had the same intent ("find") and entity ("users")
- High similarity threshold (0.7) collapsed diverse queries into one group
- No differentiation between search fields, filter types, or aggregations

## Solution: Enhanced Template Generation

We've created three resources to fix this:

### 1. **Enriched Test Queries** (`contact_test_queries_enriched.md`)
   - 25 distinct categories of queries
   - Each category targets a specific template type
   - Clear comments indicate intent, entity, and filter type
   - Produces 20-25+ specific templates instead of 2 generic ones

### 2. **Seed Templates** (`contact_seed_templates.yaml`)
   - 25 hand-crafted, production-ready templates
   - Covers all major query patterns
   - Can be used directly or merged with auto-generated templates
   - Serves as quality benchmark

### 3. **Updated Configuration** (`configs/contact-config.yaml`)
   - Lowered similarity threshold: 0.7 → 0.3
   - Reweighted grouping features to emphasize differentiators
   - Reduced examples per template: 8 → 5

---

## Quick Start: Generate Enriched Templates

### Option 1: Auto-Generate from Enriched Queries

```bash
# From the orbit root directory
python utils/sql-intent-template/template_generator.py \
  --schema utils/sql-intent-template/examples/contact.sql \
  --queries utils/sql-intent-template/examples/contact_test_queries_enriched.md \
  --domain config/sql_intent_templates/examples/contact/contact-domain.yaml \
  --output config/sql_intent_templates/examples/contact/contact-templates-enriched.yaml \
  --config config/config.yaml \
  --provider ollama_cloud
```

**Expected Result:** 20-25 diverse templates covering:
- Basic listing
- Name search (partial match)
- Email search (exact match)
- Age filters (exact, range, comparison)
- City filters
- Counts (total, by city, by age range)
- Aggregations (avg, min/max)
- Sorting (by name, age, date)
- Top N queries
- Multi-field filters
- Existence checks

### Option 2: Use Seed Templates Directly

The seed templates are production-ready and can be used immediately:

```bash
# Copy seed templates to your active config
cp utils/sql-intent-template/examples/contact_seed_templates.yaml \
   config/sql_intent_templates/examples/contact/contact-templates.yaml
```

Then update your adapter config to force reload:

```yaml
# In config/adapters.yaml
- name: "intent-sql-sqlite-contact"
  config:
    reload_templates_on_start: true
    force_reload_templates: true
```

### Option 3: Hybrid Approach (Recommended)

Combine seed templates with auto-generated ones:

```bash
# 1. Generate new templates from enriched queries
python utils/sql-intent-template/template_generator.py \
  --schema utils/sql-intent-template/examples/contact.sql \
  --queries utils/sql-intent-template/examples/contact_test_queries_enriched.md \
  --domain config/sql_intent_templates/examples/contact/contact-domain.yaml \
  --output /tmp/contact-auto-generated.yaml \
  --config config/config.yaml

# 2. Manually merge with seed templates
# Review both files and combine the best templates:
# - Use seed templates as foundation (high quality, well-tested)
# - Add any unique auto-generated templates that add value
# - Remove duplicates
# - Validate all templates

# 3. Save merged result
cp merged-templates.yaml config/sql_intent_templates/examples/contact/contact-templates.yaml
```

---

## Template Categories Generated

With enriched queries, you should get templates for:

### **Basic Operations**
- ✅ List all users (with pagination)

### **Search Operations**
- ✅ Search by name (partial match)
- ✅ Search by exact email
- ✅ Search by email domain

### **Filtering**
- ✅ Filter by exact age
- ✅ Filter by age range (BETWEEN)
- ✅ Filter older than X
- ✅ Filter younger than X
- ✅ Filter by exact city
- ✅ Filter by city + age range (multi-field)
- ✅ Search name + filter by city (multi-field)

### **Aggregations**
- ✅ Count all users
- ✅ Count users by city (GROUP BY)
- ✅ Count users in specific city
- ✅ Count users by age range
- ✅ Average user age
- ✅ Age statistics (min, max, avg, count)

### **Sorting**
- ✅ Order by name (alphabetical)
- ✅ Order by age (oldest/youngest first)
- ✅ Order by creation date (recent first)

### **Top N**
- ✅ Get N oldest users
- ✅ Get N youngest users
- ✅ Get N most recent users

### **Existence Checks**
- ✅ Check if user exists by email
- ✅ Check if user exists by name pattern

---

## Validation and Testing

### 1. Verify Template Count

```bash
# Check how many templates were generated
grep "^- id:" config/sql_intent_templates/examples/contact/contact-templates.yaml | wc -l
```

**Expected:** 20-25 templates (instead of 2)

### 2. Verify Template Diversity

```bash
# List all template IDs to check variety
grep "^- id:" config/sql_intent_templates/examples/contact/contact-templates.yaml
```

**Expected:** Different IDs like:
- `list_all_users`
- `search_users_by_name_partial`
- `filter_users_by_exact_age`
- `filter_users_by_age_range`
- `count_users_by_city`
- `average_user_age`
- etc.

### 3. Test Templates with ORBIT

```bash
# Start ORBIT server
python main.py

# In another terminal, test various queries:
curl -X POST http://localhost:8718/api/v1/chat \
  -H "Content-Type: application/json" \
  -H "x-api-key: demo-contact-key" \
  -d '{
    "session_id": "test-session",
    "message": "Show me users from New York aged 25-35",
    "adapters": ["intent-sql-sqlite-contact"]
  }'
```

### 4. Check Template Matching

Enable debug logging to see which templates are matched:

```python
# In config/config.yaml
logging:
  level: DEBUG
```

Then test queries and check logs for template matching details.

---

## Customization Tips

### Increase Template Diversity Further

If you still want MORE specific templates, adjust these settings:

```yaml
# In configs/contact-config.yaml
generation:
  similarity_threshold: 0.2  # Lower = more templates (was 0.3)
  max_examples_per_template: 3  # Fewer examples = more templates (was 5)
```

### Add Your Own Query Categories

Edit `contact_test_queries_enriched.md` and add sections like:

```markdown
## Category 26: Users by Age Decade
<!-- Intent: filter, Entity: users, Filter: age (decade) -->

Show me users in their 20s
Find users in their 30s
Get users in their 40s
```

### Tune Grouping Weights

Adjust feature weights to emphasize what matters:

```yaml
# In configs/contact-config.yaml
grouping:
  feature_weights:
    search_field: 0.40  # Increase if field differences are most important
    filter_type: 0.30   # Increase if filter type (exact vs range) is key
    intent: 0.15        # Decrease if most queries have same intent
```

---

## Troubleshooting

### Still Getting Generic Templates?

**Problem:** All queries grouped into 1-2 templates

**Solutions:**
1. Check similarity threshold: Should be ≤ 0.3
2. Verify enriched queries file is being used (not the original)
3. Add more explicit category markers in test queries
4. Check template generator logs for grouping decisions

### Templates Too Specific?

**Problem:** 100+ templates with minimal differences

**Solutions:**
1. Increase similarity threshold: 0.3 → 0.5
2. Increase max_examples_per_template: 5 → 10
3. Review and merge similar templates manually

### Parameter Binding Errors?

**Problem:** "Incorrect number of bindings supplied"

**Solution:** The updated `template_generator.py` automatically fixes null defaults, but if you still have issues:
1. Check templates for `default: null` in parameters
2. Replace with actual values: `default: 100` (limit), `default: 0` (offset)
3. Or make parameter required: `required: true` (and remove default)

---

## Next Steps

### 1. Generate Production Templates

Use the hybrid approach to create your production template library:
- Start with seed templates (proven quality)
- Add auto-generated templates for coverage
- Manually review and test each template
- Mark approved templates: `approved: true`

### 2. Create Custom Templates

For specialized queries, manually add templates following the seed template structure.

### 3. Expand to Other Schemas

Apply this enrichment approach to your other examples:
- classified-data
- customer-orders
- library

### 4. Continuous Improvement

- Collect real user queries
- Identify gaps in template coverage
- Add new categories to enriched queries
- Regenerate templates periodically

---

## Summary

**Before Enrichment:**
- 150 diverse test queries → 2 generic templates ❌

**After Enrichment:**
- 25 categorized query groups → 20-25 specific templates ✅

**Key Changes:**
1. ✅ Lowered similarity threshold (0.7 → 0.3)
2. ✅ Reweighted grouping features (emphasize differentiators)
3. ✅ Created categorized test queries
4. ✅ Provided seed templates as quality benchmark

**Result:**
- More accurate query matching
- Better user experience
- Comprehensive query coverage
- Production-ready template library
