# Comprehensive Plan: Generalizing the Intent SQL Retriever

**Date:** December 21, 2024
**Last Updated:** December 21, 2024

**Author:** Claude

## Implementation Status

### ✅ Phase 1: COMPLETED (Sep 21, 2025)

**Goal:** Extract all hardcoded customer order logic from core components and delegate to domain strategy.

**Files Modified:**
- `server/retrievers/implementations/intent/domain_strategies/base.py` - Extended interface
- `server/retrievers/implementations/intent/domain_strategies/customer_order.py` - Added new methods
- `server/retrievers/implementations/intent/domain/extraction/value_extractor.py` - Made domain-agnostic
- `server/retrievers/implementations/intent/domain/extraction/extractor.py` - Wired strategy

**Files Added:**
- `server/tests/intent/test_domain_extraction_refactor.py` - Comprehensive test suite

**Key Achievements:**
1. **Extended DomainStrategy Interface:**
   - Added `extract_domain_parameters()` for domain-specific extraction
   - Added `get_semantic_extractors()` for semantic type mapping
   - Added `get_summary_field_priority()` for field prioritization

2. **CustomerOrderStrategy Implementation:**
   - Migrated all order ID extraction logic (single and multiple)
   - Migrated amount/currency extraction logic
   - Migrated time period extraction logic (days, weeks, months, etc.)
   - Fixed bug where `order_ids` parameter incorrectly matched single order condition

3. **ValueExtractor Refactoring:**
   - Now accepts optional `DomainStrategy` in constructor
   - `extract_template_parameter()` delegates to strategy first, falls back to generic
   - Removed 176 lines of hardcoded customer order logic
   - Maintains backward compatibility for domains without strategies

4. **DomainParameterExtractor Integration:**
   - Automatically loads strategy from registry based on domain name
   - Passes strategy to ValueExtractor during initialization
   - No changes required to calling code

5. **Comprehensive Testing:**
   - 6 new test cases covering all extraction scenarios
   - Verified customer order functionality unchanged
   - Verified generic fallback works for emails, dates, enums
   - All existing tests continue to pass (20/20)

**Result:** Core extraction logic is now completely domain-agnostic while maintaining full backward compatibility.

### ✅ Phase 2: COMPLETED (Sep 21, 2025)

**Goal:** Make ResponseFormatter configuration-driven by removing hardcoded summary field selection.

**Files Modified:**
- `server/retrievers/implementations/intent/domain/response/formatters.py` - Refactored `_get_summary_fields()`
- `server/retrievers/implementations/intent/domain/response/generator.py` - Added domain strategy support
- `server/retrievers/base/intent_sql_base.py` - Wired domain strategy to response generator
- `server/tests/intent/test_domain_extraction_refactor.py` - Added comprehensive tests

**Key Achievements:**
1. **ResponseFormatter Refactoring:**
   - Added optional `domain_strategy` parameter to constructor
   - Replaced hardcoded keyword matching with strategy-driven prioritization
   - Added support for configuration-based field priorities
   - Implemented semantic type-based prioritization
   - Added generic fallback for domains without strategies

2. **Domain Strategy Integration:**
   - ResponseFormatter now uses `get_summary_field_priority()` from domain strategy
   - Maintains backward compatibility with existing code
   - Ensures all fields are included (even with low priority)

3. **Comprehensive Testing:**
   - Added 3 new test cases covering all scenarios
   - Verified strategy-driven prioritization works correctly
   - Verified generic fallback works without strategy
   - Verified correct priority hierarchy ordering
   - All existing tests continue to pass (9/9)

4. **Bug Fix:**
   - Fixed AttributeError when domain_config is a dictionary
   - Added proper type checking and conversion to DomainConfig object

**Result:** ResponseFormatter is now fully domain-agnostic and configuration-driven while maintaining complete backward compatibility.

### 🔄 Phase 3: NEXT STEPS
- **Primary Goal:** Enhance domain configuration schema with semantic types and priorities
- **Target:** Add semantic metadata to domain YAML configuration
- **Files to modify:**
  - `server/retrievers/implementations/intent/domain/config.py` - Add semantic metadata support
  - Domain YAML files - Add semantic types and priorities
  - `config/sql_intent_templates/examples/customer-orders/customer_order_domain.yaml` - Example implementation

