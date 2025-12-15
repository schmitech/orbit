"""Unit tests for the Jinja2-based TemplateProcessor."""

import os
import sys

import pytest
from unittest.mock import MagicMock

# Ensure the server directory is in the path for imports
_server_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)


class MockEntity:
    """Mock entity class for testing."""
    def __init__(self, name, entity_type, table_name, primary_key="id"):
        self.name = name
        self.entity_type = entity_type
        self.table_name = table_name
        self.primary_key = primary_key
        self.display_name = name.title()
        self.display_name_field = "name"
        self.relationships = {}
        self.searchable_fields = ["name"]
        self.common_filters = []
        self.default_sort_field = "name"
        self.default_sort_order = "asc"
        self.metadata = {}


class MockDomainConfig:
    """Mock domain config class for testing."""
    def __init__(self):
        self.domain_name = "hr_system"
        self.domain_type = "hr"

        self._primary = MockEntity("employee", "primary", "employees")
        self._primary.searchable_fields = ["name", "email"]
        self._primary.common_filters = ["status", "department_id"]
        self._primary.relationships = {"department": "departments.id"}
        self._primary.metadata = {"version": "1.0"}

        self._secondary = MockEntity("department", "secondary", "departments")

        self.entities = {
            "employee": self._primary,
            "department": self._secondary
        }

    def get_primary_entity(self):
        return self._primary

    def get_secondary_entities(self):
        return [self._secondary]


@pytest.fixture
def mock_domain_config():
    """Create a mock domain configuration for testing."""
    return MockDomainConfig()


@pytest.fixture
def template_processor(mock_domain_config):
    """Create a TemplateProcessor instance with mock config."""
    from retrievers.implementations.intent.template_processor import TemplateProcessor
    return TemplateProcessor(mock_domain_config)


class TestTemplateProcessorBasics:
    """Test basic template processor functionality."""

    def test_initialization(self, template_processor):
        """Test that the processor initializes correctly."""
        assert template_processor.env is not None
        assert template_processor.env_preserve is not None
        assert template_processor._base_context is not None

    def test_get_context(self, template_processor):
        """Test that get_context returns expected domain variables."""
        context = template_processor.get_context()

        assert context["domain_name"] == "hr_system"
        assert context["domain_type"] == "hr"
        assert context["primary_entity"] == "employee"
        assert context["primary_table"] == "employees"
        assert context["secondary_entity"] == "department"
        assert context["secondary_table"] == "departments"
        assert context["has_secondary_entity"] is True
        assert "employee" in context["entities"]
        assert "department" in context["entities"]

    def test_get_context_returns_copy(self, template_processor):
        """Test that get_context returns a deep copy."""
        context1 = template_processor.get_context()
        context2 = template_processor.get_context()

        context1["domain_name"] = "modified"
        assert context2["domain_name"] == "hr_system"


class TestVariableSubstitution:
    """Test Jinja2 variable substitution."""

    def test_simple_variable_substitution(self, template_processor):
        """Test basic variable substitution."""
        template = "Hello, {{ name }}!"
        result = template_processor.render_sql(template, parameters={"name": "World"})
        assert result == "Hello, World!"

    def test_domain_variable_substitution(self, template_processor):
        """Test domain context variable substitution."""
        template = "SELECT * FROM {{ primary_table }}"
        result = template_processor.render_sql(template)
        assert result == "SELECT * FROM employees"

    def test_nested_variable_substitution(self, template_processor):
        """Test nested/dotted variable access."""
        template = "Table: {{ entities.employee.table_name }}"
        result = template_processor.render_sql(template)
        assert result == "Table: employees"

    def test_parameter_overrides_context(self, template_processor):
        """Test that parameters override context variables."""
        template = "{{ primary_table }}"
        result = template_processor.render_sql(
            template,
            parameters={"primary_table": "custom_table"}
        )
        assert result == "custom_table"

    def test_extra_context(self, template_processor):
        """Test extra context is merged correctly."""
        template = "{{ custom_var }}"
        result = template_processor.render_sql(
            template,
            extra_context={"custom_var": "custom_value"}
        )
        assert result == "custom_value"


