"""Pulse connection info."""

from asyncio import AbstractEventLoop
from re import search

from aiohttp import ClientSession
from typeguard import typechecked

from .const import (
    ADT_DEFAULT_HTTP_ACCEPT_HEADERS,
    ADT_DEFAULT_HTTP_USER_AGENT,
    ADT_DEFAULT_SEC_FETCH_HEADERS,
    API_HOST_CA,
    API_PREFIX,
    DEFAULT_API_HOST,
)
from .util import set_debug_lock


class PulseConnectionProperties:
    """Pulse connection info."""

    __slots__ = (
        "_api_host",
        "_session",
        "_user_agent",
        "_loop",
        "_api_version",
        "_pci_attribute_lock",
        "_detailed_debug_logging",
        "_debug_locks",
    )

    @staticmethod
    @typechecked
    def check_service_host(service_host: str) -> None:
        """Check if service host is valid."""
        if service_host is None or service_host == "":
            raise ValueError("Service host is mandatory")
        if service_host not in (DEFAULT_API_HOST, API_HOST_CA):
            raise ValueError(
                f"Service host must be one of {DEFAULT_API_HOST}" f" or {API_HOST_CA}"
            )

    @staticmethod
    def get_api_version(response_path: str) -> str | None:
        """Regex used to exctract the API version.

        Use for testing.
        """
        version: str | None = None
        if not response_path:
            return None
        m = search(f"{API_PREFIX}(.+)/[a-z]*/", response_path)
        if m is not None:
            version = m.group(1)
        return version

    def __init__(
        self,
        host: str,
        user_agent=ADT_DEFAULT_HTTP_USER_AGENT["User-Agent"],
        detailed_debug_logging=False,
        debug_locks=False,
    ) -> None:
        """Initialize Pulse connection information."""
        self._pci_attribute_lock = set_debug_lock(
            debug_locks, "pyadtpulse.pci_attribute_lock"
        )
        self.debug_locks = debug_locks
        self.detailed_debug_logging = detailed_debug_logging
        self._loop: AbstractEventLoop | None = None
        self._session: ClientSession | None = None
        self.service_host = host
        self._api_version = ""
        self._user_agent = user_agent

    def __del__(self):
        """Destructor for ADTPulseConnection."""
        if self._session is not None and not self._session.closed:
            self._session.detach()

    def _set_headers(self) -> None:
        if self._session is not None:
            self._session.headers.update(ADT_DEFAULT_HTTP_ACCEPT_HEADERS)
            self._session.headers.update(ADT_DEFAULT_SEC_FETCH_HEADERS)
            self._session.headers.update({"User-Agent": self._user_agent})

    @property
    def service_host(self) -> str:
        """Get the service host."""
        with self._pci_attribute_lock:
            return self._api_host

    @service_host.setter
    @typechecked
    def service_host(self, host: str):
        """Set the service host.

        Raises:
            ValueError if host is not valid.
        """
        self.check_service_host(host)
        with self._pci_attribute_lock:
            self._api_host = host

    @property
    def detailed_debug_logging(self) -> bool:
        """Get the detailed debug logging flag."""
        with self._pci_attribute_lock:
            return self._detailed_debug_logging

    @detailed_debug_logging.setter
    @typechecked
    def detailed_debug_logging(self, value: bool):
        """Set the detailed debug logging flag."""
        with self._pci_attribute_lock:
            self._detailed_debug_logging = value

    @property
    def debug_locks(self) -> bool:
        """Get the debug locks flag."""
        with self._pci_attribute_lock:
            return self._debug_locks

    @debug_locks.setter
    @typechecked
    def debug_locks(self, value: bool):
        """Set the debug locks flag."""
        with self._pci_attribute_lock:
            self._debug_locks = value

    @typechecked
    def check_sync(self, message: str) -> AbstractEventLoop:
        """Checks if sync login was performed.

        Returns the loop to use for run_coroutine_threadsafe if so.
        Raises RuntimeError with given message if not.
        """
        with self._pci_attribute_lock:
            if self._loop is None:
                raise RuntimeError(message)
            return self._loop

    @typechecked
    def check_async(self, message: str) -> None:
        """Checks if async login was performed.

        Raises RuntimeError with given message if not.
        """
        with self._pci_attribute_lock:
            if self._loop is not None:
                raise RuntimeError(message)

    @property
    def loop(self) -> AbstractEventLoop | None:
        """Get the event loop."""
        with self._pci_attribute_lock:
            return self._loop

    @loop.setter
    @typechecked
    def loop(self, loop: AbstractEventLoop | None):
        """Set the event loop."""
        with self._pci_attribute_lock:
            self._loop = loop

    @property
    def session(self) -> ClientSession:
        """Get the session."""
        with self._pci_attribute_lock:
            if self._session is None:
                self._session = ClientSession()
            self._set_headers()
            return self._session

    @property
    def api_version(self) -> str:
        """Get the API version."""
        with self._pci_attribute_lock:
            return self._api_version

    @api_version.setter
    @typechecked
    def api_version(self, version: str):
        """Set the API version.

        Raises:
            ValueError: if version is not in the form major.minor.patch-subpatch
        """

        def check_version_string(value: str):
            parts = value.split("-")
            if len(parts) == 2:
                version_parts = parts[0].split(".")
                if not (
                    version_parts[0].isdigit()
                    and version_parts[1].isdigit()
                    and version_parts[2].isdigit()
                    and parts[1].isdigit()
                ):
                    raise ValueError(
                        "API version must be in the form major.minor.patch-subpatch"
                    )
                if len(version_parts) == 3 and version_parts[0].isdigit():
                    major_version = int(version_parts[0])
                    if major_version >= 26:
                        return
                    else:
                        raise ValueError("API version is numeric but less than 26")
            raise ValueError(
                "API version must be in the form major.minor.patch-subpatch"
            )

        with self._pci_attribute_lock:
            check_version_string(version)
            self._api_version = version

    @typechecked
    def make_url(self, uri: str) -> str:
        """Create a URL to service host from a URI.

        Args:
            uri (str): the URI to convert

        Returns:
            str: the converted string
        """
        with self._pci_attribute_lock:
            return f"{self._api_host}{API_PREFIX}{self._api_version}{uri}"

    async def clear_session(self):
        """Clear the session."""
        with self._pci_attribute_lock:
            old_session = self._session
            self._session = None
            if old_session:
                await old_session.close()
