#!/usr/bin/env python3
"""
Template Builder SDK for RAG Framework
======================================

This SDK provides a fluent API for building query templates
in any business domain.
"""

from typing import Dict, List, Any, Optional, Union, Callable
from dataclasses import dataclass, field
from enum import Enum
import yaml
import re
from domain_configuration import DomainConfiguration, DataType


class TemplateType(Enum):
    """Standard template types"""
    FIND_LIST = "find_list"
    CALCULATE_SUMMARY = "calculate_summary"
    RANK_LIST = "rank_list"
    SEARCH_FIND = "search_find"
    FILTER_BY = "filter_by"
    COMPARE_DATA = "compare_data"
    TREND_ANALYSIS = "trend_analysis"
    AGGREGATE_REPORT = "aggregate_report"


class ParameterType(Enum):
    """Extended parameter types with validation"""
    STRING = "string"
    INTEGER = "integer"
    DECIMAL = "decimal"
    DATE = "date"
    DATETIME = "datetime"
    BOOLEAN = "boolean"
    ENUM = "enum"
    ARRAY = "array"
    RANGE = "range"
    DYNAMIC = "dynamic"


@dataclass
class TemplateParameter:
    """Enhanced parameter definition"""
    name: str
    param_type: ParameterType
    description: str
    required: bool = True
    default: Any = None
    aliases: List[str] = field(default_factory=list)
    validation_rules: List[Dict[str, Any]] = field(default_factory=list)
    example: Any = None
    allowed_values: Optional[List[Any]] = None
    min_value: Optional[Union[int, float]] = None
    max_value: Optional[Union[int, float]] = None
    pattern: Optional[str] = None
    depends_on: Optional[str] = None
    transform_function: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for YAML export"""
        result = {
            "name": self.name,
            "type": self.param_type.value,
            "description": self.description,
            "required": self.required
        }
        
        if self.default is not None:
            result["default"] = self.default
        if self.aliases:
            result["aliases"] = self.aliases
        if self.validation_rules:
            result["validation_rules"] = self.validation_rules
        if self.example is not None:
            result["example"] = self.example
        if self.allowed_values:
            result["allowed_values"] = self.allowed_values
        if self.min_value is not None:
            result["min_value"] = self.min_value
        if self.max_value is not None:
            result["max_value"] = self.max_value
        if self.pattern:
            result["pattern"] = self.pattern
        if self.depends_on:
            result["depends_on"] = self.depends_on
        if self.transform_function:
            result["transform_function"] = self.transform_function
            
        return result


@dataclass
class SemanticTags:
    """Semantic tags for better intent matching"""
    action: str
    primary_entity: str
    secondary_entity: Optional[str] = None
    qualifiers: List[str] = field(default_factory=list)
    intent: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "action": self.action,
            "primary_entity": self.primary_entity,
            "intent": self.intent or f"{self.action}_{self.primary_entity}"
        }
        if self.secondary_entity:
            result["secondary_entity"] = self.secondary_entity
        if self.qualifiers:
            result["qualifiers"] = self.qualifiers
        return result


class QueryTemplateBuilder:
    """Fluent API for building query templates"""
    
    def __init__(self, template_id: str, domain: Optional[DomainConfiguration] = None):
        self.template_id = template_id
        self.domain = domain
        self.version = "1.0.0"
        self.description = ""
        self.template_type = TemplateType.FIND_LIST
        self.nl_examples: List[str] = []
        self.negative_examples: List[str] = []
        self.parameters: List[TemplateParameter] = []
        self.semantic_tags: Optional[SemanticTags] = None
        self.sql_template = ""
        self.result_format = "table"
        self.tags: List[str] = []
        self.approved = False
        self.metadata: Dict[str, Any] = {}
        self.pre_processors: List[str] = []
        self.post_processors: List[str] = []
        self.custom_validators: List[Callable] = []
        
    def with_version(self, version: str) -> 'QueryTemplateBuilder':
        """Set template version"""
        self.version = version
        return self
    
    def with_description(self, description: str) -> 'QueryTemplateBuilder':
        """Set template description"""
        self.description = description
        return self
    
    def of_type(self, template_type: TemplateType) -> 'QueryTemplateBuilder':
        """Set template type"""
        self.template_type = template_type
        return self
    
    def with_examples(self, *examples: str) -> 'QueryTemplateBuilder':
        """Add natural language examples"""
        self.nl_examples.extend(examples)
        return self
    
    def with_negative_examples(self, *examples: str) -> 'QueryTemplateBuilder':
        """Add negative examples (what this template doesn't handle)"""
        self.negative_examples.extend(examples)
        return self
    
    def with_parameter(self, 
                      name: str,
                      param_type: Union[ParameterType, str],
                      description: str,
                      required: bool = True,
                      default: Any = None,
                      **kwargs) -> 'QueryTemplateBuilder':
        """Add a parameter to the template"""
        if isinstance(param_type, str):
            param_type = ParameterType(param_type)
            
        param = TemplateParameter(
            name=name,
            param_type=param_type,
            description=description,
            required=required,
            default=default,
            aliases=kwargs.get('aliases', []),
            validation_rules=kwargs.get('validation_rules', []),
            example=kwargs.get('example'),
            allowed_values=kwargs.get('allowed_values'),
            min_value=kwargs.get('min_value'),
            max_value=kwargs.get('max_value'),
            pattern=kwargs.get('pattern'),
            depends_on=kwargs.get('depends_on'),
            transform_function=kwargs.get('transform_function')
        )
        self.parameters.append(param)
        return self
    
    def with_semantic_tags(self,
                          action: str,
                          primary_entity: str,
                          secondary_entity: Optional[str] = None,
                          qualifiers: Optional[List[str]] = None,
                          intent: Optional[str] = None) -> 'QueryTemplateBuilder':
        """Add semantic tags for better matching"""
        self.semantic_tags = SemanticTags(
            action=action,
            primary_entity=primary_entity,
            secondary_entity=secondary_entity,
            qualifiers=qualifiers or [],
            intent=intent or f"{action}_{primary_entity}"
        )
        return self
    
    def with_sql(self, sql_template: str) -> 'QueryTemplateBuilder':
        """Set SQL template"""
        self.sql_template = sql_template.strip()
        return self
    
    def with_sql_builder(self, builder_func: Callable) -> 'QueryTemplateBuilder':
        """Use a SQL builder function"""
        self.sql_template = builder_func(self.domain, self.parameters)
        return self
    
    def with_result_format(self, format: str) -> 'QueryTemplateBuilder':
        """Set result format (table, summary, chart, etc.)"""
        self.result_format = format
        return self
    
    def with_tags(self, *tags: str) -> 'QueryTemplateBuilder':
        """Add searchable tags"""
        self.tags.extend(tags)
        return self
    
    def with_metadata(self, key: str, value: Any) -> 'QueryTemplateBuilder':
        """Add custom metadata"""
        self.metadata[key] = value
        return self
    
    def with_pre_processor(self, processor: str) -> 'QueryTemplateBuilder':
        """Add pre-processing step"""
        self.pre_processors.append(processor)
        return self
    
    def with_post_processor(self, processor: str) -> 'QueryTemplateBuilder':
        """Add post-processing step"""
        self.post_processors.append(processor)
        return self
    
    def with_validator(self, validator: Callable) -> 'QueryTemplateBuilder':
        """Add custom validation function"""
        self.custom_validators.append(validator)
        return self
    
    def approve(self) -> 'QueryTemplateBuilder':
        """Mark template as approved"""
        self.approved = True
        return self
    
    def validate(self) -> List[str]:
        """Validate the template configuration"""
        errors = []
        
        if not self.template_id:
            errors.append("Template ID is required")
        if not self.description:
            errors.append("Description is required")
        if not self.nl_examples:
            errors.append("At least one natural language example is required")
        if not self.sql_template:
            errors.append("SQL template is required")
        if not self.tags:
            errors.append("At least one tag is required")
            
        # Validate SQL template has all parameter placeholders
        sql_params = re.findall(r'%\((\w+)\)s', self.sql_template)
        param_names = {p.name for p in self.parameters}
        
        for sql_param in sql_params:
            if sql_param not in param_names:
                errors.append(f"SQL parameter '{sql_param}' not defined in parameters")
                
        # Validate parameter dependencies
        for param in self.parameters:
            if param.depends_on and param.depends_on not in param_names:
                errors.append(f"Parameter '{param.name}' depends on unknown parameter '{param.depends_on}'")
                
        # Run custom validators
        for validator in self.custom_validators:
            try:
                validator_errors = validator(self)
                if validator_errors:
                    errors.extend(validator_errors)
            except Exception as e:
                errors.append(f"Validator error: {str(e)}")
                
        return errors
    
    def build(self) -> Dict[str, Any]:
        """Build the final template dictionary"""
        errors = self.validate()
        if errors:
            raise ValueError(f"Template validation failed: {', '.join(errors)}")
            
        template = {
            "id": self.template_id,
            "version": self.version,
            "description": self.description,
            "nl_examples": self.nl_examples,
            "parameters": [p.to_dict() for p in self.parameters],
            "sql_template": self.sql_template,
            "result_format": self.result_format,
            "tags": self.tags,
            "approved": self.approved
        }
        
        if self.negative_examples:
            template["negative_examples"] = self.negative_examples
        
        if self.semantic_tags:
            template["semantic_tags"] = self.semantic_tags.to_dict()
            
        if self.metadata:
            template["metadata"] = self.metadata
            
        if self.pre_processors:
            template["pre_processors"] = self.pre_processors
            
        if self.post_processors:
            template["post_processors"] = self.post_processors
            
        return template


class TemplateLibrary:
    """Manages a collection of query templates"""
    
    def __init__(self, domain: Optional[DomainConfiguration] = None):
        self.domain = domain
        self.templates: Dict[str, Dict[str, Any]] = {}
        self.categories: Dict[str, List[str]] = {}
        
    def add_template(self, template: Union[Dict[str, Any], QueryTemplateBuilder]) -> None:
        """Add a template to the library"""
        if isinstance(template, QueryTemplateBuilder):
            template_dict = template.build()
        else:
            template_dict = template
            
        template_id = template_dict["id"]
        self.templates[template_id] = template_dict
        
        # Categorize by type
        if "semantic_tags" in template_dict:
            action = template_dict["semantic_tags"].get("action", "other")
            if action not in self.categories:
                self.categories[action] = []
            self.categories[action].append(template_id)
    
    def get_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        """Get a template by ID"""
        return self.templates.get(template_id)
    
    def find_templates(self, 
                      category: Optional[str] = None,
                      entity: Optional[str] = None,
                      tags: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Find templates matching criteria"""
        results = []
        
        for template in self.templates.values():
            # Filter by category
            if category:
                semantic_tags = template.get("semantic_tags", {})
                if semantic_tags.get("action") != category:
                    continue
                    
            # Filter by entity
            if entity:
                semantic_tags = template.get("semantic_tags", {})
                if semantic_tags.get("primary_entity") != entity:
                    continue
                    
            # Filter by tags
            if tags:
                template_tags = set(template.get("tags", []))
                if not any(tag in template_tags for tag in tags):
                    continue
                    
            results.append(template)
            
        return results
    
    def export_to_yaml(self, file_path: str) -> None:
        """Export all templates to YAML"""
        data = {
            "templates": list(self.templates.values())
        }
        
        with open(file_path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    
    def import_from_yaml(self, file_path: str) -> None:
        """Import templates from YAML"""
        with open(file_path, 'r') as f:
            data = yaml.safe_load(f)
            
        for template in data.get("templates", []):
            self.add_template(template)
    
    def generate_documentation(self) -> str:
        """Generate markdown documentation for all templates"""
        doc_lines = ["# Query Template Library\n"]
        
        # Group by category
        for category, template_ids in sorted(self.categories.items()):
            doc_lines.append(f"\n## {category.replace('_', ' ').title()}\n")
            
            for template_id in sorted(template_ids):
                template = self.templates[template_id]
                doc_lines.append(f"### {template['id']}\n")
                doc_lines.append(f"**Description:** {template['description']}\n")
                doc_lines.append(f"**Version:** {template['version']}\n")
                
                if template.get('nl_examples'):
                    doc_lines.append("\n**Examples:**")
                    for example in template['nl_examples'][:3]:
                        doc_lines.append(f"- {example}")
                
                if template.get('parameters'):
                    doc_lines.append("\n**Parameters:**")
                    for param in template['parameters']:
                        required = "required" if param['required'] else "optional"
                        doc_lines.append(f"- `{param['name']}` ({param['type']}, {required}): {param['description']}")
                
                doc_lines.append("")
        
        return '\n'.join(doc_lines)


# Example: Building templates with the SDK
def example_template_creation():
    """Example of creating templates using the SDK"""
    
    # Create a template using the builder
    template = (QueryTemplateBuilder("find_recent_activities")
        .with_version("1.0.0")
        .with_description("Find recent activities for any entity")
        .of_type(TemplateType.FIND_LIST)
        .with_examples(
            "Show me recent customer activities",
            "What happened in the last 7 days?",
            "Recent transactions"
        )
        .with_parameter(
            name="entity_type",
            param_type=ParameterType.STRING,
            description="Type of entity to query",
            required=True,
            allowed_values=["customer", "order", "product"]
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
            primary_entity="activity",
            qualifiers=["recent", "time-bound"]
        )
        .with_sql("""
            SELECT * FROM activities
            WHERE entity_type = %(entity_type)s
            AND created_at >= NOW() - INTERVAL '%(days_back)s days'
            ORDER BY created_at DESC
        """)
        .with_tags("activity", "recent", "history")
        .approve()
        .build()
    )
    
    return template


if __name__ == "__main__":
    # Example usage
    library = TemplateLibrary()
    
    # Add example template
    example_template = example_template_creation()
    library.add_template(example_template)
    
    # Export to YAML
    library.export_to_yaml("example_templates.yaml")
    
    # Generate documentation
    docs = library.generate_documentation()
    print(docs)