"""Custom exceptions for ORBIT CLI."""


class OrbitError(Exception):
    """Base exception for ORBIT CLI errors."""
    pass


class ServerError(OrbitError):
    """Server-related errors."""
    pass


class AuthenticationError(OrbitError):
    """Authentication-related errors."""
    pass


class ConfigurationError(OrbitError):
    """Configuration-related errors."""
    pass


class NetworkError(OrbitError):
    """Network-related errors."""
    pass


class ValidationError(OrbitError):
    """Input validation errors."""
    pass


class FileOperationError(OrbitError):
    """File operation errors."""
    pass