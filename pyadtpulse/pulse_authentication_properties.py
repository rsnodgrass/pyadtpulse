"""Pulse Authentication Properties."""

from re import match

from typeguard import typechecked

from .util import set_debug_lock


class PulseAuthenticationProperties:
    """Pulse Authentication Properties."""

    __slots__ = (
        "_username",
        "_password",
        "_fingerprint",
        "_paa_attribute_lock",
        "_last_login_time",
        "_site_id",
    )

    @staticmethod
    def check_username(username: str) -> None:
        """Check if username is valid.

        Raises ValueError if a login parameter is not valid."""
        if not username:
            raise ValueError("Username is mandatory")
        pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
        if not match(pattern, username):
            raise ValueError("Username must be an email address")

    @staticmethod
    @typechecked
    def check_password(password: str) -> None:
        """Check if password is valid.

        Raises ValueError if password is not valid.
        """
        if not password:
            raise ValueError("Password is mandatory")

    @staticmethod
    @typechecked
    def check_fingerprint(fingerprint: str) -> None:
        """Check if fingerprint is valid.

        Raises ValueError if password is not valid.
        """
        if not fingerprint:
            raise ValueError("Fingerprint is required")

    @typechecked
    def __init__(
        self,
        username: str,
        password: str,
        fingerprint: str,
        debug_locks: bool = False,
    ) -> None:
        """Initialize Pulse Authentication Properties."""
        self.check_username(username)
        self.check_password(password)
        self.check_fingerprint(fingerprint)
        self._username = username
        self._password = password
        self._fingerprint = fingerprint
        self._paa_attribute_lock = set_debug_lock(
            debug_locks, "pyadtpulse.paa_attribute_lock"
        )
        self._last_login_time = 0
        self._site_id = ""

    @property
    def last_login_time(self) -> int:
        """Get the last login time."""
        with self._paa_attribute_lock:
            return self._last_login_time

    @last_login_time.setter
    @typechecked
    def last_login_time(self, login_time: int) -> None:
        with self._paa_attribute_lock:
            self._last_login_time = login_time

    @property
    def username(self) -> str:
        """Get the username."""
        with self._paa_attribute_lock:
            return self._username

    @username.setter
    @typechecked
    def username(self, username: str) -> None:
        self.check_username(username)
        with self._paa_attribute_lock:
            self._username = username

    @property
    def password(self) -> str:
        """Get the password."""
        with self._paa_attribute_lock:
            return self._password

    @password.setter
    @typechecked
    def password(self, password: str) -> None:
        self.check_password(password)
        with self._paa_attribute_lock:
            self._password = password

    @property
    def fingerprint(self) -> str:
        """Get the fingerprint."""
        with self._paa_attribute_lock:
            return self._fingerprint

    @fingerprint.setter
    @typechecked
    def fingerprint(self, fingerprint: str) -> None:
        self.check_fingerprint(fingerprint)
        with self._paa_attribute_lock:
            self._fingerprint = fingerprint

    @property
    def site_id(self) -> str:
        """Get the site ID."""
        with self._paa_attribute_lock:
            return self._site_id

    @site_id.setter
    @typechecked
    def site_id(self, site_id: str) -> None:
        with self._paa_attribute_lock:
            self._site_id = site_id
