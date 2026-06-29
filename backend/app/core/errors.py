"""Domain-level exception types used by service abstractions."""


class JarvisError(Exception):
    """Base exception for controlled JARVIS failures."""


class IntegrationNotConfiguredError(JarvisError):
    """Raised when a required external integration has not been configured."""


class AuthenticationError(JarvisError):
    """Raised when credentials or tokens cannot be validated."""
