# Intent Configuration Unification Plan

## Overview

Analysis of the current configuration structure for the Intent SQL system reveals opportunities for simplification. This document outlines a plan to unify the scattered configurations into a single, comprehensive configuration file.

## Current Configuration Structure

### Template Generator Config (`utils/sql-intent-template/template_generator_config.yaml`)
- **Purpose**: AI-driven template generation
- **Size**: 152 lines
- **Focus**: Inference, validation, schema analysis, grouping
- **Key Sections**:
  - `generation`: Core generation settings and defaults
  - `inference`: AI model parameters for analysis and SQL generation
  - `validation`: Rules for validating generated templates
  - `schema`: Settings for database schema analysis
  - `grouping`: Rules for grouping similar queries
  - `output`: Formatting options for generated templates

### Intent Retriever Config (in `base_intent_sql_retriever.py`)
- **Purpose**: Runtime configuration for intent-based SQL retrieval
- **Location**: Embedded in retriever code as intent-specific config
- **Key Settings**:
  - Template storage and ChromaDB settings
  - Domain configuration paths
  - Confidence thresholds
  - Parameter extraction settings

## Problems with Current Structure

1. **Configuration Scattered**: Settings spread across multiple files and code
2. **Duplication**: Similar settings defined in different places
3. **Maintenance**: Hard to manage and update configurations
4. **Discoverability**: Difficult to find all intent-related settings

## Proposed Unified Configuration Schema

### File Structure: `config/intent_config.yaml`

```yaml
# intent_config.yaml - Unified Intent SQL Configuration

# Core intent settings
intent:
  confidence_threshold: 0.75
  max_templates: 5
  template_collection_name: "intent_query_templates"
  
  # Domain configuration
  domain:
    config_path: "examples/postgres/customer_order_domain.yaml"
    vocabulary_enabled: true
    
  # Template library settings  
  templates:
    library_path: "examples/postgres/intent_templates.yaml"
    auto_reload: true
    force_reload: false

# Template generation settings (AI-powered)
generation:
  enabled: true
  max_examples_per_template: 10
  similarity_threshold: 0.8
  
  # Default template metadata
  defaults:
    version: "1.0.0"
    approved: false
    result_format: "table"
  
  # Template categories
  categories:
    - customer_queries
    - order_queries
    - analytics_queries
    - location_queries
    - status_queries
    - payment_queries

# AI inference settings
inference:
  provider: "ollama"  # Can override main config
  
  # Model parameters for different tasks
  analysis:
    temperature: 0.1
    max_tokens: 1024
    
  sql_generation:
    temperature: 0.2
    max_tokens: 2048
    
  parameter_extraction:
    temperature: 0.1
    max_tokens: 512

# Template storage (ChromaDB)
storage:
  type: "chromadb"
  persist: true
  persist_path: "./chroma_db/intent"
  collection_name: "intent_query_templates"
  
  # Collection settings
  distance_metric: "cosine"
  embedding_function: "auto"  # Use main embedding config

# Validation rules
validation:
  # Required template fields
  required_fields:
    - id
    - description
    - sql_template
    - parameters
    - nl_examples
    
  # Constraints
  min_examples: 3
  max_sql_length: 5000
  
  # Parameter validation
  parameters:
    valid_types:
      - string
      - integer
      - decimal
      - date
      - datetime
      - boolean
      - enum
    required_fields:
      - name
      - type
      - description
      - required

# Schema analysis (for generation)
schema:
  include_tables: []  # Empty = all tables
  exclude_tables:
    - migrations
    - schema_version
    
  # Special column patterns
  special_columns:
    email:
      pattern: ".*email.*"
      format: "email"
    phone:
      pattern: ".*phone.*" 
      format: "phone"
    date:
      pattern: ".*(date|_at)$"
      format: "date"
    amount:
      pattern: ".*(amount|total|price|cost).*"
      format: "currency"

# Query processing
processing:
  # Query grouping for template generation
  grouping:
    features:
      - intent
      - primary_entity
      - secondary_entity
      - aggregations
      - filters
    
    feature_weights:
      intent: 0.3
      primary_entity: 0.3
      secondary_entity: 0.2
      aggregations: 0.1
      filters: 0.1
  
  # Parameter extraction
  parameters:
    auto_wildcards: true  # Add % for LIKE queries
    validate_types: true
    apply_defaults: true

# Output formatting
output:
  sort_by: "primary_entity"
  group_by_category: true
  
  # Response generation
  response:
    domain_aware: true
    include_metadata: true
    format: "natural"  # "natural", "structured", "table"
  
  # Metadata to include
  include_metadata:
    - created_at
    - created_by
    - generator_version
    - validation_status
    - template_id
    - similarity_score
    - parameters_used
```

## Configuration Mapping

### From Template Generator Config → Unified

| Original Section | Unified Location | Notes |
|-----------------|------------------|-------|
| `generation.*` | `generation.*` | Direct mapping |
| `inference.*` | `inference.*` | Direct mapping |
| `validation.*` | `validation.*` | Direct mapping |
| `schema.*` | `schema.*` | Direct mapping |
| `grouping.*` | `processing.grouping.*` | Moved under processing |
| `output.*` | `output.*` | Direct mapping |

### From Intent Retriever Code → Unified

| Original Setting | Unified Location | Notes |
|-----------------|------------------|-------|
| `confidence_threshold` | `intent.confidence_threshold` | Core intent setting |
| `max_templates` | `intent.max_templates` | Core intent setting |
| `template_collection_name` | `intent.template_collection_name` | Core intent setting |
| ChromaDB settings | `storage.*` | Unified storage config |
| Domain settings | `intent.domain.*` | Domain configuration |

### New Unified Sections

