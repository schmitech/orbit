"""
Tests for Validator (server/retrievers/implementations/intent/domain/extraction/validator.py).

Covers type checks, min/max/length/pattern/allowed_values rules, sanitize(),
and validate_all() across dotted and bare parameter keys.
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from retrievers.implementations.intent.domain.config import DomainConfig
from retrievers.implementations.intent.domain.extraction.validator import Validator


def make_domain_config():
    return DomainConfig({
        "domain_name": "Test",
        "entities": {
            "employee": {"table_name": "employees"},
        },
        "fields": {
            "employee": {
                "age": {
                    "data_type": "integer",
                    "validation_rules": {"min": 18, "max": 65},
                },
                "email": {
                    "data_type": "email",
                },
                "name": {
                    "data_type": "string",
                    "validation_rules": {"min_length": 2, "max_length": 5},
                },
                "status": {
                    "data_type": "string",
                    "validation_rules": {"allowed_values": ["active", "terminated", "on_leave"]},
                },
                "mrn": {
                    "data_type": "string",
                    "validation_rules": {"pattern": r"^MR\d{6}$"},
                },
            }
        },
    })


class TestTypeValidation:
    def setup_method(self):
        self.validator = Validator(make_domain_config())

    def test_none_is_valid_for_any_type(self):
        is_valid, err = self.validator.validate(None, "employee", "age")
        assert is_valid and err is None

    def test_valid_integer(self):
        is_valid, err = self.validator.validate(30, "employee", "age")
        assert is_valid

    def test_integer_as_numeric_string_is_valid(self):
        is_valid, err = self.validator.validate("30", "employee", "age")
        assert is_valid

    def test_non_numeric_string_fails_integer_type(self):
        is_valid, err = self.validator.validate("not-a-number", "employee", "age")
        assert not is_valid
        assert "Invalid type" in err

    def test_valid_email(self):
        is_valid, err = self.validator.validate("a@b.com", "employee", "email")
        assert is_valid

    def test_invalid_email(self):
        is_valid, err = self.validator.validate("not-an-email", "employee", "email")
        assert not is_valid

    def test_unknown_field_skips_validation(self):
        is_valid, err = self.validator.validate("anything", "employee", "nonexistent_field")
        assert is_valid and err is None

    def test_unknown_entity_skips_validation(self):
        is_valid, err = self.validator.validate("anything", "nonexistent_entity", "age")
        assert is_valid and err is None


class TestRuleValidation:
    def setup_method(self):
        self.validator = Validator(make_domain_config())

    def test_min_violation(self):
        is_valid, err = self.validator.validate(10, "employee", "age")
        assert not is_valid
        assert "at least 18" in err

    def test_max_violation(self):
        is_valid, err = self.validator.validate(99, "employee", "age")
        assert not is_valid
        assert "at most 65" in err

    def test_within_range_is_valid(self):
        is_valid, err = self.validator.validate(40, "employee", "age")
        assert is_valid

    def test_min_length_violation(self):
        is_valid, err = self.validator.validate("a", "employee", "name")
        assert not is_valid
        assert "at least 2 characters" in err

    def test_max_length_violation(self):
        is_valid, err = self.validator.validate("toolongname", "employee", "name")
        assert not is_valid
        assert "at most 5 characters" in err

    def test_allowed_values_accepts_member(self):
        is_valid, err = self.validator.validate("active", "employee", "status")
        assert is_valid

    def test_allowed_values_rejects_non_member(self):
        is_valid, err = self.validator.validate("deceased", "employee", "status")
        assert not is_valid
        assert "must be one of" in err

    def test_pattern_match(self):
        is_valid, err = self.validator.validate("MR123456", "employee", "mrn")
        assert is_valid

    def test_pattern_mismatch(self):
        is_valid, err = self.validator.validate("not-an-mrn", "employee", "mrn")
        assert not is_valid
        assert "does not match" in err

    def test_invalid_regex_pattern_logs_and_passes(self):
        domain_config = DomainConfig({
            "entities": {"employee": {"table_name": "employees"}},
            "fields": {"employee": {"bad": {
                "data_type": "string",
                "validation_rules": {"pattern": "["},  # invalid regex
            }}},
        })
        validator = Validator(domain_config)
        is_valid, err = validator.validate("anything", "employee", "bad")
        assert is_valid and err is None


class TestSanitize:
    def setup_method(self):
        self.validator = Validator(make_domain_config())

    def test_string_is_stripped(self):
        assert self.validator.sanitize("  bob  ", "employee", "name") == "bob"

    def test_string_truncated_to_max_length(self):
        assert self.validator.sanitize("abcdefgh", "employee", "name") == "abcde"

    def test_email_lowercased(self):
        assert self.validator.sanitize("  Bob@Example.COM  ", "employee", "email") == "bob@example.com"

    def test_unknown_field_returns_value_unchanged(self):
        assert self.validator.sanitize("value", "employee", "nonexistent") == "value"


class TestValidateAll:
    def setup_method(self):
        self.validator = Validator(make_domain_config())

    def test_dotted_key_resolves_entity_and_field(self):
        errors = self.validator.validate_all({"employee.age": 10})
        assert "age" in errors
        assert "at least 18" in errors["age"][0]

    def test_bare_key_searches_across_entities(self):
        errors = self.validator.validate_all({"age": 200})
        assert "age" in errors

    def test_bare_key_with_no_matching_entity_is_skipped(self):
        errors = self.validator.validate_all({"totally_unknown_param": "value"})
        assert errors == {}

    def test_all_valid_parameters_produce_no_errors(self):
        errors = self.validator.validate_all({"employee.age": 30, "employee.status": "active"})
        assert errors == {}