### ⏳ Phase 4-5: PENDING
- Phase 4: Implement GenericDomainStrategy for new domains
- Phase 5: Integration and comprehensive testing

---

## Executive Summary

This document outlines a comprehensive refactoring plan to transform the Intent SQL Retriever from a customer-order-specific implementation into a fully domain-agnostic framework. The refactoring will enable the system to work with any database schema and business domain purely through YAML configuration, without requiring any Python code changes.

## 1. Current State Analysis

### Architecture Strengths
- **Good separation:** `DomainConfig` class provides a solid generic foundation
- **Plugin pattern:** `DomainStrategy` and registry enable domain-specific extensions
- **Modular extraction:** Pattern builder, value extractor, and LLM fallback are well-separated

### Critical Issues Requiring Refactoring

#### 1.1 Hardcoded Customer Order Logic in `ValueExtractor`
**File:** `server/retrievers/implementations/intent/domain/extraction/value_extractor.py`

**Lines 172-348:** The `extract_template_parameter` method contains extensive hardcoded logic for:
- Order ID extraction (lines 180-197, 199-239)
- Amount parameters with currency patterns (lines 241-259)
- Days/time period extraction (lines 262-298)
- Customer-specific patterns

#### 1.2 Hardcoded Summary Field Selection
**File:** `server/retrievers/implementations/intent/domain/response/formatters.py`

**Lines 235-264:** The `_get_summary_fields` method uses hardcoded keyword matching for field prioritization rather than configuration-driven selection.

## 2. Refactoring Implementation Plan

### Phase 1: Enhance Domain Strategy Interface

#### Step 1.1: Extend `DomainStrategy` Base Class
```python
# server/retrievers/implementations/intent/domain_strategies/base.py

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List

class DomainStrategy(ABC):
    """Base class for domain-specific pattern matching and logic"""

    @abstractmethod
    def get_domain_names(self) -> list:
        """Return list of domain names this strategy handles"""
        pass

    @abstractmethod
    def calculate_domain_boost(self, template_info: Dict, query: str, domain_config: Dict) -> float:
        """Calculate domain-specific boost for a template"""
        pass

    @abstractmethod
    def get_pattern_matchers(self) -> Dict[str, Any]:
        """Return domain-specific pattern matching functions"""
        pass

    # NEW METHODS
    @abstractmethod
    def extract_domain_parameters(self, query: str, param: Dict, domain_config: Any) -> Optional[Any]:
        """
        Extract domain-specific parameters that require special logic.

        Args:
            query: User's query text
            param: Parameter definition from template
            domain_config: DomainConfig instance

        Returns:
            Extracted value or None if not found
        """
        pass

    @abstractmethod
    def get_semantic_extractors(self) -> Dict[str, callable]:
        """
        Return semantic type extractors for this domain.

        Returns:
            Dict mapping semantic types to extraction functions
        """
        pass

    @abstractmethod
    def get_summary_field_priority(self, field_name: str, field_config: Any) -> int:
        """
        Get priority for including field in summaries.

        Returns:
            Priority score (higher = more important), or 0 if not relevant
        """
        pass
```

