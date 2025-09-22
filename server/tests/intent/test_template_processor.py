"""Tests for the template processor utility."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from retrievers.implementations.intent.template_processor import TemplateProcessor


BASIC_DOMAIN_CONFIG = {
    "domain_name": "Test",
    "entities": {
        "record": {
            "entity_type": "primary",
            "table_name": "records",
            "display_name": "Record",
        },
        "detail": {
            "entity_type": "related",
            "table_name": "record_details",
        },
    },
    "fields": {},
}


def test_template_processor_builds_context():
    processor = TemplateProcessor(BASIC_DOMAIN_CONFIG)
    context = processor.get_context()

    assert context["primary_entity"] == "record"
    assert context["primary_table"] == "records"
    assert context["secondary_entity"] == "detail"
    assert context["secondary_table"] == "record_details"
    assert context["has_secondary_entity"] is True
    assert context["entities"]["record"]["table_name"] == "records"


def test_template_processor_renders_template_structure():
    processor = TemplateProcessor(BASIC_DOMAIN_CONFIG)

    template = {
        "id": "find_record",
        "description": "Find a {{primary_entity}}",
        "tags": ["{{primary_entity}}", "lookup"],
        "semantic_tags": {
            "primary_entity": "{{primary_entity}}",
            "action": "lookup",
        },
        "sql_template": "SELECT * FROM {{primary_table}}",
    }

    rendered = processor.render_template_structure(template)

    assert rendered["description"] == "Find a record"
    assert rendered["tags"][0] == "record"
    assert rendered["semantic_tags"]["primary_entity"] == "record"
    assert rendered["sql_template"] == "SELECT * FROM records"


def test_template_processor_renders_sql_with_conditions():
    processor = TemplateProcessor(BASIC_DOMAIN_CONFIG)

    sql_template = (
        "SELECT * FROM {{primary_table}} "
        "{% if has_secondary_entity %}JOIN {{secondary_table}} s ON s.record_id = records.id {% endif %}"
        "WHERE 1=1 {% if min_id %}AND records.id >= %(min_id)s{% endif %}"
    )

    rendered_with_param = processor.render_sql(sql_template, parameters={"min_id": 10})
    assert "JOIN record_details" in rendered_with_param
    assert "records.id >= %(min_id)s" in rendered_with_param

    rendered_without_param = processor.render_sql(sql_template, parameters={"min_id": None})
    assert "JOIN record_details" in rendered_without_param
    assert "records.id >=" not in rendered_without_param

    # When domain has no secondary entity, the join should be removed
    primary_only_config = {
        "domain_name": "PrimaryOnly",
        "entities": {
            "record": {
                "entity_type": "primary",
                "table_name": "records",
            }
        },
        "fields": {},
    }
    primary_only_processor = TemplateProcessor(primary_only_config)
    rendered_primary_only = primary_only_processor.render_sql(sql_template, parameters={"min_id": 10})
    assert "JOIN" not in rendered_primary_only
