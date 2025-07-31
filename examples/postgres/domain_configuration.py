#!/usr/bin/env python3
"""
Domain Configuration System for RAG Framework
============================================

This module provides a domain-agnostic configuration system that allows
developers to define their business domain structure and rules.
"""

from typing import Dict, List, Any, Optional, Set, Callable
from dataclasses import dataclass, field
from enum import Enum
import yaml
import json


class DataType(Enum):
    """Standard data types supported across domains"""
    STRING = "string"
    INTEGER = "integer"
    DECIMAL = "decimal"
    DATE = "date"
    DATETIME = "datetime"
    BOOLEAN = "boolean"
    JSON = "json"
    ARRAY = "array"
    ENUM = "enum"


class EntityType(Enum):
    """Common entity types that can be extended"""
    PRIMARY = "primary"
    LOOKUP = "lookup"
    TRANSACTION = "transaction"
    REFERENCE = "reference"
    AGGREGATE = "aggregate"
    
    
class RelationType(Enum):
    """Standard relationship types between entities"""
    ONE_TO_ONE = "one_to_one"
    ONE_TO_MANY = "one_to_many"
    MANY_TO_MANY = "many_to_many"
    SELF_REFERENTIAL = "self_referential"


@dataclass
class DomainEntity:
    """Represents an entity in the business domain"""
    name: str
    entity_type: EntityType
    table_name: str
    description: str
    primary_key: str
    display_name_field: Optional[str] = None
    searchable_fields: List[str] = field(default_factory=list)
    common_filters: List[str] = field(default_factory=list)
    default_sort_field: Optional[str] = None
    default_sort_order: str = "DESC"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "entity_type": self.entity_type.value,
            "table_name": self.table_name,
            "description": self.description,
            "primary_key": self.primary_key,
            "display_name_field": self.display_name_field,
            "searchable_fields": self.searchable_fields,
            "common_filters": self.common_filters,
            "default_sort_field": self.default_sort_field,
            "default_sort_order": self.default_sort_order
        }


@dataclass
class DomainField:
    """Represents a field within an entity"""
    name: str
    data_type: DataType
    db_column: str
    description: str
    required: bool = False
    searchable: bool = False
    filterable: bool = True
    sortable: bool = True
    display_format: Optional[str] = None
    validation_rules: List[Dict[str, Any]] = field(default_factory=list)
    aliases: List[str] = field(default_factory=list)
    enum_values: Optional[List[str]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "data_type": self.data_type.value,
            "db_column": self.db_column,
            "description": self.description,
            "required": self.required,
            "searchable": self.searchable,
            "filterable": self.filterable,
            "sortable": self.sortable,
            "display_format": self.display_format,
            "validation_rules": self.validation_rules,
            "aliases": self.aliases,
            "enum_values": self.enum_values
        }


@dataclass
class DomainRelationship:
    """Represents a relationship between entities"""
    name: str
    from_entity: str
    to_entity: str
    relation_type: RelationType
    from_field: str
    to_field: str
    join_type: str = "INNER"
    description: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "from_entity": self.from_entity,
            "to_entity": self.to_entity,
            "relation_type": self.relation_type.value,
            "from_field": self.from_field,
            "to_field": self.to_field,
            "join_type": self.join_type,
            "description": self.description
        }


@dataclass
class QueryPattern:
    """Represents a common query pattern in the domain"""
    name: str
    description: str
    pattern_type: str  # find, aggregate, compare, trend, etc.
    required_entities: List[str]
    optional_entities: List[str] = field(default_factory=list)
    common_filters: List[str] = field(default_factory=list)
    common_aggregations: List[str] = field(default_factory=list)
    example_queries: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "pattern_type": self.pattern_type,
            "required_entities": self.required_entities,
            "optional_entities": self.optional_entities,
            "common_filters": self.common_filters,
            "common_aggregations": self.common_aggregations,
            "example_queries": self.example_queries
        }


