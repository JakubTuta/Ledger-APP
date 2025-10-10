class AuthServiceError(Exception):
    """Base exception for all auth service errors."""

    pass


class AuthenticationError(AuthServiceError):
    """Raised when authentication fails."""

    pass


class ValidationError(AuthServiceError):
    """Raised when input validation fails."""

    pass


class InvalidTokenError(AuthServiceError):
    """Raised when JWT token is invalid or expired."""

    pass


class RateLimitError(AuthServiceError):
    """Raised when rate limit is exceeded."""

    def __init__(self, message: str, limit: int, window: str, retry_after: int):
        super().__init__(message)
        self.limit = limit
        self.window = window
        self.retry_after = retry_after