#### Step 1.2: Migrate Customer Order Logic to Strategy
```python
# server/retrievers/implementations/intent/domain_strategies/customer_order.py

class CustomerOrderStrategy(DomainStrategy):

    def extract_domain_parameters(self, query: str, param: Dict, domain_config: Any) -> Optional[Any]:
        """Extract customer order specific parameters"""
        param_name = param.get('name', '')
        param_type = param.get('type') or param.get('data_type', 'string')

        # Order ID extraction
        if 'order' in param_name.lower() and ('id' in param_name.lower() or 'number' in param_name.lower()):
            return self._extract_order_id(query, param_type)

        # Multiple order IDs
        if 'order_ids' in param_name.lower():
            return self._extract_order_ids(query)

        # Amount extraction
        if 'amount' in param_name.lower():
            return self._extract_amount(query, param_type)

        # Days/time period
        if 'days' in param_name.lower():
            return self._extract_days(query)

        return None

    def _extract_order_id(self, query: str, param_type: str) -> Optional[Any]:
        """Extract single order ID"""
        patterns = [
            r'order\s+(?:number\s+|#\s*|id\s+)?(\d+)',
            r'#\s*(\d+)',
            r'(?:order|id|number)\s+(\d+)',
        ]
        # [Implementation migrated from ValueExtractor]

    def _extract_order_ids(self, query: str) -> Optional[str]:
        """Extract multiple order IDs"""
        # [Implementation migrated from ValueExtractor]

    def _extract_amount(self, query: str, param_type: str) -> Optional[Any]:
        """Extract monetary amounts"""
        # [Implementation migrated from ValueExtractor]

    def _extract_days(self, query: str) -> Optional[int]:
        """Extract time periods in days"""
        # [Implementation migrated from ValueExtractor]

    def get_semantic_extractors(self) -> Dict[str, callable]:
        """Return e-commerce specific semantic extractors"""
        return {
            'order_identifier': self._extract_order_id,
            'monetary_amount': self._extract_amount,
            'time_period_days': self._extract_days,
            'customer_email': self._extract_email,
            'tracking_number': self._extract_tracking_number,
        }

    def get_summary_field_priority(self, field_name: str, field_config: Any) -> int:
        """Get field priority for e-commerce summaries"""
        priorities = {
            'order_id': 100,
            'customer_name': 90,
            'total': 85,
            'status': 80,
            'order_date': 75,
            'payment_method': 70,
            'shipping_address': 60,
        }

        # Check direct field name match
        if field_name in priorities:
            return priorities[field_name]

        # Check field name patterns
        field_lower = field_name.lower()
        if 'id' in field_lower or 'number' in field_lower:
            return 95
        if 'name' in field_lower:
            return 85
        if 'amount' in field_lower or 'total' in field_lower:
            return 80
        if 'date' in field_lower:
            return 70
        if 'status' in field_lower or 'state' in field_lower:
            return 75

        return 0
```

### Phase 2: Refactor Core Components

#### Step 2.1: Make `ValueExtractor` Domain-Agnostic
```python
# server/retrievers/implementations/intent/domain/extraction/value_extractor.py

class ValueExtractor:
    """Extracts values from user queries using patterns - now domain-agnostic"""

    def __init__(self, domain_config: DomainConfig, patterns: Dict[str, Pattern],
                 domain_strategy: Optional[DomainStrategy] = None):
        """Initialize with optional domain strategy"""
        self.domain_config = domain_config
        self.patterns = patterns
        self.domain_strategy = domain_strategy

    def extract_template_parameter(self, user_query: str, param: Dict) -> Optional[Any]:
        """
        Extract a template parameter - now delegates to domain strategy
        """
        # First try domain strategy if available
        if self.domain_strategy:
            value = self.domain_strategy.extract_domain_parameters(
                user_query, param, self.domain_config
            )
            if value is not None:
                return value

        # Then try semantic type extraction
        semantic_type = param.get('semantic_type')
        if semantic_type and self.domain_strategy:
            extractors = self.domain_strategy.get_semantic_extractors()
            if semantic_type in extractors:
                value = extractors[semantic_type](user_query, param.get('type', 'string'))
                if value is not None:
                    return value

        # Finally, fall back to generic extraction
        return self._extract_generic_parameter(user_query, param)

    def _extract_generic_parameter(self, user_query: str, param: Dict) -> Optional[Any]:
        """Generic parameter extraction for common types"""
        param_type = param.get('type') or param.get('data_type', 'string')

        # Date parameters
        if param_type == 'date':
            return self._extract_date_generic(user_query)

        # Email parameters
        if param_type == 'string' and 'email' in param.get('name', '').lower():
            return self._extract_email_generic(user_query)

        # Enum parameters
        if param_type == 'enum' and 'allowed_values' in param:
            return self._extract_enum_generic(user_query, param['allowed_values'])

        # Generic string with quotes
        if param_type == 'string':
            return self._extract_quoted_string(user_query)

        return None
```

