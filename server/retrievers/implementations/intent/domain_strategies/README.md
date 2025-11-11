# Domain Strategies for Template Reranking

This module provides a pluggable architecture for domain-specific template reranking strategies.

## Architecture

The system is designed with separation of concerns:

1. **Generic Reranking Logic** (`template_reranker.py`):
   - Handles vocabulary-based boosting (entities, actions, synonyms)
   - Manages semantic tag matching
   - Performs text similarity calculations
   - Applies natural language example matching

2. **Domain-Specific Strategies** (`domain_strategies/`):
   - Contains domain-specific pattern matching
   - Implements specialized boosting rules
   - Handles domain-specific disambiguation (e.g., person name vs. city)

## Adding a New Domain

To add support for a new domain, create a new strategy class:

```python
# domain_strategies/healthcare.py
from typing import Dict, Any
from .base import DomainStrategy

class HealthcareStrategy(DomainStrategy):
    """Strategy for healthcare/medical domains"""
    
    def get_domain_names(self) -> list:
        """Return list of domain names this strategy handles"""
        return ['healthcare', 'medical', 'clinical']
    
    def calculate_domain_boost(self, template_info: Dict, query: str, domain_config: Dict) -> float:
        """Calculate healthcare-specific boost"""
        template = template_info['template']
        query_lower = query.lower()
        boost = 0.0
        
        template_id = template.get('id', '')
        
        # Boost patient-related queries
        if 'patient' in template_id and self._contains_patient_pattern(query_lower):
            boost += 0.3
        
        # Boost diagnosis queries
        if 'diagnosis' in template_id and self._contains_medical_terms(query_lower):
            boost += 0.4
        
        # Boost treatment queries
        if 'treatment' in template_id and self._contains_treatment_pattern(query_lower):
            boost += 0.3
        
        return boost
    
    def get_pattern_matchers(self) -> Dict[str, Any]:
        """Return healthcare-specific pattern matchers"""
        return {
            'patient': self._contains_patient_pattern,
            'medical_term': self._contains_medical_terms,
            'treatment': self._contains_treatment_pattern
        }
    
    def _contains_patient_pattern(self, text: str) -> bool:
        """Check if text contains patient-related terms"""
        patient_terms = ['patient', 'mrn', 'medical record', 'chart']
        return any(term in text for term in patient_terms)
    
    def _contains_medical_terms(self, text: str) -> bool:
        """Check if text contains medical terminology"""
        # This could connect to a medical terminology database
        medical_indicators = ['diagnosis', 'symptom', 'condition', 'disease']
        return any(term in text for term in medical_indicators)
    
    def _contains_treatment_pattern(self, text: str) -> bool:
        """Check if text contains treatment-related terms"""
        treatment_terms = ['treatment', 'therapy', 'medication', 'prescription']
        return any(term in text for term in treatment_terms)
```

Then register it in the registry:

```python
# domain_strategies/registry.py
# Example: If you need custom domain-specific logic beyond YAML configuration
from .healthcare import HealthcareStrategy

class DomainStrategyRegistry:
    _builtin_strategies = [
        # All domains now use GenericDomainStrategy with YAML config by default
        # Only add custom strategies here if you need logic that cannot be expressed in YAML
        HealthcareStrategy,  # Add custom strategy here if needed
    ]
```

## Domain Configuration

Domain strategies work in conjunction with domain configuration files. The configuration provides:

- **Vocabulary**: Entity synonyms, action verbs, common phrases
- **Fields**: Database schema and field metadata
- **Relationships**: Entity relationships for join operations

Example domain configuration structure:

```yaml
domain_name: Healthcare
description: Patient health records management
entities:
  patient:
    name: patient
    entity_type: primary
    table_name: patients
  diagnosis:
    name: diagnosis
    entity_type: record
    table_name: diagnoses
vocabulary:
  entity_synonyms:
    patient:
      - patient
      - person
      - individual
    diagnosis:
      - diagnosis
      - condition
      - disease
  action_verbs:
    find:
      - find
      - search
      - lookup
    diagnose:
      - diagnose
      - identify
      - determine
```

## Best Practices

1. **Keep domain logic isolated**: All domain-specific pattern matching should be in the strategy class
2. **Use configuration**: Leverage the domain configuration for vocabulary and field information
3. **Provide meaningful boosts**: Typical boost values range from 0.1 to 0.4
4. **Avoid over-boosting**: Multiple boosts should not push similarity above 1.0
5. **Test thoroughly**: Each domain strategy should have comprehensive tests

## Testing a Domain Strategy

```python
# Example test
def test_healthcare_strategy():
    config = {
        'domain_name': 'healthcare',
        'vocabulary': {
            'entity_synonyms': {
                'patient': ['patient', 'person'],
                'diagnosis': ['diagnosis', 'condition']
            }
        }
    }
    
    reranker = TemplateReranker(config)
    
    templates = [
        {
            'template': {'id': 'patient_by_name', 'description': 'Find patient by name'},
            'similarity': 0.5
        },
        {
            'template': {'id': 'diagnosis_by_code', 'description': 'Find diagnosis by code'},
            'similarity': 0.5
        }
    ]
    
    # Query about patient should boost patient template
    results = reranker.rerank_templates(templates, "find patient John Doe")
    assert results[0]['template']['id'] == 'patient_by_name'
    assert results[0]['similarity'] > 0.5
```