- **`processing.*`**: Combines query processing logic from multiple sources
- **`intent.*`**: Core intent-specific settings in one place
- **`storage.*`**: Unified storage configuration for all storage needs

## Benefits of Unified Approach

1. **Single Configuration File**: One `intent_config.yaml` instead of multiple scattered configs
2. **Clear Separation**: Logical sections for different purposes (generation, storage, validation, etc.)
3. **Backward Compatibility**: Can maintain existing config paths during transition
4. **Flexibility**: Sections can be enabled/disabled as needed
5. **Inheritance**: Can inherit from main config for common settings like inference provider
6. **Maintainability**: Easier to update and manage all intent-related settings
7. **Discoverability**: All intent settings in one place
8. **Validation**: Single schema for validating all intent configurations

## Implementation Plan

### Phase 1: Create Unified Config
**Objective**: Establish the unified configuration structure

**Tasks**:
1. Create `config/intent_config.yaml` with unified schema
2. Add config loader utility to handle the unified format
3. Create configuration validation schema
4. Update `template_generator.py` to use unified config

**Files to Modify**:
- Create: `config/intent_config.yaml`
- Create: `utils/intent_config_loader.py`
- Modify: `utils/sql-intent-template/template_generator.py`

### Phase 2: Update Intent Retriever
**Objective**: Migrate intent retrieval system to use unified config

**Tasks**:
1. Modify `base_intent_sql_retriever.py` to load from unified config
2. Update domain-aware components to use new config structure
3. Update ChromaDB initialization to use unified storage config
4. Maintain backward compatibility with existing config paths

**Files to Modify**:
- `server/retrievers/implementations/intent/base_intent_sql_retriever.py`
- `server/retrievers/implementations/intent/domain_aware_extractor.py`
- `server/retrievers/implementations/intent/domain_aware_response_generator.py`
- `server/retrievers/implementations/intent/template_reranker.py`

### Phase 3: Validation & Testing
**Objective**: Ensure all functionality works with unified config

**Tasks**:
1. Test template generation with unified config
2. Test intent retrieval with unified config
3. Verify all existing functionality works
4. Run regression tests on intent SQL functionality
5. Test configuration validation

**Test Areas**:
- Template generation from test queries
- Intent-based SQL query execution
- Parameter extraction and validation
- Domain-aware response generation
- ChromaDB template storage and retrieval

### Phase 4: Documentation & Migration
**Objective**: Complete the transition and provide migration support

**Tasks**:
1. Update documentation to reflect unified configuration
2. Provide migration guide for existing installations
3. Add configuration validation and error messages
4. Create example configurations for different use cases
5. Update README files and usage examples

**Documentation Updates**:
- Configuration reference documentation
- Migration guide from old to new config
- Example configurations
- Troubleshooting guide

## Migration Strategy

### Backward Compatibility

During transition, support both old and new configuration methods:

```python
def load_intent_config(config_path=None):
    """Load intent configuration with backward compatibility"""
    
    # Try new unified config first
    unified_config_path = config_path or "config/intent_config.yaml"
    if Path(unified_config_path).exists():
        return load_unified_config(unified_config_path)
    
    # Fall back to old scattered configs
    logger.warning("Using legacy configuration. Consider migrating to unified config.")
    return load_legacy_configs()
```

### Migration Utility

Create a migration utility to convert existing configurations:

```bash
python utils/migrate_intent_config.py \
    --template-config utils/sql-intent-template/template_generator_config.yaml \
    --output config/intent_config.yaml
```

## Configuration Validation

### Schema Validation

Use JSON Schema or similar to validate configuration:

```python
from jsonschema import validate

intent_config_schema = {
    "type": "object",
    "properties": {
        "intent": {"type": "object", "required": ["confidence_threshold"]},
        "generation": {"type": "object"},
        "storage": {"type": "object", "required": ["type"]},
        # ... more schema definitions
    },
    "required": ["intent", "storage"]
}

def validate_intent_config(config):
    """Validate intent configuration against schema"""
    validate(instance=config, schema=intent_config_schema)
```

### Runtime Validation

Add runtime checks for configuration consistency:

```python
def validate_config_consistency(config):
    """Validate configuration for internal consistency"""
    errors = []
    
    # Check storage path exists
    if config['storage']['persist']:
        if not Path(config['storage']['persist_path']).exists():
            errors.append("Storage persist_path does not exist")
    
    # Check domain config exists
    domain_path = config['intent']['domain']['config_path']
    if not Path(domain_path).exists():
        errors.append(f"Domain config not found: {domain_path}")
    
    return errors
```

## Success Metrics

1. **Configuration Consolidation**: All intent settings in single file
2. **Backward Compatibility**: Existing setups continue to work
3. **Improved Maintainability**: Easier to find and update settings
4. **Validation**: Clear error messages for invalid configurations
5. **Documentation**: Complete documentation of unified configuration

## Risks and Mitigation

### Risk: Breaking Existing Installations
**Mitigation**: Maintain backward compatibility during transition period

### Risk: Configuration Complexity
**Mitigation**: Provide clear examples and good defaults

### Risk: Migration Effort
**Mitigation**: Provide automated migration tools and clear documentation

## Timeline Estimate

- **Phase 1**: 2-3 days
- **Phase 2**: 3-4 days  
- **Phase 3**: 2-3 days
- **Phase 4**: 2-3 days

**Total**: ~10-13 days for complete implementation and testing

## Conclusion

Unifying the intent configuration will significantly improve the maintainability and usability of the intent SQL system. The proposed structure provides clear organization while maintaining all existing functionality and providing a path for future enhancements.

The implementation plan ensures a smooth transition with minimal disruption to existing installations while providing immediate benefits in terms of configuration management and system understanding.