#### Step 2.2: Refactor `ResponseFormatter` for Configuration
```python
# server/retrievers/implementations/intent/domain/response/formatters.py

class ResponseFormatter:
    """Handles deterministic formatting of result data"""

    def __init__(self, domain_config: DomainConfig, domain_strategy: Optional[DomainStrategy] = None):
        """Initialize formatter with domain configuration and optional strategy"""
        self.domain_config = domain_config
        self.domain_strategy = domain_strategy

    def _get_summary_fields(self, sample_result: Dict) -> List[str]:
        """Determine which fields are most important for summary"""
        field_priorities = []

        for field_name in sample_result.keys():
            priority = 0

            # Check domain configuration for priority
            field_config = self._find_field_config(field_name)
            if field_config:
                # Use configured priority
                if hasattr(field_config, 'summary_priority'):
                    priority = field_config.summary_priority
                # Or use semantic type priority
                elif hasattr(field_config, 'semantic_type') and self.domain_strategy:
                    semantic_priorities = {
                        'identifier': 100,
                        'person_name': 90,
                        'monetary_amount': 85,
                        'status': 80,
                        'timestamp': 75,
                        'location': 70,
                        'contact_info': 65,
                    }
                    priority = semantic_priorities.get(field_config.semantic_type, 0)

            # Ask domain strategy for priority
            if self.domain_strategy and priority == 0:
                priority = self.domain_strategy.get_summary_field_priority(field_name, field_config)

            # Generic fallback based on field patterns
            if priority == 0:
                priority = self._get_generic_field_priority(field_name)

            if priority > 0:
                field_priorities.append((field_name, priority))

        # Sort by priority and return top fields
        field_priorities.sort(key=lambda x: x[1], reverse=True)
        return [field for field, _ in field_priorities[:5]]

    def _get_generic_field_priority(self, field_name: str) -> int:
        """Generic priority based on common patterns"""
        field_lower = field_name.lower()

        if 'id' in field_lower:
            return 50
        if 'name' in field_lower or 'title' in field_lower:
            return 45
        if 'status' in field_lower or 'state' in field_lower:
            return 40
        if 'date' in field_lower or 'time' in field_lower:
            return 35
        if 'amount' in field_lower or 'total' in field_lower or 'price' in field_lower:
            return 30

        return 0
```

### Phase 3: Enhance Domain Configuration

#### Step 3.1: Extend Domain YAML Schema
```yaml
# Enhanced schema for domain configuration

domain_name: E-Commerce
description: Customer order management system

# NEW: Domain metadata for strategy selection
domain_type: ecommerce  # Used to select appropriate strategy
semantic_types:          # Define semantic types for fields
  order_identifier:
    description: "Unique identifier for an order"
    patterns: ["order", "id", "number"]
  monetary_amount:
    description: "Currency amounts"
    patterns: ["amount", "total", "price", "cost"]
  time_period:
    description: "Time duration"
    patterns: ["days", "weeks", "months"]

entities:
  customer:
    # ... existing config ...

fields:
  customer:
    name:
      # ... existing config ...
      semantic_type: person_name     # NEW
      summary_priority: 10           # NEW: Explicit priority
      extraction_hints:               # NEW: Hints for extraction
        - look_for_quotes: true
        - capitalization_required: true

    email:
      # ... existing config ...
      semantic_type: contact_email
      summary_priority: 8
      extraction_pattern: '\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'

  order:
    id:
      # ... existing config ...
      semantic_type: order_identifier
      summary_priority: 10
      extraction_hints:
        - patterns: ["order #", "order number", "#"]
        - numeric_required: true

    total:
      # ... existing config ...
      semantic_type: monetary_amount
      summary_priority: 8
      extraction_hints:
        - currency_symbols: ["$", "USD", "dollars"]
        - decimal_places: 2
```

#### Step 3.2: Update `DomainConfig` Class
```python
# server/retrievers/implementations/intent/domain/config.py

@dataclass
class FieldConfig:
    """Enhanced field configuration with semantic metadata"""
    name: str
    data_type: str
    # ... existing fields ...

    # NEW fields
    semantic_type: Optional[str] = None
    summary_priority: Optional[int] = None
    extraction_pattern: Optional[str] = None
    extraction_hints: Optional[Dict[str, Any]] = None

class DomainConfig:
    """Enhanced domain configuration"""

    def __init__(self, config_dict: Dict[str, Any]):
        # ... existing initialization ...

        # NEW: Parse domain metadata
        self.domain_type = config_dict.get('domain_type', 'generic')
        self.semantic_types = config_dict.get('semantic_types', {})

    def get_fields_by_semantic_type(self, semantic_type: str) -> List[FieldConfig]:
        """Get all fields with a specific semantic type"""
        fields = []
        for entity in self.entities.values():
            for field in entity.fields.values():
                if field.semantic_type == semantic_type:
                    fields.append(field)
        return fields
```

