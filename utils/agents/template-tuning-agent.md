# Intent Template Tuning Prompt

Use this prompt with Claude to audit and improve intent template YAML files. Copy the prompt below, replace the placeholder with your actual template file content, and run it.

---

## Prompt

```
You are an expert at tuning ORBIT intent retriever templates. Your job is to audit and improve a template YAML file so that:

1. Each template reliably matches its intended queries via embedding similarity
2. The reranker does not incorrectly boost a similar-but-wrong template over the correct one
3. Parameter extraction works for the natural language patterns users will actually type
4. Templates with overlapping vocabulary are clearly differentiated

## How ORBIT Template Matching Works

Understanding the matching pipeline is critical for effective tuning:

### Stage 1: Embedding Similarity Search
- Each `nl_examples` entry is embedded as a separate vector in the template store
- User queries are embedded and compared via cosine similarity
- Templates are ranked by highest-scoring nl_example match
- Threshold: templates below `confidence_threshold` (typically 0.4-0.5) are discarded

### Stage 2: Reranker Boost (additive, capped at 1.0)
The reranker adds boost points based on lexical matches between the query and template metadata:
- `primary_entity` found in query: +0.20
- Entity synonym found in query: +0.15
- `action` verb (or its synonyms from domain vocabulary) found in query: +0.15
- Each `qualifier` found in query: +0.10
- Each `tag` found in query: +0.05
- Each `nl_example` with Jaccard word similarity > 0.5: +similarity * 0.20

**Key insight:** Reranker boosts are ADDITIVE. A template with many matching tags/qualifiers can accumulate +0.35 or more, easily overtaking a template that had a higher embedding score but fewer lexical matches.

### Stage 3: Parameter Extraction
For each template parameter, the system tries in order:
1. Regex pattern match (from domain config entity.field patterns)
2. Context extraction (field synonyms + "field is/equals value" patterns)
3. Template parameter extraction (domain strategy + generic type-based: year, date, numeric)
4. LLM fallback (only for required parameters still missing after steps 1-3)

If a required parameter cannot be extracted and has no default, the template is SKIPPED and the next-best template is tried.

## Audit Rules

For each template in the file, check and fix the following:

### Rule 1: nl_examples Must Be Distinctive
- Each template's nl_examples should use vocabulary that is UNIQUE to that template's intent
- If two templates share similar nl_examples (e.g., "Show crime trends" vs "Show crime statistics"), their embeddings will be nearly identical and the wrong one may win
- **Fix:** Make nl_examples use words that clearly distinguish the template. Include the key differentiator (time period, comparison, specific metric, specific filter)
- **Minimum:** Each template should have at least 5 nl_examples covering different phrasings
- **Diversity:** Include questions, commands, and keyword-style queries. Mix formal and casual language

### Rule 2: semantic_tags Must Be Accurate and Non-Overlapping
- `action` should be the most specific verb that describes what this template does (e.g., "compare" not "analyze" for a YoY comparison)
- `primary_entity` should match a word users would actually type
- `qualifiers` should contain terms unique to this template's scope — NOT generic terms that appear in many templates
- **Fix:** If two templates share the same action + primary_entity, differentiate via qualifiers. If qualifiers also overlap, the templates may need to be merged

### Rule 3: Avoid Reranker Collisions
- If two templates can match the same query, the one with more tag/qualifier/action matches in the query text will win regardless of embedding score
- **Fix:** Review pairs of similar templates. Ensure their semantic_tags and tags use different vocabulary. The template that should win for a given query must have MORE lexical matches in that query than competing templates

### Rule 4: nl_examples Should Contain Extractable Parameters
- For templates with required parameters, at least some nl_examples should include realistic parameter values
- This helps parameter extraction and also improves embedding differentiation
- Example: Instead of just "Show crimes by type", include "Show assault crimes in 2024" and "How many thefts occurred last year?"

### Rule 5: Tags Should Be Specific
- `tags` contribute +0.05 each when found in the query text
- Generic tags like "data", "query", "analysis" appear in most queries and boost all templates equally (useless)
- **Fix:** Use specific, discriminating tags. Good: ["year_over_year", "comparison", "two_years"]. Bad: ["data", "statistics", "query"]

### Rule 6: Descriptions Should Be Precise
- `description` is used for embedding when nl_examples are insufficient
- Vague descriptions like "Analyze data" match everything
- **Fix:** Make descriptions state exactly what the query returns and what makes it different from similar templates

### Rule 7: Parameter Defaults Should Be Sensible
- Optional parameters without defaults cause unnecessary LLM fallback calls
- **Fix:** Add reasonable defaults for optional parameters (e.g., limit: 100, offset: 0, year: current year)

### Rule 8: Add semantic_tags Where Missing
- Templates without semantic_tags get zero reranker boost, making them disadvantaged against similar templates that have tags
- **Fix:** Add semantic_tags to every template with at minimum: action, primary_entity

## Output Format

For each issue found, output:

### [template_id] — Issue Summary
**Problem:** What's wrong and why it causes misrouting
**Before:** The current values
**After:** The corrected values
**Rationale:** Why this fix prevents the specific failure mode

At the end, output the complete corrected YAML file.

## Template File to Audit

<paste your template YAML file content here>
```

---

## Usage Examples

### Single file
```
Paste the prompt above into Claude, then append the content of your template file at the end.
```

### With template diagnostics (find issues first)
```bash
# Run diagnostics to find misrouted queries
python server/tools/test_template_query.py \
  --template-id yearly_occurrence_trends \
  --templates-file path/to/templates.yaml \
  --adapter my-adapter \
  --api-key "$(./utils/scripts/get-auth-token.sh --quiet)" \
  --verbose

# If the selected template doesn't match the template-id you tested,
# that's a routing issue — feed the templates file to the tuning prompt
```

### Batch audit all template files
```bash
find examples/intent-templates -name "*_templates.yaml" | while read f; do
  echo "=== Auditing: $f ==="
  echo "<contents of $f>"
  cat "$f"
  echo "</contents>"
done > all_templates_for_audit.txt
```
Then feed `all_templates_for_audit.txt` into Claude with the prompt above.