class TestConditionalBlocks:
    """Test Jinja2 conditional blocks."""

    def test_if_true(self, template_processor):
        """Test if block when condition is true."""
        template = "{% if name %}Hello, {{ name }}!{% endif %}"
        result = template_processor.render_sql(template, parameters={"name": "Alice"})
        assert result == "Hello, Alice!"

    def test_if_false(self, template_processor):
        """Test if block when condition is false (empty value)."""
        template = "{% if name %}Hello, {{ name }}!{% endif %}"
        result = template_processor.render_sql(template, parameters={"name": ""})
        assert result == ""

    def test_if_missing(self, template_processor):
        """Test if block when variable is missing."""
        template = "{% if name %}Hello, {{ name }}!{% endif %}"
        result = template_processor.render_sql(template, parameters={})
        assert result == ""

    def test_if_else(self, template_processor):
        """Test if-else blocks."""
        template = "{% if name %}Hello, {{ name }}!{% else %}Hello, Guest!{% endif %}"

        result_with = template_processor.render_sql(template, parameters={"name": "Bob"})
        assert result_with == "Hello, Bob!"

        result_without = template_processor.render_sql(template, parameters={})
        assert result_without == "Hello, Guest!"

    def test_elif(self, template_processor):
        """Test if-elif-else blocks."""
        template = """{% if level == 'admin' %}Admin User{% elif level == 'user' %}Regular User{% else %}Guest{% endif %}"""

        result_admin = template_processor.render_sql(template, parameters={"level": "admin"})
        assert result_admin == "Admin User"

        result_user = template_processor.render_sql(template, parameters={"level": "user"})
        assert result_user == "Regular User"

        result_guest = template_processor.render_sql(template, parameters={"level": "other"})
        assert result_guest == "Guest"

    def test_nested_conditionals(self, template_processor):
        """Test nested if blocks."""
        template = """{% if outer %}OUTER{% if inner %}INNER{% endif %}{% endif %}"""

        result = template_processor.render_sql(
            template,
            parameters={"outer": True, "inner": True}
        )
        assert result == "OUTERINNER"

        result_no_inner = template_processor.render_sql(
            template,
            parameters={"outer": True, "inner": False}
        )
        assert result_no_inner == "OUTER"

    def test_not_condition(self, template_processor):
        """Test negated conditions."""
        template = "{% if not is_active %}INACTIVE{% endif %}"

        result_false = template_processor.render_sql(template, parameters={"is_active": False})
        assert result_false == "INACTIVE"

        result_true = template_processor.render_sql(template, parameters={"is_active": True})
        assert result_true == ""

    def test_and_condition(self, template_processor):
        """Test AND conditions."""
        template = "{% if a and b %}BOTH{% endif %}"

        result_both = template_processor.render_sql(template, parameters={"a": True, "b": True})
        assert result_both == "BOTH"

        result_one = template_processor.render_sql(template, parameters={"a": True, "b": False})
        assert result_one == ""

    def test_or_condition(self, template_processor):
        """Test OR conditions."""
        template = "{% if a or b %}ANY{% endif %}"

        result_both = template_processor.render_sql(template, parameters={"a": True, "b": False})
        assert result_both == "ANY"

        result_none = template_processor.render_sql(template, parameters={"a": False, "b": False})
        assert result_none == ""