### Phase 4: Implement Generic Fallback Strategy

#### Step 4.1: Create `GenericDomainStrategy`
```python
# server/retrievers/implementations/intent/domain_strategies/generic.py

class GenericDomainStrategy(DomainStrategy):
    """Generic strategy for domains without custom implementation"""

    def __init__(self, domain_config: Any):
        self.domain_config = domain_config
        self._build_semantic_extractors()

    def _build_semantic_extractors(self):
        """Build extractors based on semantic type definitions"""
        self.semantic_extractors = {}

        # Build extractors from domain configuration
        for semantic_type, config in self.domain_config.semantic_types.items():
            if 'patterns' in config:
                self.semantic_extractors[semantic_type] = self._create_pattern_extractor(config)

    def extract_domain_parameters(self, query: str, param: Dict, domain_config: Any) -> Optional[Any]:
        """Extract parameters using semantic types and extraction hints"""
        # Check for semantic type
        semantic_type = param.get('semantic_type')
        if semantic_type and semantic_type in self.semantic_extractors:
            return self.semantic_extractors[semantic_type](query, param)

        # Check for extraction pattern in field config
        field_name = param.get('field')
        entity_name = param.get('entity')
        if entity_name and field_name:
            field_config = domain_config.get_field(entity_name, field_name)
            if field_config and field_config.extraction_pattern:
                pattern = re.compile(field_config.extraction_pattern, re.IGNORECASE)
                match = pattern.search(query)
                if match:
                    return self._parse_match(match, param.get('type', 'string'))

        # Use extraction hints if available
        if 'extraction_hints' in param:
            return self._extract_with_hints(query, param)

        return None

    def get_semantic_extractors(self) -> Dict[str, callable]:
        """Return configured semantic extractors"""
        return self.semantic_extractors

    def get_summary_field_priority(self, field_name: str, field_config: Any) -> int:
        """Get priority from configuration"""
        if field_config and hasattr(field_config, 'summary_priority'):
            return field_config.summary_priority

        # Use semantic type priority
        if field_config and hasattr(field_config, 'semantic_type'):
            default_priorities = {
                'identifier': 90,
                'name': 85,
                'status': 80,
                'amount': 75,
                'date': 70,
                'description': 60,
            }

            for key, priority in default_priorities.items():
                if key in field_config.semantic_type.lower():
                    return priority

        return 0

    def _create_pattern_extractor(self, config: Dict) -> callable:
        """Create an extractor function from configuration"""
        def extractor(query: str, param: Dict) -> Optional[Any]:
            patterns = config.get('patterns', [])
            for pattern in patterns:
                regex = rf'\b{pattern}\s*[:=]?\s*([^\s,]+)'
                match = re.search(regex, query, re.IGNORECASE)
                if match:
                    return self._parse_match(match, param.get('type', 'string'))
            return None
        return extractor
```

#### Step 4.2: Update Strategy Registry
```python
# server/retrievers/implementations/intent/domain_strategies/registry.py

class DomainStrategyRegistry:
    """Registry for domain strategies with generic fallback"""

    def __init__(self):
        self.strategies = {}
        self._register_default_strategies()

    def get_strategy(self, domain_name: str, domain_config: Any) -> DomainStrategy:
        """Get strategy for domain, with generic fallback"""
        # Try exact match
        if domain_name in self.strategies:
            return self.strategies[domain_name]

        # Try domain type from config
        if hasattr(domain_config, 'domain_type'):
            domain_type = domain_config.domain_type
            if domain_type in self.strategies:
                return self.strategies[domain_type]

        # Return generic strategy
        return GenericDomainStrategy(domain_config)
```

### Phase 5: Integration Updates

