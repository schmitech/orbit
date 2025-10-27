"""
ID Utility Layer
================

This module provides backend-agnostic ID generation and conversion utilities.
It allows the application to work with different ID formats (ObjectId for MongoDB,
UUID for SQLite) without changing the service layer code.
"""

import uuid
from typing import Union, Any


def generate_id(backend_type: str = 'mongodb') -> Union[Any, str]:
    """
    Generate an ID appropriate for the specified backend type.

    Args:
        backend_type: Type of database backend ('mongodb' or 'sqlite')

    Returns:
        Generated ID (ObjectId for MongoDB, UUID string for SQLite)

    Raises:
        ValueError: If backend_type is not supported
    """
    if backend_type == 'mongodb':
        from bson import ObjectId
        return ObjectId()
    elif backend_type == 'sqlite':
        # Generate a UUID4 and return as string
        return str(uuid.uuid4())
    else:
        raise ValueError(f"Unsupported backend type: {backend_type}")


def ensure_id(id_value: Union[str, Any], backend_type: str = 'mongodb') -> Union[Any, str]:
    """
    Ensure an ID is in the correct format for the specified backend.

    This function converts string IDs to the appropriate type for the backend,
    or validates that the ID is already in the correct format.

    Args:
        id_value: ID value to convert/validate
        backend_type: Type of database backend ('mongodb' or 'sqlite')

    Returns:
        ID in the correct format for the backend

    Raises:
        ValueError: If the ID cannot be converted or is invalid
    """
    if backend_type == 'mongodb':
        from bson import ObjectId
        if isinstance(id_value, ObjectId):
            return id_value
        elif isinstance(id_value, str):
            try:
                return ObjectId(id_value)
            except Exception as e:
                raise ValueError(f"Invalid ObjectId format: {id_value}") from e
        else:
            raise ValueError(f"Cannot convert {type(id_value)} to ObjectId")

    elif backend_type == 'sqlite':
        # SQLite uses UUID strings, so just convert to string and validate
        if isinstance(id_value, str):
            # Validate that it's a valid UUID
            try:
                uuid.UUID(id_value)
                return id_value
            except ValueError as e:
                raise ValueError(f"Invalid UUID format: {id_value}") from e
        else:
            # Try to convert to string
            return str(id_value)

    else:
        raise ValueError(f"Unsupported backend type: {backend_type}")


def id_to_string(id_value: Union[str, Any]) -> str:
    """
    Convert an ID to string format.

    This function handles both ObjectId and UUID formats.

    Args:
        id_value: ID value to convert

    Returns:
        String representation of the ID
    """
    return str(id_value)


def is_valid_id(id_value: Any, backend_type: str = 'mongodb') -> bool:
    """
    Check if an ID is valid for the specified backend.

    Args:
        id_value: ID value to check
        backend_type: Type of database backend ('mongodb' or 'sqlite')

    Returns:
        True if the ID is valid, False otherwise
    """
    try:
        ensure_id(id_value, backend_type)
        return True
    except (ValueError, Exception):
        return False
