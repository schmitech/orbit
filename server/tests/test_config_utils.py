#!/usr/bin/env python3
"""
Tests for the is_true_value function from utils.config_utils
"""

import pytest
import sys
import os

# Add the server directory to the Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils import is_true_value


def test_boolean_values():
    """Test the is_true_value function with boolean inputs."""
    assert is_true_value(True) == True
    assert is_true_value(False) == False


def test_true_string_values():
    """Test the is_true_value function with truthy string inputs."""
    true_strings = ["true", "TRUE", "True", "yes", "YES", "y", "Y", "1", "on", "ON"]
    for value in true_strings:
        assert is_true_value(value) == True, f"Expected {value} to be True"


def test_false_string_values():
    """Test the is_true_value function with falsy string inputs."""
    false_strings = ["false", "FALSE", "no", "n", "0", "off", "random", ""]
    for value in false_strings:
        assert is_true_value(value) == False, f"Expected {value} to be False"


def test_numeric_values():
    """Test the is_true_value function with numeric inputs."""
    # Truthy numeric values
    assert is_true_value(1) == True
    assert is_true_value(42) == True
    assert is_true_value(-1) == True
    assert is_true_value(1.0) == True
    
    # Falsy numeric values
    assert is_true_value(0) == False
    assert is_true_value(0.0) == False


def test_other_types():
    """Test the is_true_value function with other data types."""
    # All should return False
    assert is_true_value(None) == False
    assert is_true_value([]) == False
    assert is_true_value({}) == False
    assert is_true_value(()) == False
    assert is_true_value(set()) == False


def test_edge_cases():
    """Test the is_true_value function with edge cases."""
    # Whitespace strings should be False
    assert is_true_value(" ") == False
    assert is_true_value("\t") == False
    assert is_true_value("\n") == False
    
    # Mixed case variations
    assert is_true_value("Yes") == True
    assert is_true_value("No") == False
    assert is_true_value("On") == True
    assert is_true_value("Off") == False 