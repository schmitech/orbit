"""
Configuration utility functions.

This module contains utility functions for working with configuration values,
particularly for parsing and validating configuration settings.
"""

from typing import Union


def is_true_value(value: Union[str, bool, int, float]) -> bool:
    """
    Check if a value (string or boolean) is equivalent to True.
    
    This function handles various formats that might represent boolean values:
    - Boolean values: True/False
    - String values: 'true', 'yes', 'y', '1', 'on' (case-insensitive)
    - Numeric values: 0 is False, anything else is True
    - Other types: False
    
    Args:
        value: The value to check, can be string, boolean, or numeric
        
    Returns:
        bool: True if the value represents a truthy value, False otherwise
        
    Examples:
        >>> is_true_value(True)
        True
        >>> is_true_value("true")
        True
        >>> is_true_value("YES")
        True
        >>> is_true_value("1")
        True
        >>> is_true_value(False)
        False
        >>> is_true_value("false")
        False
        >>> is_true_value(0)
        False
        >>> is_true_value(1)
        True
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ('true', 'yes', 'y', '1', 'on')
    # Numeric values - 0 is False, anything else is True
    if isinstance(value, (int, float)):
        return bool(value)
    # Default for anything else
    return False 