#### Step 5.1: Update `DomainParameterExtractor`
```python
# server/retrievers/implementations/intent/domain/extraction/extractor.py

class DomainParameterExtractor:

    def __init__(self, inference_client, domain_config: Optional[Dict[str, Any]] = None):
        # ... existing initialization ...

        # NEW: Get domain strategy
        registry = DomainStrategyRegistry()
        self.domain_strategy = registry.get_strategy(
            self.domain_config.domain_name,
            self.domain_config
        )

    def _initialize_components(self):
        """Initialize all extraction components with domain strategy"""
        # Build patterns
        self.pattern_builder = PatternBuilder(self.domain_config)
        self.patterns = self.pattern_builder.build_patterns()

        # Initialize extractor WITH domain strategy
        self.value_extractor = ValueExtractor(
            self.domain_config,
            self.patterns,
            self.domain_strategy  # NEW
        )

        # ... rest of initialization ...
```

## 3. Migration Guide

### For Existing Customer Order Domain

1. **Update YAML Configuration:**
   - Add `domain_type: ecommerce`
   - Add `semantic_type` to relevant fields
   - Add `summary_priority` to important fields
   - Add `extraction_hints` where helpful

2. **No Code Changes Required:**
   - The `CustomerOrderStrategy` will be automatically selected
   - All existing functionality preserved
   - Enhanced with configuration-driven features

### For New Domains

1. **Create Domain YAML:**
```yaml
domain_name: Healthcare
domain_type: healthcare  # Or use 'generic' for automatic handling

entities:
  patient:
    # Define entities...

fields:
  patient:
    patient_id:
      semantic_type: patient_identifier
      summary_priority: 10
      extraction_pattern: 'P\d{6}'  # P followed by 6 digits
```

2. **Optional: Create Custom Strategy:**
   - Only if domain has special requirements
   - Inherit from `DomainStrategy`
   - Register in `DomainStrategyRegistry`

3. **Use Without Code Changes:**
   - System automatically uses `GenericDomainStrategy`
   - Extraction works based on configuration
   - Summary fields selected by priority

## 4. Testing Strategy

### Unit Tests
1. **Test `GenericDomainStrategy`:**
   - Parameter extraction with various semantic types
   - Summary field prioritization
   - Pattern-based extraction

2. **Test Refactored `ValueExtractor`:**
   - Generic extraction without strategy
   - Extraction with customer order strategy
   - Extraction with generic strategy

3. **Test `ResponseFormatter`:**
   - Summary generation with priorities
   - Configuration-driven formatting

### Integration Tests
1. **Customer Order Domain:**
   - Ensure all existing tests pass
   - No regression in functionality

2. **New Test Domain:**
   - Create "Healthcare" domain YAML
   - Test end-to-end without custom code
   - Verify extraction and formatting

### Validation Criteria
- ✅ Customer order functionality unchanged
- ✅ New domains work without Python changes
- ✅ Configuration drives all domain-specific behavior
- ✅ Generic strategy handles common patterns
- ✅ Performance remains similar or improves

## 5. Implementation Timeline

### Week 1: Core Refactoring
- Extend `DomainStrategy` interface
- Migrate customer order logic to strategy
- Refactor `ValueExtractor`

### Week 2: Configuration Enhancement
- Enhance domain YAML schema
- Update `DomainConfig` class
- Refactor `ResponseFormatter`

### Week 3: Generic Implementation
- Implement `GenericDomainStrategy`
- Update strategy registry
- Integration updates

### Week 4: Testing & Documentation
- Comprehensive testing
- Migration guide completion
- Documentation updates

## 6. Benefits

### Immediate Benefits
- **True Domain Independence:** Core engine has no domain-specific code
- **Configuration-Driven:** New domains via YAML only
- **Backward Compatible:** Existing functionality preserved

### Long-Term Benefits
- **Maintainability:** Clear separation of concerns
- **Extensibility:** Easy to add new semantic types
- **Reusability:** Generic patterns benefit all domains
- **Scalability:** Can handle unlimited domains without code changes

## 7. Risk Mitigation

### Risks
1. **Breaking existing functionality**
   - Mitigation: Comprehensive test suite before refactoring
   - Keep old code available during transition

2. **Performance degradation**
   - Mitigation: Profile before/after
   - Optimize critical paths

3. **Complex configuration**
   - Mitigation: Provide templates and examples
   - Create configuration validator

### Rollback Plan
- Use feature flags to enable/disable new code
- Keep parallel implementations during transition
- Gradual rollout with monitoring

