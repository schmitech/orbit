"""
Domain configuration helper for centralized access to domain metadata.
"""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class FieldConfig:
    """Configuration for a domain field"""
    name: str
    data_type: str
    display_name: Optional[str] = None
    display_format: Optional[str] = None
    searchable: bool = False
    filterable: bool = False
    sortable: bool = False
    aggregatable: bool = False
    description: Optional[str] = None
    validation_rules: Dict[str, Any] = field(default_factory=dict)
    # NEW: Semantic metadata for domain-agnostic extraction and prioritization
    semantic_type: Optional[str] = None
    summary_priority: Optional[int] = None
    extraction_pattern: Optional[str] = None
    extraction_hints: Optional[Dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, field_name: str, config: Dict[str, Any]) -> 'FieldConfig':
        """Create FieldConfig from dictionary"""
        return cls(
            name=field_name,
            data_type=config.get('data_type', 'string'),
            display_name=config.get('display_name'),
            display_format=config.get('display_format'),
            searchable=config.get('searchable', False),
            filterable=config.get('filterable', False),
            sortable=config.get('sortable', False),
            aggregatable=config.get('aggregatable', False),
            description=config.get('description'),
            validation_rules=config.get('validation_rules', {}),
            # NEW: Parse semantic metadata
            semantic_type=config.get('semantic_type'),
            summary_priority=config.get('summary_priority'),
            extraction_pattern=config.get('extraction_pattern'),
            extraction_hints=config.get('extraction_hints', {})
        )


@dataclass
class EntityConfig:
    """Configuration for a domain entity"""
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    fields: Dict[str, FieldConfig] = field(default_factory=dict)
    relationships: Dict[str, Dict] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, entity_name: str, config: Dict[str, Any], fields_config: Dict[str, Any]) -> 'EntityConfig':
        """Create EntityConfig from dictionary"""
        entity = cls(
            name=entity_name,
            display_name=config.get('display_name', entity_name),
            description=config.get('description')
        )

        # Add fields
        entity_fields = fields_config.get(entity_name, {})
        for field_name, field_data in entity_fields.items():
            entity.fields[field_name] = FieldConfig.from_dict(field_name, field_data)

        # Add relationships if present
        entity.relationships = config.get('relationships', {})

        return entity


class DomainConfig:
    """
    Centralized domain configuration helper.
    Provides unified access to domain metadata currently queried in multiple modules.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize domain configuration"""
        self.config = config or {}
        self.domain_name = self.config.get('domain_name', 'unknown')
        self.description = self.config.get('description', '')

        # NEW: Parse domain metadata for strategy selection
        self.domain_type = self.config.get('domain_type', 'generic')
        self.semantic_types = self.config.get('semantic_types', {})

        # Parse entities and fields
        self.entities: Dict[str, EntityConfig] = {}
        self._parse_entities()

        # Cache vocabulary
        self.vocabulary = self.config.get('vocabulary', {})
        self.entity_synonyms = self.vocabulary.get('entity_synonyms', {})
        self.field_synonyms = self.vocabulary.get('field_synonyms', {})

        # Cache metrics and aggregations
        self.metrics = self.config.get('metrics', {})
        self.aggregations = self.config.get('aggregations', {})

        # Cache business rules
        self.business_rules = self.config.get('business_rules', {})

    def _parse_entities(self):
        """Parse entity configurations"""
        entities = self.config.get('entities', {})
        fields = self.config.get('fields', {})

        for entity_name, entity_data in entities.items():
            self.entities[entity_name] = EntityConfig.from_dict(
                entity_name, entity_data, fields
            )

    def get_entity(self, entity_name: str) -> Optional[EntityConfig]:
        """Get entity configuration by name"""
        return self.entities.get(entity_name)

    def get_field(self, entity_name: str, field_name: str) -> Optional[FieldConfig]:
        """Get field configuration"""
        entity = self.get_entity(entity_name)
        if entity:
            return entity.fields.get(field_name)
        return None

    def get_searchable_fields(self, entity_name: Optional[str] = None) -> List[FieldConfig]:
        """Get all searchable fields, optionally filtered by entity"""
        searchable = []

        if entity_name:
            entity = self.get_entity(entity_name)
            if entity:
                searchable = [f for f in entity.fields.values() if f.searchable]
        else:
            for entity in self.entities.values():
                searchable.extend([f for f in entity.fields.values() if f.searchable])

        return searchable

    def get_filterable_fields(self, entity_name: Optional[str] = None) -> List[FieldConfig]:
        """Get all filterable fields, optionally filtered by entity"""
        filterable = []

        if entity_name:
            entity = self.get_entity(entity_name)
            if entity:
                filterable = [f for f in entity.fields.values() if f.filterable]
        else:
            for entity in self.entities.values():
                filterable.extend([f for f in entity.fields.values() if f.filterable])

        return filterable

    def get_entity_synonyms(self, entity_name: str) -> List[str]:
        """Get synonyms for an entity"""
        return self.entity_synonyms.get(entity_name, [])

    def get_field_synonyms(self, field_name: str) -> List[str]:
        """Get synonyms for a field"""
        return self.field_synonyms.get(field_name, [])

    def get_metric(self, metric_name: str) -> Optional[Dict[str, Any]]:
        """Get metric configuration"""
        return self.metrics.get(metric_name)

    def get_aggregation(self, aggregation_name: str) -> Optional[Dict[str, Any]]:
        """Get aggregation configuration"""
        return self.aggregations.get(aggregation_name)

    def get_business_rule(self, rule_name: str) -> Optional[Dict[str, Any]]:
        """Get business rule configuration"""
        return self.business_rules.get(rule_name)

    def find_entity_by_synonym(self, synonym: str) -> Optional[str]:
        """Find entity name by synonym"""
        synonym_lower = synonym.lower()

        # First check direct entity names
        for entity_name in self.entities.keys():
            if entity_name.lower() == synonym_lower:
                return entity_name

        # Then check synonyms
        for entity_name, synonyms in self.entity_synonyms.items():
            if synonym_lower in [s.lower() for s in synonyms]:
                return entity_name

        return None

    def find_field_by_synonym(self, entity_name: str, synonym: str) -> Optional[str]:
        """Find field name by synonym within an entity"""
        entity = self.get_entity(entity_name)
        if not entity:
            return None

        synonym_lower = synonym.lower()

        # Check direct field names
        for field_name in entity.fields.keys():
            if field_name.lower() == synonym_lower:
                return field_name

        # Check field synonyms
        for field_name, synonyms in self.field_synonyms.items():
            if field_name in entity.fields and synonym_lower in [s.lower() for s in synonyms]:
                return field_name

        return None

    def get_fields_by_semantic_type(self, semantic_type: str) -> List[FieldConfig]:
        """Get all fields with a specific semantic type"""
        fields = []
        for entity in self.entities.values():
            for field in entity.fields.values():
                if field.semantic_type == semantic_type:
                    fields.append(field)
        return fields

    def to_dict(self) -> Dict[str, Any]:
        """Convert back to dictionary format for compatibility"""
        return self.config