"""Pulse exceptions."""

import datetime
from time import time

from .pulse_backoff import PulseBackoff


def compute_retry_time(retry_time: float | None) -> str:
    """Compute the retry time."""
    if not retry_time:
        return "indefinitely"
    return str(datetime.datetime.fromtimestamp(retry_time))


class PulseExceptionWithBackoff(Exception):
    """Exception with backoff."""

    def __init__(self, message: str, backoff: PulseBackoff):
        """Initialize exception."""
        super().__init__(message)
        self.backoff = backoff
        self.backoff.increment_backoff()

    def __str__(self):
        """Return a string representation of the exception."""
        return f"{self.__class__.__name__}: {self.args[0]}"

    def __repr__(self):
        """Return a string representation of the exception."""
        return f"{self.__class__.__name__}(message='{self.args[0]}', backoff={self.backoff})"


class PulseExceptionWithRetry(PulseExceptionWithBackoff):
    """Exception with backoff

    If retry_time is None, or is in the past, then just the backoff count will be incremented.
    """

    def __init__(self, message: str, backoff: PulseBackoff, retry_time: float | None):
        """Initialize exception."""
        # super.__init__ will increment the backoff count
        super().__init__(message, backoff)
        self.retry_time = retry_time
        if retry_time and retry_time > time():
            # set the absolute backoff time will remove the backoff count
            self.backoff.set_absolute_backoff_time(retry_time)
            return

    def __str__(self):
        """Return a string representation of the exception."""
        return f"{self.__class__.__name__}: {self.args[0]}"

    def __repr__(self):
        """Return a string representation of the exception."""
        return f"{self.__class__.__name__}(message='{self.args[0]}', backoff={self.backoff}, retry_time={self.retry_time})"


class PulseConnectionError(Exception):
    """Base class for connection errors"""


class PulseServerConnectionError(PulseExceptionWithBackoff, PulseConnectionError):
    """Server error."""

    def __init__(self, message: str, backoff: PulseBackoff):
        """Initialize Pulse server error exception."""
        super().__init__(f"Pulse server error: {message}", backoff)


class PulseClientConnectionError(PulseExceptionWithBackoff, PulseConnectionError):
    """Client error."""

    def __init__(self, message: str, backoff: PulseBackoff):
        """Initialize Pulse client error exception."""
        super().__init__(f"Client error connecting to Pulse: {message}", backoff)


class PulseServiceTemporarilyUnavailableError(
    PulseExceptionWithRetry, PulseConnectionError
):
    """Service temporarily unavailable error.

    For HTTP 503 and 429 errors.
    """

    def __init__(self, backoff: PulseBackoff, retry_time: float | None = None):
        """Initialize Pusle service temporarily unavailable error exception."""
        super().__init__(
            f"Pulse service temporarily unavailable until {compute_retry_time(retry_time)}",
            backoff,
            retry_time,
        )


class PulseLoginException(Exception):
    """Login exceptions.

    Base class for catching all login exceptions."""


class PulseAuthenticationError(PulseLoginException):
    """Authentication error."""

    def __init__(self):
        """Initialize Pulse Authentication error exception."""
        super().__init__("Error authenticating to Pulse")


class PulseAccountLockedError(PulseExceptionWithRetry, PulseLoginException):
    """Account locked error."""

    def __init__(self, backoff: PulseBackoff, retry: float):
        """Initialize Pulse Account locked error exception."""
        super().__init__(
            f"Pulse Account is locked until {compute_retry_time(retry)}", backoff, retry
        )


class PulseGatewayOfflineError(PulseExceptionWithBackoff):
    """Gateway offline error."""

    def __init__(self, backoff: PulseBackoff):
        """Initialize Pulse Gateway offline error exception."""
        super().__init__("Gateway is offline", backoff)


class PulseMFARequiredError(PulseLoginException):
    """MFA required error."""

    def __init__(self):
        """Initialize Pulse MFA required error exception."""
        super().__init__("Authentication failed because MFA is required")


class PulseNotLoggedInError(PulseLoginException):
    """Exception to indicate that the application code is not logged in.

    Used for signalling waiters.
    """

    def __init__(self):
        """Initialize Pulse Not logged in error exception."""
        super().__init__("Not logged into Pulse")
