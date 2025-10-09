# Validation Tools Quick Reference

This directory includes three validation scripts to ensure generated domain configurations and SQL templates are compatible with the Orbit Intent SQL Retriever adapter.

---

## 1. validate_output.py

**Purpose:** Validates file structure against the required schema

**Usage:**
```bash
python validate_output.py <domain_config.yaml> <templates.yaml>
```

**Example:**
```bash
python validate_output.py contact-example-domain.yaml contact-example-output.yaml
```

**What it checks:**
- ✅ Required fields present
- ✅ Field data types valid
- ✅ Entity and relationship structures
- ✅ Template parameters correct
- ✅ Semantic tags present

**When to use:**
- After generating new templates
- Before deploying to production
- First step in validation workflow

**View full documentation:**
```bash
python -c "import validate_output; print(validate_output.__doc__)"
```

---

## 2. compare_structures.py

**Purpose:** Compare generated files with official reference examples

**Usage:**
```bash
python compare_structures.py <gen_domain> <gen_templates> <ref_domain> <ref_templates>
```

**Example:**
```bash
python compare_structures.py \
  contact-example-domain.yaml \
  contact-example-output.yaml \
  ../../config/sql_intent_templates/examples/customer-orders/customer_order_domain.yaml \
  ../../config/sql_intent_templates/examples/customer-orders/postgres_customer_orders.yaml
```

**What it checks:**
- 📊 Structure differences from reference
- ⚠️  Missing fields
- ✨ Extra fields
- ✅ Critical field matching

**When to use:**
- To understand structural differences
- When basing on existing examples
- To verify completeness

**View full documentation:**
```bash
python -c "import compare_structures; print(compare_structures.__doc__)"
```

---

## 3. test_adapter_loading.py

**Purpose:** Test that IntentAdapter can load the generated files

**Usage:**
```bash
python test_adapter_loading.py <domain_config.yaml> <templates.yaml>
```

**Example:**
```bash
# Must run from Orbit project root!
cd /path/to/orbit
python utils/sql-intent-template/test_adapter_loading.py \
  utils/sql-intent-template/contact-example-domain.yaml \
  utils/sql-intent-template/contact-example-output.yaml
```

**What it checks:**
- ✅ IntentAdapter imports successfully
- ✅ Domain config loads
- ✅ Templates load
- ✅ Retrieval methods work

**Requirements:**
- Must run from Orbit project root
- Virtual environment activated
- Dependencies installed

**When to use:**
- Final validation before deployment
- Debugging adapter loading issues
- Integration testing

**View full documentation:**
```bash
python -c "import test_adapter_loading; print(test_adapter_loading.__doc__)"
```

---

## Recommended Validation Workflow

### Step 1: Validate Structure
```bash
python validate_output.py my-domain.yaml my-templates.yaml
```
**Expected:** ✅ ALL CHECKS PASSED

### Step 2: Compare with Reference (Optional)
```bash
python compare_structures.py \
  my-domain.yaml \
  my-templates.yaml \
  ../../config/sql_intent_templates/examples/customer-orders/customer_order_domain.yaml \
  ../../config/sql_intent_templates/examples/customer-orders/postgres_customer_orders.yaml
```
**Expected:** ✅ NO ERRORS (warnings are OK)

### Step 3: Test Adapter Loading
```bash
cd ../../  # Go to Orbit root
python utils/sql-intent-template/test_adapter_loading.py \
  utils/sql-intent-template/my-domain.yaml \
  utils/sql-intent-template/my-templates.yaml
```
**Expected:** ✅ ALL ADAPTER LOADING TESTS PASSED

### Step 4: Deploy
If all validations pass:
1. Copy files to `config/sql_intent_templates/`
2. Update `config/adapters.yaml`
3. Start Orbit server
4. Test with real queries

---

## Exit Codes

All scripts use standard exit codes:
- **0** = Success (validation passed)
- **1** = Failure (validation failed or error)

Use in scripts:
```bash
if python validate_output.py domain.yaml templates.yaml; then
  echo "✅ Validation passed"
else
  echo "❌ Validation failed"
  exit 1
fi
```

---

## Troubleshooting

### "File not found" error
- Check file paths are correct
- Use absolute paths if relative paths fail
- Ensure you're in the correct directory

### "No module named 'utils.lazy_loader'"
- You're running test_adapter_loading.py from wrong directory
- Must run from Orbit project root: `cd /path/to/orbit`

### "Import error" or "Module not found"
- Activate virtual environment: `source venv/bin/activate`
- Install dependencies: `pip install -r requirements.txt`

### Validation fails unexpectedly
1. Check YAML syntax with: `python -c "import yaml; yaml.safe_load(open('file.yaml'))"`
2. Review error messages for specific missing fields
3. Compare with working examples in `config/sql_intent_templates/examples/`
4. Check VALIDATION_REPORT.md for detailed requirements

---

## See Also

- **VALIDATION_REPORT.md** - Full validation report and deployment guide
- **README.md** - Generator usage and configuration
- **SQL_DIALECT_GUIDE.md** - SQL dialect configuration
- **docs/intent-sql-rag-system.md** - Intent adapter documentation
- **config/sql_intent_templates/examples/** - Reference implementations
