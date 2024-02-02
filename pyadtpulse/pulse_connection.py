"""ADT Pulse connection. End users should probably not call this directly.

This is the main interface to the http functions to access ADT Pulse.
"""

import logging
import re
from asyncio import AbstractEventLoop
from time import time

from bs4 import BeautifulSoup
from typeguard import typechecked
from yarl import URL

from .const import (
    ADT_DEFAULT_LOGIN_TIMEOUT,
    ADT_LOGIN_URI,
    ADT_LOGOUT_URI,
    ADT_MFA_FAIL_URI,
    ADT_SUMMARY_URI,
)
from .exceptions import (
    PulseAccountLockedError,
    PulseAuthenticationError,
    PulseClientConnectionError,
    PulseMFARequiredError,
    PulseNotLoggedInError,
    PulseServerConnectionError,
    PulseServiceTemporarilyUnavailableError,
)
from .pulse_authentication_properties import PulseAuthenticationProperties
from .pulse_backoff import PulseBackoff
from .pulse_connection_properties import PulseConnectionProperties
from .pulse_connection_status import PulseConnectionStatus
from .pulse_query_manager import PulseQueryManager
from .util import make_soup, set_debug_lock

LOG = logging.getLogger(__name__)


SESSION_COOKIES = {"X-mobile-browser": "false", "ICLocal": "en_US"}