## 8. Success Metrics

- **Code Metrics:**
  - Zero domain-specific imports in core modules
  - 100% test coverage maintained
  - < 5% performance impact

- **Functionality Metrics:**
  - New domain operational in < 1 hour
  - No Python code required for new domains
  - All existing features working

- **Developer Experience:**
  - Clear documentation
  - Example templates for common domains
  - Configuration validation tools

## Appendix A: File Change Summary

### Files to Modify:
1. `server/retrievers/implementations/intent/domain_strategies/base.py` - Extend interface
2. `server/retrievers/implementations/intent/domain_strategies/customer_order.py` - Add new methods
3. `server/retrievers/implementations/intent/domain/extraction/value_extractor.py` - Remove hardcoded logic
4. `server/retrievers/implementations/intent/domain/response/formatters.py` - Make configurable
5. `server/retrievers/implementations/intent/domain/config.py` - Add semantic metadata
6. `server/retrievers/implementations/intent/domain/extraction/extractor.py` - Wire strategy

### New Files:
1. `server/retrievers/implementations/intent/domain_strategies/generic.py` - Generic strategy
2. `config/sql_intent_templates/examples/healthcare/` - Example new domain
3. `docs/intent_retriever_configuration_guide.md` - Configuration documentation

### Configuration Files to Update:
1. `config/sql_intent_templates/examples/customer-orders/customer_order_domain.yaml` - Add semantic metadata

## Appendix B: Example Healthcare Domain Configuration

```yaml
domain_name: Healthcare
domain_type: generic  # Uses GenericDomainStrategy
description: Patient health record management

semantic_types:
  patient_identifier:
    description: "Unique patient ID"
    patterns: ["patient", "pid", "mrn"]
  diagnosis_code:
    description: "ICD-10 diagnosis code"
    patterns: ["icd", "diagnosis", "condition"]
  medication_name:
    description: "Medication or drug name"
    patterns: ["medication", "drug", "prescription"]

entities:
  patient:
    name: patient
    entity_type: primary
    table_name: patients

  appointment:
    name: appointment
    entity_type: transaction
    table_name: appointments

fields:
  patient:
    patient_id:
      name: patient_id
      data_type: string
      semantic_type: patient_identifier
      summary_priority: 10
      extraction_pattern: '[PM]\d{6,8}'

    name:
      name: name
      data_type: string
      semantic_type: person_name
      summary_priority: 9

    date_of_birth:
      name: date_of_birth
      data_type: date
      semantic_type: birth_date
      summary_priority: 7

  appointment:
    appointment_id:
      name: appointment_id
      data_type: integer
      semantic_type: identifier
      summary_priority: 10

    diagnosis:
      name: diagnosis
      data_type: string
      semantic_type: diagnosis_code
      extraction_pattern: '[A-Z]\d{2}\.?\d*'
      summary_priority: 8
```

This configuration alone would enable the system to handle healthcare queries without any Python code changes.

---

## Quick Resume Guide

### Phase 2: ✅ COMPLETED (Dec 21, 2024)
- ResponseFormatter is now configuration-driven
- Domain strategy integration complete
- All tests passing (9/9)
- Backward compatibility maintained

### To Continue Phase 3:

1. **Objective:** Enhance domain configuration schema with semantic types and priorities
2. **Start with:** `server/retrievers/implementations/intent/domain/config.py`
3. **Target:** Add semantic metadata support to DomainConfig and FieldConfig classes
4. **Implementation:**
   - Add `semantic_type` and `summary_priority` fields to FieldConfig
   - Add `domain_type` and `semantic_types` to DomainConfig
   - Update domain YAML files with semantic metadata
5. **Example:** Update `config/sql_intent_templates/examples/customer-orders/customer_order_domain.yaml`
6. **Test:** Verify semantic types work with existing ResponseFormatter

### Key Files for Phase 3:
- `server/retrievers/implementations/intent/domain/config.py` (main target)
- `config/sql_intent_templates/examples/customer-orders/customer_order_domain.yaml` (example)
- `server/tests/intent/test_domain_extraction_refactor.py` (add semantic type tests)

### Validation:
- Domain configuration supports semantic metadata
- Customer order domain uses semantic types
- ResponseFormatter leverages semantic types for prioritization