class TestCustomFilters:
    """Test custom Jinja2 filters."""

    def test_sql_string_filter(self, template_processor):
        """Test SQL string escaping filter."""
        template = "{{ name | sql_string }}"

        result = template_processor.render_sql(template, parameters={"name": "John"})
        assert result == "'John'"

        # Test escaping single quotes
        result_escape = template_processor.render_sql(
            template,
            parameters={"name": "O'Brien"}
        )
        assert result_escape == "'O''Brien'"

    def test_sql_string_null(self, template_processor):
        """Test SQL string filter with None."""
        template = "{{ name | sql_string }}"
        result = template_processor.render_sql(template, parameters={"name": None})
        assert result == "NULL"

    def test_sql_list_filter(self, template_processor):
        """Test SQL list filter."""
        template = "{{ items | sql_list }}"

        result = template_processor.render_sql(
            template,
            parameters={"items": ["a", "b", "c"]}
        )
        assert result == "'a', 'b', 'c'"

    def test_sql_list_empty(self, template_processor):
        """Test SQL list filter with empty list."""
        template = "{{ items | sql_list }}"
        result = template_processor.render_sql(template, parameters={"items": []})
        assert result == "NULL"

    def test_json_filter(self, template_processor):
        """Test JSON encoding filter."""
        template = "{{ data | json }}"

        result = template_processor.render_sql(
            template,
            parameters={"data": {"key": "value"}}
        )
        assert result == '{"key": "value"}'

        result_list = template_processor.render_sql(
            template,
            parameters={"data": [1, 2, 3]}
        )
        assert result_list == "[1, 2, 3]"

    def test_tojson_filter(self, template_processor):
        """Test tojson alias for json filter."""
        template = "{{ data | tojson }}"
        result = template_processor.render_sql(
            template,
            parameters={"data": ["a", "b"]}
        )
        assert result == '["a", "b"]'

    def test_default_filter(self, template_processor):
        """Test Jinja2 default filter."""
        template = "{{ name | default('Unknown') }}"

        result_with = template_processor.render_sql(template, parameters={"name": "Alice"})
        assert result_with == "Alice"

        result_without = template_processor.render_sql(template, parameters={})
        assert result_without == "Unknown"


class TestPreserveUnknown:
    """Test preserve_unknown functionality."""

    def test_preserve_unknown_true(self, template_processor):
        """Test that unknown variables are preserved when flag is True."""
        template = "Hello, {{ unknown_var }}!"
        result = template_processor.render_sql(
            template,
            parameters={},
            preserve_unknown=True
        )
        assert "{{ unknown_var }}" in result

    def test_preserve_unknown_false(self, template_processor):
        """Test that unknown variables cause an error when flag is False."""
        from jinja2 import UndefinedError
        template = "Hello, {{ unknown_var }}!"
        # This should raise an UndefinedError since unknown variables aren't allowed
        with pytest.raises(UndefinedError):
            template_processor.render_sql(
                template,
                parameters={},
                preserve_unknown=False
            )


class TestRenderTemplateStructure:
    """Test recursive template structure rendering."""

    def test_render_dict(self, template_processor):
        """Test rendering a dictionary structure."""
        template = {
            "table": "{{ primary_table }}",
            "name": "{{ name }}"
        }
        result = template_processor.render_template_structure(
            template,
            extra_context={"name": "Test"}
        )
        assert result["table"] == "employees"
        assert result["name"] == "Test"

    def test_render_nested_dict(self, template_processor):
        """Test rendering nested dictionary structure."""
        template = {
            "outer": {
                "inner": "{{ value }}"
            }
        }
        result = template_processor.render_template_structure(
            template,
            extra_context={"value": "nested_value"}
        )
        assert result["outer"]["inner"] == "nested_value"

    def test_render_list(self, template_processor):
        """Test rendering a list of templates."""
        template = {
            "items": ["{{ a }}", "{{ b }}", "{{ c }}"]
        }
        result = template_processor.render_template_structure(
            template,
            extra_context={"a": "1", "b": "2", "c": "3"}
        )
        assert result["items"] == ["1", "2", "3"]

    def test_render_mixed_structure(self, template_processor):
        """Test rendering complex mixed structure."""
        template = {
            "query": {
                "table": "{{ primary_table }}",
                "filters": [
                    {"field": "name", "value": "{{ name }}"},
                    {"field": "id", "value": "{{ id }}"}
                ]
            }
        }
        result = template_processor.render_template_structure(
            template,
            extra_context={"name": "John", "id": "123"}
        )
        assert result["query"]["table"] == "employees"
        assert result["query"]["filters"][0]["value"] == "John"
        assert result["query"]["filters"][1]["value"] == "123"