class PulseConnection(PulseQueryManager):
    """ADT Pulse connection related attributes."""

    __slots__ = (
        "_pc_attribute_lock",
        "_authentication_properties",
        "_login_backoff",
        "_login_in_progress",
    )

    @typechecked
    def __init__(
        self,
        pulse_connection_status: PulseConnectionStatus,
        pulse_connection_properties: PulseConnectionProperties,
        pulse_authentication: PulseAuthenticationProperties,
        debug_locks: bool = False,
    ):
        """Initialize ADT Pulse connection."""

        # need to initialize this after the session since we set cookies
        # based on it
        super().__init__(
            pulse_connection_status,
            pulse_connection_properties,
            debug_locks,
        )
        self._pc_attribute_lock = set_debug_lock(
            debug_locks, "pyadtpulse.pc_attribute_lock"
        )
        self._connection_properties = pulse_connection_properties
        self._connection_status = pulse_connection_status
        self._authentication_properties = pulse_authentication
        self._login_backoff = PulseBackoff(
            "Login",
            pulse_connection_status._backoff.initial_backoff_interval,
            detailed_debug_logging=self._connection_properties.detailed_debug_logging,
        )
        self._login_in_progress = False
        self._debug_locks = debug_locks

    @typechecked
    def check_login_errors(
        self, response: tuple[int, str | None, URL | None]
    ) -> BeautifulSoup:
        """Check response for login errors.

        Will handle setting backoffs and raising exceptions.

        Args:
            response (tuple[int, str | None, URL | None]): The response

        Returns:
            BeautifulSoup: The parsed response

        Raises:
            PulseAuthenticationError: if login fails due to incorrect username/password
            PulseServerConnectionError: if login fails due to server error
            PulseAccountLockedError: if login fails due to account locked
            PulseMFARequiredError: if login fails due to MFA required
            PulseNotLoggedInError: if login fails due to not logged in
        """

        def extract_seconds_from_string(s: str) -> int:
            seconds = 0
            match = re.search(r"\d+", s)
            if match:
                seconds = int(match.group())
                if "minutes" in s:
                    seconds *= 60
            return seconds

        def determine_error_type():
            """Determine what type of error we have from the url and the parsed page.

            Will raise the appropriate exception.
            """
            self._login_in_progress = False
            url = self._connection_properties.make_url(ADT_LOGIN_URI)
            if url == response_url_string:
                error = soup.find("div", {"id": "warnMsgContents"})
                if error:
                    error_text = error.get_text()
                    LOG.error("Error logging into pulse: %s", error_text)
                    if "Try again in" in error_text:
                        if (retry_after := extract_seconds_from_string(error_text)) > 0:
                            raise PulseAccountLockedError(
                                self._login_backoff,
                                retry_after + time(),
                            )
                    elif "You have not yet signed in" in error_text:
                        raise PulseNotLoggedInError()
                    elif "Sign In Unsuccessful" in error_text:
                        raise PulseAuthenticationError()
                else:
                    raise PulseNotLoggedInError()
            else:
                url = self._connection_properties.make_url(ADT_MFA_FAIL_URI)
                if url == response_url_string:
                    raise PulseMFARequiredError()

        soup = make_soup(
            response[0],
            response[1],
            response[2],
            logging.ERROR,
            "Could not log into ADT Pulse site",
        )
        # this probably should have been handled by async_query()
        if soup is None:
            raise PulseServerConnectionError(
                f"Could not log into ADT Pulse site: code {response[0]}: URL: {response[2]}, response: {response[1]}",
                self._login_backoff,
            )
        url = self._connection_properties.make_url(ADT_SUMMARY_URI)
        response_url_string = str(response[2])
        if url != response_url_string:
            determine_error_type()
            raise PulseAuthenticationError()
        return soup

    @typechecked
    async def async_do_login_query(
        self, timeout: int = ADT_DEFAULT_LOGIN_TIMEOUT
    ) -> BeautifulSoup | None:
        """
        Performs a login query to the Pulse site.

        Will backoff on login failures.

        Will set login in progress flag.

        Args:
            timeout (int, optional): The timeout value for the query in seconds.
            Defaults to ADT_DEFAULT_LOGIN_TIMEOUT.

        Returns:
            soup: Optional[BeautifulSoup]: A BeautifulSoup object containing
            summary.jsp, or None if failure
        Raises:
            ValueError: if login parameters are not correct
            PulseAuthenticationError: if login fails due to incorrect username/password
            PulseServerConnectionError: if login fails due to server error
            PulseServiceTemporarilyUnavailableError: if login fails due to too many requests or
                server is temporarily unavailable
            PulseAccountLockedError: if login fails due to account locked
            PulseMFARequiredError: if login fails due to MFA required
            PulseNotLoggedInError: if login fails due to not logged in (which is probably an internal error)
        """

        if self.login_in_progress:
            return None
        await self.quick_logout()
        # just raise exceptions if we're not going to be able to log in
        lockout_time = self._login_backoff.expiration_time
        if lockout_time > time():
            raise PulseAccountLockedError(self._login_backoff, lockout_time)
        cs_backoff = self._connection_status.get_backoff()
        lockout_time = cs_backoff.expiration_time
        if lockout_time > time():
            raise PulseServiceTemporarilyUnavailableError(cs_backoff, lockout_time)
        self.login_in_progress = True
        data = {
            "usernameForm": self._authentication_properties.username,
            "passwordForm": self._authentication_properties.password,
            "networkid": self._authentication_properties.site_id,
            "fingerprint": self._authentication_properties.fingerprint,
        }
        await self._login_backoff.wait_for_backoff()
        try:
            response = await self.async_query(
                ADT_LOGIN_URI,
                "POST",
                extra_params=data,
                timeout=timeout,
                requires_authentication=False,
            )
        except (
            PulseClientConnectionError,
            PulseServerConnectionError,
            PulseServiceTemporarilyUnavailableError,
        ) as e:
            LOG.error("Could not log into Pulse site: %s", e)
            self.login_in_progress = False
            raise
        soup = self.check_login_errors(response)
        self._connection_status.authenticated_flag.set()
        self._authentication_properties.last_login_time = int(time())
        self._login_backoff.reset_backoff()
        self.login_in_progress = False
        return soup

    @typechecked
    async def async_do_logout_query(self, site_id: str | None = None) -> None:
        """Performs a logout query to the ADT Pulse site."""
        params = {}
        si = ""
        self._connection_status.authenticated_flag.clear()
        if site_id is not None and site_id != "":
            self._authentication_properties.site_id = site_id
            si = site_id
        params.update({"networkid": si})

        params.update({"partner": "adt"})
        try:
            await self.async_query(
                ADT_LOGOUT_URI,
                extra_params=params,
                timeout=10,
                requires_authentication=False,
            )
        # FIXME: do we care if this raises exceptions?
        except (
            PulseClientConnectionError,
            PulseServiceTemporarilyUnavailableError,
            PulseServerConnectionError,
        ) as e:
            LOG.debug("Could not logout from Pulse site: %s", e)

    @property
    def is_connected(self) -> bool:
        """Check if ADT Pulse is connected."""
        return (
            self._connection_status.authenticated_flag.is_set()
            and not self._login_in_progress
        )

    @property
    def login_backoff(self) -> PulseBackoff:
        """Return backoff object."""
        with self._pc_attribute_lock:
            return self._login_backoff

    def check_sync(self, message: str) -> AbstractEventLoop:
        """Convenience method to check if running from sync context."""
        return self._connection_properties.check_sync(message)

    @property
    def debug_locks(self):
        """Return debug locks."""
        return self._debug_locks

    @property
    def login_in_progress(self) -> bool:
        """Return login in progress."""
        with self._pc_attribute_lock:
            return self._login_in_progress

    @login_in_progress.setter
    @typechecked
    def login_in_progress(self, value: bool) -> None:
        """Set login in progress."""
        with self._pc_attribute_lock:
            self._login_in_progress = value

    async def quick_logout(self) -> None:
        """Quickly logout.

        This just resets the authenticated flag and clears the ClientSession.
        """
        LOG.debug("Resetting session")
        self._connection_status.authenticated_flag.clear()
        await self._connection_properties.clear_session()

    @property
    def detailed_debug_logging(self) -> bool:
        """Return detailed debug logging."""
        return (
            self._login_backoff.detailed_debug_logging
            and self._connection_properties.detailed_debug_logging
            and self._connection_status.detailed_debug_logging
        )

    @detailed_debug_logging.setter
    @typechecked
    def detailed_debug_logging(self, value: bool):
        with self._pc_attribute_lock:
            self._login_backoff.detailed_debug_logging = value
            self._connection_properties.detailed_debug_logging = value
            self._connection_status.detailed_debug_logging = value

    def get_login_backoff(self) -> PulseBackoff:
        """Return login backoff."""
        return self._login_backoff