@dataclass
class DomainVocabulary:
    """Domain-specific vocabulary and terminology"""
    entity_synonyms: Dict[str, List[str]] = field(default_factory=dict)
    action_verbs: Dict[str, List[str]] = field(default_factory=dict)
    time_expressions: Dict[str, str] = field(default_factory=dict)
    value_expressions: Dict[str, str] = field(default_factory=dict)
    common_phrases: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_synonyms": self.entity_synonyms,
            "action_verbs": self.action_verbs,
            "time_expressions": self.time_expressions,
            "value_expressions": self.value_expressions,
            "common_phrases": self.common_phrases
        }


class DomainConfiguration:
    """Main domain configuration class"""
    
    def __init__(self, domain_name: str, description: str):
        self.domain_name = domain_name
        self.description = description
        self.entities: Dict[str, DomainEntity] = {}
        self.fields: Dict[str, Dict[str, DomainField]] = {}
        self.relationships: List[DomainRelationship] = []
        self.query_patterns: List[QueryPattern] = []
        self.vocabulary = DomainVocabulary()
        self.custom_functions: Dict[str, Callable] = {}
        self.metadata: Dict[str, Any] = {}
    
    def add_entity(self, entity: DomainEntity) -> None:
        """Add an entity to the domain"""
        self.entities[entity.name] = entity
        self.fields[entity.name] = {}
    
    def add_field(self, entity_name: str, field: DomainField) -> None:
        """Add a field to an entity"""
        if entity_name not in self.entities:
            raise ValueError(f"Entity {entity_name} not found")
        self.fields[entity_name][field.name] = field
    
    def add_relationship(self, relationship: DomainRelationship) -> None:
        """Add a relationship between entities"""
        # Validate entities exist
        if relationship.from_entity not in self.entities:
            raise ValueError(f"Entity {relationship.from_entity} not found")
        if relationship.to_entity not in self.entities:
            raise ValueError(f"Entity {relationship.to_entity} not found")
        self.relationships.append(relationship)
    
    def add_query_pattern(self, pattern: QueryPattern) -> None:
        """Add a common query pattern"""
        self.query_patterns.append(pattern)
    
    def register_custom_function(self, name: str, func: Callable) -> None:
        """Register a custom function for domain-specific logic"""
        self.custom_functions[name] = func
    
    def get_entity_relationships(self, entity_name: str) -> List[DomainRelationship]:
        """Get all relationships for an entity"""
        return [
            r for r in self.relationships 
            if r.from_entity == entity_name or r.to_entity == entity_name
        ]
    
    def get_searchable_fields(self, entity_name: str) -> List[DomainField]:
        """Get all searchable fields for an entity"""
        if entity_name not in self.fields:
            return []
        return [
            f for f in self.fields[entity_name].values() 
            if f.searchable
        ]
    
    def generate_base_query(self, 
                           primary_entity: str,
                           include_entities: Optional[List[str]] = None,
                           fields: Optional[List[str]] = None) -> str:
        """Generate a base SQL query for the domain"""
        if primary_entity not in self.entities:
            raise ValueError(f"Entity {primary_entity} not found")
        
        primary = self.entities[primary_entity]
        query_parts = []
        
        # SELECT clause
        select_fields = []
        if fields:
            for field_spec in fields:
                if '.' in field_spec:
                    entity_name, field_name = field_spec.split('.')
                    if entity_name in self.entities and field_name in self.fields.get(entity_name, {}):
                        field = self.fields[entity_name][field_name]
                        alias = f"{entity_name}_{field_name}"
                        select_fields.append(f"{entity_name[0]}.{field.db_column} as {alias}")
                else:
                    if field_spec in self.fields.get(primary_entity, {}):
                        field = self.fields[primary_entity][field_spec]
                        select_fields.append(f"{primary_entity[0]}.{field.db_column} as {field_spec}")
        else:
            # Default: include all fields from primary entity
            for field_name, field in self.fields.get(primary_entity, {}).items():
                select_fields.append(f"{primary_entity[0]}.{field.db_column} as {field_name}")
        
        query_parts.append(f"SELECT {', '.join(select_fields)}")
        
        # FROM clause
        query_parts.append(f"FROM {primary.table_name} {primary_entity[0]}")
        
        # JOIN clauses
        if include_entities:
            for entity_name in include_entities:
                if entity_name == primary_entity:
                    continue
                
                # Find relationship
                for rel in self.relationships:
                    if (rel.from_entity == primary_entity and rel.to_entity == entity_name) or \
                       (rel.from_entity == entity_name and rel.to_entity == primary_entity):
                        
                        entity = self.entities[entity_name]
                        if rel.from_entity == primary_entity:
                            join_condition = f"{primary_entity[0]}.{rel.from_field} = {entity_name[0]}.{rel.to_field}"
                        else:
                            join_condition = f"{entity_name[0]}.{rel.from_field} = {primary_entity[0]}.{rel.to_field}"
                        
                        query_parts.append(
                            f"{rel.join_type} JOIN {entity.table_name} {entity_name[0]} ON {join_condition}"
                        )
                        break
        
        return '\n'.join(query_parts)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        return {
            "domain_name": self.domain_name,
            "description": self.description,
            "entities": {name: entity.to_dict() for name, entity in self.entities.items()},
            "fields": {
                entity: {name: field.to_dict() for name, field in fields.items()}
                for entity, fields in self.fields.items()
            },
            "relationships": [rel.to_dict() for rel in self.relationships],
            "query_patterns": [pattern.to_dict() for pattern in self.query_patterns],
            "vocabulary": self.vocabulary.to_dict(),
            "metadata": self.metadata
        }
    
    def to_yaml(self, file_path: str) -> None:
        """Export configuration to YAML file"""
        with open(file_path, 'w') as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False, sort_keys=False)
    
    def from_yaml(self, file_path: str) -> None:
        """Load configuration from YAML file"""
        with open(file_path, 'r') as f:
            data = yaml.safe_load(f)
        
        # Load entities
        for name, entity_data in data.get('entities', {}).items():
            entity = DomainEntity(
                name=name,
                entity_type=EntityType(entity_data['entity_type']),
                table_name=entity_data['table_name'],
                description=entity_data['description'],
                primary_key=entity_data['primary_key'],
                display_name_field=entity_data.get('display_name_field'),
                searchable_fields=entity_data.get('searchable_fields', []),
                common_filters=entity_data.get('common_filters', []),
                default_sort_field=entity_data.get('default_sort_field'),
                default_sort_order=entity_data.get('default_sort_order', 'DESC')
            )
            self.add_entity(entity)
        
        # Load fields
        for entity_name, fields in data.get('fields', {}).items():
            for field_name, field_data in fields.items():
                field = DomainField(
                    name=field_name,
                    data_type=DataType(field_data['data_type']),
                    db_column=field_data['db_column'],
                    description=field_data['description'],
                    required=field_data.get('required', False),
                    searchable=field_data.get('searchable', False),
                    filterable=field_data.get('filterable', True),
                    sortable=field_data.get('sortable', True),
                    display_format=field_data.get('display_format'),
                    validation_rules=field_data.get('validation_rules', []),
                    aliases=field_data.get('aliases', []),
                    enum_values=field_data.get('enum_values')
                )
                self.add_field(entity_name, field)
        
        # Load relationships
        for rel_data in data.get('relationships', []):
            relationship = DomainRelationship(
                name=rel_data['name'],
                from_entity=rel_data['from_entity'],
                to_entity=rel_data['to_entity'],
                relation_type=RelationType(rel_data['relation_type']),
                from_field=rel_data['from_field'],
                to_field=rel_data['to_field'],
                join_type=rel_data.get('join_type', 'INNER'),
                description=rel_data.get('description', '')
            )
            self.add_relationship(relationship)
        
        # Load vocabulary
        vocab_data = data.get('vocabulary', {})
        self.vocabulary = DomainVocabulary(
            entity_synonyms=vocab_data.get('entity_synonyms', {}),
            action_verbs=vocab_data.get('action_verbs', {}),
            time_expressions=vocab_data.get('time_expressions', {}),
            value_expressions=vocab_data.get('value_expressions', {}),
            common_phrases=vocab_data.get('common_phrases', {})
        )
        
        # Load metadata
        self.metadata = data.get('metadata', {})


