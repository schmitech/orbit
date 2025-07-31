#!/usr/bin/env python3
"""
Template Generator using Template Library SDK
============================================

This module provides utilities to generate query templates for any domain
using the Template Library SDK.
"""

from typing import Dict, List, Optional
from domain_configuration import DomainConfiguration, EntityType, RelationType
from template_library import TemplateLibrary, QueryTemplateBuilder, TemplateType, ParameterType


class DomainTemplateGenerator:
    """Generates standard templates for a domain"""
    
    def __init__(self, domain: DomainConfiguration):
        self.domain = domain
        self.library = TemplateLibrary(domain)
    
    def generate_standard_templates(self) -> TemplateLibrary:
        """Generate standard templates for the domain"""
        
        # Generate templates for each primary entity
        for entity_name, entity in self.domain.entities.items():
            if entity.entity_type == EntityType.PRIMARY:
                self._generate_entity_templates(entity_name, entity)
            elif entity.entity_type == EntityType.TRANSACTION:
                self._generate_transaction_templates(entity_name, entity)
        
        # Generate relationship-based templates
        self._generate_relationship_templates()
        
        # Generate analytics templates
        self._generate_analytics_templates()
        
        return self.library
    
    def _generate_entity_templates(self, entity_name: str, entity):
        """Generate standard templates for a primary entity"""
        
        # 1. Find by ID template
        if entity.primary_key:
            template = (QueryTemplateBuilder(f"find_{entity_name}_by_id", self.domain)
                .with_description(f"Find {entity.description} by ID")
                .of_type(TemplateType.SEARCH_FIND)
                .with_examples(
                    f"Show me {entity_name} {entity.primary_key} 123",
                    f"Get {entity_name} #{entity.primary_key} 456",
                    f"Find {entity_name} with {entity.primary_key} 789"
                )
                .with_parameter(
                    name=f"{entity_name}_{entity.primary_key}",
                    param_type=ParameterType.INTEGER,
                    description=f"{entity.description} ID",
                    required=True,
                    example=123
                )
                .with_semantic_tags(
                    action="search_find",
                    primary_entity=entity_name,
                    intent=f"find_{entity_name}"
                )
                .with_sql(f"""
                    SELECT * FROM {entity.table_name}
                    WHERE {entity.primary_key} = %({entity_name}_{entity.primary_key})s
                """)
                .with_tags(entity_name, "find", "id", "lookup")
                .approve()
                .build()
            )
            self.library.add_template(template)
        
        # 2. Search by name/display field template
        if entity.display_name_field and entity.display_name_field in self.domain.fields[entity_name]:
            field = self.domain.fields[entity_name][entity.display_name_field]
            
            template = (QueryTemplateBuilder(f"search_{entity_name}_by_name", self.domain)
                .with_description(f"Search {entity.description} by name")
                .of_type(TemplateType.FIND_LIST)
                .with_examples(
                    f"Find {entity_name} named John",
                    f"Search for {entity_name} with name like Mary",
                    f"Show me all {entity_name}s matching Smith"
                )
                .with_parameter(
                    name=f"{entity_name}_name",
                    param_type=ParameterType.STRING,
                    description=f"{entity.description} name pattern",
                    required=True,
                    example="John%",
                    aliases=field.aliases
                )
                .with_semantic_tags(
                    action="find_list",
                    primary_entity=entity_name,
                    qualifiers=["name", "search"]
                )
                .with_sql(f"""
                    SELECT * FROM {entity.table_name}
                    WHERE LOWER({field.db_column}) LIKE LOWER(%({entity_name}_name)s)
                    ORDER BY {field.db_column}
                    LIMIT 50
                """)
                .with_tags(entity_name, "search", "name", "find")
                .approve()
                .build()
            )
            self.library.add_template(template)
        
        # 3. List recent entities
        if entity.default_sort_field:
            template = (QueryTemplateBuilder(f"list_recent_{entity_name}s", self.domain)
                .with_description(f"List recent {entity.description}")
                .of_type(TemplateType.FIND_LIST)
                .with_examples(
                    f"Show me recent {entity_name}s",
                    f"List new {entity_name}s from last week",
                    f"Recent {entity_name}s"
                )
                .with_parameter(
                    name="days_back",
                    param_type=ParameterType.INTEGER,
                    description="Number of days to look back",
                    required=False,
                    default=7,
                    min_value=1,
                    max_value=365
                )
                .with_semantic_tags(
                    action="find_list",
                    primary_entity=entity_name,
                    qualifiers=["recent", "new"]
                )
                .with_sql(f"""
                    SELECT * FROM {entity.table_name}
                    WHERE {entity.default_sort_field} >= CURRENT_DATE - INTERVAL '%(days_back)s days'
                    ORDER BY {entity.default_sort_field} {entity.default_sort_order}
                    LIMIT 100
                """)
                .with_tags(entity_name, "recent", "list", "new")
                .approve()
                .build()
            )
            self.library.add_template(template)
    
    def _generate_transaction_templates(self, entity_name: str, entity):
        """Generate templates for transaction entities"""
        
        # 1. Filter by common filters
        for filter_field in entity.common_filters:
            if filter_field not in self.domain.fields[entity_name]:
                continue
            
            field = self.domain.fields[entity_name][filter_field]
            
            # Generate appropriate template based on field type
            if field.enum_values:
                # Enum filter template
                template = (QueryTemplateBuilder(f"filter_{entity_name}_by_{filter_field}", self.domain)
                    .with_description(f"Filter {entity.description} by {field.description}")
                    .of_type(TemplateType.FILTER_BY)
                    .with_examples(
                        f"Show me {entity_name}s with {filter_field} {field.enum_values[0]}",
                        f"Find all {field.enum_values[1]} {entity_name}s",
                        f"List {entity_name}s where {filter_field} is {field.enum_values[0]}"
                    )
                    .with_parameter(
                        name=filter_field,
                        param_type=ParameterType.ENUM,
                        description=field.description,
                        required=True,
                        allowed_values=field.enum_values,
                        example=field.enum_values[0]
                    )
                    .with_semantic_tags(
                        action="filter_by",
                        primary_entity=entity_name,
                        qualifiers=[filter_field]
                    )
                    .with_sql(f"""
                        SELECT * FROM {entity.table_name}
                        WHERE {field.db_column} = %({filter_field})s
                        ORDER BY {entity.default_sort_field} {entity.default_sort_order}
                        LIMIT 100
                    """)
                    .with_tags(entity_name, "filter", filter_field)
                    .approve()
                    .build()
                )
                self.library.add_template(template)
            
            elif field.data_type.value in ["decimal", "integer"]:
                # Range filter template
                template = (QueryTemplateBuilder(f"filter_{entity_name}_by_{filter_field}_range", self.domain)
                    .with_description(f"Filter {entity.description} by {field.description} range")
                    .of_type(TemplateType.FILTER_BY)
                    .with_examples(
                        f"Show me {entity_name}s with {filter_field} between 100 and 500",
                        f"Find {entity_name}s over ${field.display_format == 'currency' and '1000' or '50'}",
                        f"List {entity_name}s under ${field.display_format == 'currency' and '100' or '10'}"
                    )
                    .with_parameter(
                        name=f"min_{filter_field}",
                        param_type=ParameterType.DECIMAL if field.data_type.value == "decimal" else ParameterType.INTEGER,
                        description=f"Minimum {field.description}",
                        required=False
                    )
                    .with_parameter(
                        name=f"max_{filter_field}",
                        param_type=ParameterType.DECIMAL if field.data_type.value == "decimal" else ParameterType.INTEGER,
                        description=f"Maximum {field.description}",
                        required=False
                    )
                    .with_semantic_tags(
                        action="filter_by",
                        primary_entity=entity_name,
                        qualifiers=[filter_field, "range"]
                    )
                    .with_sql(f"""
                        SELECT * FROM {entity.table_name}
                        WHERE 1=1
                        {{% if min_{filter_field} %}}
                          AND {field.db_column} >= %(min_{filter_field})s
                        {{% endif %}}
                        {{% if max_{filter_field} %}}
                          AND {field.db_column} <= %(max_{filter_field})s
                        {{% endif %}}
                        ORDER BY {entity.default_sort_field} {entity.default_sort_order}
                        LIMIT 100
                    """)
                    .with_tags(entity_name, "filter", filter_field, "range")
                    .approve()
                    .build()
                )
                self.library.add_template(template)
    
    def _generate_relationship_templates(self):
        """Generate templates based on entity relationships"""
        
        for relationship in self.domain.relationships:
            if relationship.relation_type == RelationType.ONE_TO_MANY:
                # Generate "find children by parent" template
                parent_entity = self.domain.entities[relationship.from_entity]
                child_entity = self.domain.entities[relationship.to_entity]
                
                template = (QueryTemplateBuilder(
                    f"find_{relationship.to_entity}_by_{relationship.from_entity}", 
                    self.domain
                )
                    .with_description(
                        f"Find {child_entity.description} for a specific {parent_entity.description}"
                    )
                    .of_type(TemplateType.FIND_LIST)
                    .with_examples(
                        f"Show me {relationship.to_entity}s for {relationship.from_entity} 123",
                        f"What {relationship.to_entity}s does {relationship.from_entity} 456 have?",
                        f"List all {relationship.to_entity}s from {relationship.from_entity} 789"
                    )
                    .with_parameter(
                        name=f"{relationship.from_entity}_id",
                        param_type=ParameterType.INTEGER,
                        description=f"{parent_entity.description} ID",
                        required=True
                    )
                    .with_semantic_tags(
                        action="find_list",
                        primary_entity=relationship.to_entity,
                        secondary_entity=relationship.from_entity,
                        qualifiers=["by_parent"]
                    )
                    .with_sql(f"""
                        SELECT c.* 
                        FROM {child_entity.table_name} c
                        WHERE c.{relationship.to_field} = %({relationship.from_entity}_id)s
                        ORDER BY c.{child_entity.default_sort_field} {child_entity.default_sort_order}
                        LIMIT 100
                    """)
                    .with_tags(
                        relationship.to_entity, 
                        relationship.from_entity, 
                        "relationship",
                        "find"
                    )
                    .approve()
                    .build()
                )
                self.library.add_template(template)
    
    def _generate_analytics_templates(self):
        """Generate analytics and aggregation templates"""
        
        # For each transaction entity, generate common analytics
        for entity_name, entity in self.domain.entities.items():
            if entity.entity_type != EntityType.TRANSACTION:
                continue
            
            # Find numeric fields for aggregation
            numeric_fields = []
            for field_name, field in self.domain.fields[entity_name].items():
                if field.data_type.value in ["decimal", "integer"] and field_name != entity.primary_key:
                    numeric_fields.append((field_name, field))
            
            if not numeric_fields:
                continue
            
            # Generate summary template for main numeric field
            main_field_name, main_field = numeric_fields[0]
            
            # Find relationships to group by
            relationships = self.domain.get_entity_relationships(entity_name)
            for rel in relationships:
                if rel.to_entity == entity_name:
                    # This entity is the child, can group by parent
                    parent_entity = self.domain.entities[rel.from_entity]
                    
                    template = (QueryTemplateBuilder(
                        f"calculate_{entity_name}_{main_field_name}_by_{rel.from_entity}",
                        self.domain
                    )
                        .with_description(
                            f"Calculate {main_field.description} summary for {parent_entity.description}"
                        )
                        .of_type(TemplateType.CALCULATE_SUMMARY)
                        .with_examples(
                            f"What's the total {main_field_name} for {rel.from_entity} 123?",
                            f"Calculate {main_field_name} sum for {rel.from_entity} 456",
                            f"Show me {rel.from_entity} 789's total {main_field_name}"
                        )
                        .with_parameter(
                            name=f"{rel.from_entity}_id",
                            param_type=ParameterType.INTEGER,
                            description=f"{parent_entity.description} ID",
                            required=True
                        )
                        .with_parameter(
                            name="days_back",
                            param_type=ParameterType.INTEGER,
                            description="Number of days to look back",
                            required=False,
                            default=365
                        )
                        .with_semantic_tags(
                            action="calculate_summary",
                            primary_entity=rel.from_entity,
                            secondary_entity=entity_name,
                            qualifiers=["sum", "total", main_field_name]
                        )
                        .with_sql(f"""
                            SELECT 
                                COUNT(*) as {entity_name}_count,
                                SUM({main_field.db_column}) as total_{main_field_name},
                                AVG({main_field.db_column}) as avg_{main_field_name},
                                MAX({main_field.db_column}) as max_{main_field_name},
                                MIN({main_field.db_column}) as min_{main_field_name}
                            FROM {entity.table_name}
                            WHERE {rel.to_field} = %({rel.from_entity}_id)s
                              AND {entity.default_sort_field} >= CURRENT_DATE - INTERVAL '%(days_back)s days'
                        """)
                        .with_result_format("summary")
                        .with_tags(
                            entity_name,
                            rel.from_entity,
                            "analytics",
                            "summary",
                            main_field_name
                        )
                        .approve()
                        .build()
                    )
                    self.library.add_template(template)
            
            # Top N template
            template = (QueryTemplateBuilder(f"rank_top_{entity_name}_by_{main_field_name}", self.domain)
                .with_description(f"Find top {entity.description} by {main_field.description}")
                .of_type(TemplateType.RANK_LIST)
                .with_examples(
                    f"Show me top 10 {entity_name}s by {main_field_name}",
                    f"What are the highest {main_field_name} {entity_name}s?",
                    f"Rank {entity_name}s by {main_field_name}"
                )
                .with_parameter(
                    name="limit",
                    param_type=ParameterType.INTEGER,
                    description="Number of results to return",
                    required=False,
                    default=10,
                    min_value=1,
                    max_value=100
                )
                .with_semantic_tags(
                    action="rank_list",
                    primary_entity=entity_name,
                    qualifiers=["top", "highest", main_field_name]
                )
                .with_sql(f"""
                    SELECT * FROM {entity.table_name}
                    ORDER BY {main_field.db_column} DESC
                    LIMIT %(limit)s
                """)
                .with_tags(entity_name, "top", "rank", main_field_name)
                .approve()
                .build()
            )
            self.library.add_template(template)


def generate_templates_from_yaml(domain_yaml_path: str, output_yaml_path: str):
    """Generate templates from a domain configuration YAML file"""
    
    # Load domain configuration
    domain = DomainConfiguration("temp", "temp")
    domain.from_yaml(domain_yaml_path)
    
    # Generate templates
    generator = DomainTemplateGenerator(domain)
    library = generator.generate_standard_templates()
    
    # Export templates
    library.export_to_yaml(output_yaml_path)
    
    # Generate documentation
    docs = library.generate_documentation()
    doc_path = output_yaml_path.replace('.yaml', '_docs.md')
    with open(doc_path, 'w') as f:
        f.write(docs)
    
    print(f"✅ Generated {len(library.templates)} templates")
    print(f"📁 Templates saved to: {output_yaml_path}")
    print(f"📄 Documentation saved to: {doc_path}")


if __name__ == "__main__":
    # Example usage
    import sys
    
    if len(sys.argv) != 3:
        print("Usage: python template_generator.py <domain_config.yaml> <output_templates.yaml>")
        sys.exit(1)
    
    generate_templates_from_yaml(sys.argv[1], sys.argv[2])