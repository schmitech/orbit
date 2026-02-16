#!/usr/bin/env python3
"""
Tests for the is_true_value function from utils.config_utils
"""

import sys
import os

# Add the server directory to the Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from utils import is_true_value


def test_boolean_values():
    """Test the is_true_value function with boolean inputs."""
    assert is_true_value(True)
    assert not is_true_value(False)


def test_true_string_values():
    """Test the is_true_value function with truthy string inputs."""
    true_strings = ["true", "TRUE", "True", "yes", "YES", "y", "Y", "1", "on", "ON"]
    for value in true_strings:
        assert is_true_value(value), f"Expected {value} to be True"


def test_false_string_values():
    """Test the is_true_value function with falsy string inputs."""
    false_strings = ["false", "FALSE", "no", "n", "0", "off", "random", ""]
    for value in false_strings:
        assert not is_true_value(value), f"Expected {value} to be False"


def test_numeric_values():
    """Test the is_true_value function with numeric inputs."""
    # Truthy numeric values
    assert is_true_value(1)
    assert is_true_value(42)
    assert is_true_value(-1)
    assert is_true_value(1.0)
    
    # Falsy numeric values
    assert not is_true_value(0)
    assert not is_true_value(0.0)


def test_other_types():
    """Test the is_true_value function with other data types."""
    # All should return False
    assert not is_true_value(None)
    assert not is_true_value([])
    assert not is_true_value({})
    assert not is_true_value(())
    assert not is_true_value(set())


def test_edge_cases():
    """Test the is_true_value function with edge cases."""
    # Whitespace strings should be False
    assert not is_true_value(" ")
    assert not is_true_value("\t")
    assert not is_true_value("\n")
    
    # Mixed case variations
    assert is_true_value("Yes")
    assert not is_true_value("No")
    assert is_true_value("On")
    assert not is_true_value("Off") 