# Example usage for e-commerce domain
def create_ecommerce_domain() -> DomainConfiguration:
    """Create a sample e-commerce domain configuration"""
    domain = DomainConfiguration(
        domain_name="E-Commerce",
        description="Standard e-commerce domain with customers, orders, and products"
    )
    
    # Add entities
    customer_entity = DomainEntity(
        name="customer",
        entity_type=EntityType.PRIMARY,
        table_name="customers",
        description="Customer information",
        primary_key="id",
        display_name_field="name",
        searchable_fields=["name", "email", "phone"],
        common_filters=["city", "country", "created_at"],
        default_sort_field="created_at"
    )
    domain.add_entity(customer_entity)
    
    order_entity = DomainEntity(
        name="order",
        entity_type=EntityType.TRANSACTION,
        table_name="orders",
        description="Order transactions",
        primary_key="id",
        display_name_field="id",
        searchable_fields=["id", "status"],
        common_filters=["status", "payment_method", "created_at", "total"],
        default_sort_field="created_at"
    )
    domain.add_entity(order_entity)
    
    # Add fields for customer
    domain.add_field("customer", DomainField(
        name="id",
        data_type=DataType.INTEGER,
        db_column="id",
        description="Customer ID",
        required=True,
        searchable=True
    ))
    
    domain.add_field("customer", DomainField(
        name="name",
        data_type=DataType.STRING,
        db_column="name",
        description="Customer name",
        required=True,
        searchable=True,
        aliases=["customer name", "client name", "buyer name"]
    ))
    
    domain.add_field("customer", DomainField(
        name="email",
        data_type=DataType.STRING,
        db_column="email",
        description="Customer email",
        required=True,
        searchable=True,
        display_format="email"
    ))
    
    # Add fields for order
    domain.add_field("order", DomainField(
        name="id",
        data_type=DataType.INTEGER,
        db_column="id",
        description="Order ID",
        required=True,
        searchable=True
    ))
    
    domain.add_field("order", DomainField(
        name="total",
        data_type=DataType.DECIMAL,
        db_column="total",
        description="Order total amount",
        required=True,
        filterable=True,
        display_format="currency"
    ))
    
    domain.add_field("order", DomainField(
        name="status",
        data_type=DataType.ENUM,
        db_column="status",
        description="Order status",
        required=True,
        searchable=True,
        enum_values=["pending", "processing", "shipped", "delivered", "cancelled"]
    ))
    
    # Add relationship
    domain.add_relationship(DomainRelationship(
        name="customer_orders",
        from_entity="customer",
        to_entity="order",
        relation_type=RelationType.ONE_TO_MANY,
        from_field="id",
        to_field="customer_id",
        description="Customer has many orders"
    ))
    
    # Add vocabulary
    domain.vocabulary.entity_synonyms = {
        "customer": ["client", "buyer", "user", "purchaser", "shopper"],
        "order": ["purchase", "transaction", "sale", "invoice"]
    }
    
    domain.vocabulary.action_verbs = {
        "find": ["show", "list", "get", "find", "display", "retrieve"],
        "calculate": ["sum", "total", "calculate", "compute", "aggregate"],
        "filter": ["filter", "only", "just", "where", "with"]
    }
    
    return domain


if __name__ == "__main__":
    # Example: Create and export a domain configuration
    ecommerce_domain = create_ecommerce_domain()
    ecommerce_domain.to_yaml("customer_orders.yaml")
    print("Domain configuration exported to customer_orders.yaml")