class TestSQLTemplates:
    """Test SQL-specific template patterns."""

    def test_sql_where_clause(self, template_processor):
        """Test SQL WHERE clause with conditionals."""
        template = """SELECT * FROM {{ primary_table }}
WHERE 1=1
{% if name %}AND name = {{ name | sql_string }}{% endif %}
{% if status %}AND status = {{ status | sql_string }}{% endif %}"""

        result = template_processor.render_sql(
            template,
            parameters={"name": "John", "status": "active"}
        )
        assert "AND name = 'John'" in result
        assert "AND status = 'active'" in result

    def test_sql_in_clause(self, template_processor):
        """Test SQL IN clause with list."""
        template = "SELECT * FROM users WHERE id IN ({{ ids | sql_list }})"

        result = template_processor.render_sql(
            template,
            parameters={"ids": [1, 2, 3]}
        )
        assert "IN ('1', '2', '3')" in result

    def test_sql_optional_join(self, template_processor):
        """Test SQL optional JOIN clause."""
        template = """SELECT * FROM {{ primary_table }} e
{% if include_department %}
INNER JOIN {{ secondary_table }} d ON e.department_id = d.id
{% endif %}"""

        result_with = template_processor.render_sql(
            template,
            parameters={"include_department": True}
        )
        assert "INNER JOIN departments" in result_with

        result_without = template_processor.render_sql(
            template,
            parameters={"include_department": False}
        )
        assert "INNER JOIN" not in result_without


class TestMongoDBTemplates:
    """Test MongoDB-specific template patterns."""

    def test_mongodb_query(self, template_processor):
        """Test MongoDB query template."""
        template = """{
  "filter": {
    {% if title %}
    "title": { "$regex": "{{ title }}", "$options": "i" }
    {% endif %}
  }
}"""
        result = template_processor.render_sql(
            template,
            parameters={"title": "Matrix"}
        )
        assert '"title":' in result
        assert '"Matrix"' in result

    def test_mongodb_array_in(self, template_processor):
        """Test MongoDB $in with array."""
        template = '{"genres": {"$in": {{ genres | tojson }}}}'
        result = template_processor.render_sql(
            template,
            parameters={"genres": ["Action", "Drama"]}
        )
        assert '["Action", "Drama"]' in result


class TestElasticsearchTemplates:
    """Test Elasticsearch-specific template patterns."""

    def test_elasticsearch_bool_query(self, template_processor):
        """Test Elasticsearch bool query template."""
        template = """{
  "query": {
    "bool": {
      "must": [
        {"match": {"level": "ERROR"}}
        {% if message %}
        ,{"match": {"message": "{{ message }}"}}
        {% endif %}
      ]
    }
  }
}"""
        result = template_processor.render_sql(
            template,
            parameters={"message": "connection timeout"}
        )
        assert '"match":' in result
        assert '"connection timeout"' in result


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_template(self, template_processor):
        """Test empty template string."""
        result = template_processor.render_sql("")
        assert result == ""

    def test_none_template(self, template_processor):
        """Test None template."""
        result = template_processor.render_sql(None)
        assert result is None

    def test_no_template_syntax(self, template_processor):
        """Test plain text without template syntax."""
        template = "SELECT * FROM users"
        result = template_processor.render_sql(template)
        assert result == "SELECT * FROM users"

    def test_whitespace_handling(self, template_processor):
        """Test that multiple blank lines are cleaned up."""
        template = """Line 1

{% if false %}
This should not appear
{% endif %}

Line 2"""
        result = template_processor.render_sql(template, parameters={"false": False})
        # Should not have multiple consecutive blank lines
        assert "\n\n\n" not in result
