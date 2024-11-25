"""PyADTPulse Properties."""

import logging
import asyncio
from warnings import warn

from typeguard import typechecked

from .const import (
    ADT_DEFAULT_KEEPALIVE_INTERVAL,
    ADT_DEFAULT_RELOGIN_INTERVAL,
    ADT_MAX_KEEPALIVE_INTERVAL,
    ADT_MIN_RELOGIN_INTERVAL,
)
from .site import ADTPulseSite
from .util import set_debug_lock

LOG = logging.getLogger(__name__)


class PyADTPulseProperties:
    """PyADTPulse Properties."""

    __slots__ = (
        "_updates_exist",
        "_pp_attribute_lock",
        "_relogin_interval",
        "_keepalive_interval",
        "_site",
    )

    @staticmethod
    @typechecked
    def _check_keepalive_interval(keepalive_interval: int) -> None:
        if keepalive_interval > ADT_MAX_KEEPALIVE_INTERVAL or keepalive_interval <= 0:
            raise ValueError(
                f"keepalive interval ({keepalive_interval}) must be "
                f"greater than 0 and less than {ADT_MAX_KEEPALIVE_INTERVAL}"
            )

    @staticmethod
    @typechecked
    def _check_relogin_interval(relogin_interval: int) -> None:
        if relogin_interval < ADT_MIN_RELOGIN_INTERVAL:
            raise ValueError(
                f"relogin interval ({relogin_interval}) must be "
                f"greater than {ADT_MIN_RELOGIN_INTERVAL}"
            )

    @typechecked
    def __init__(
        self,
        keepalive_interval: int = ADT_DEFAULT_KEEPALIVE_INTERVAL,
        relogin_interval: int = ADT_DEFAULT_RELOGIN_INTERVAL,
        debug_locks: bool = False,
    ) -> None:
        """Create a PyADTPulse properties object.
        Args:
        pulse_authentication_properties (PulseAuthenticationProperties):
            an instance of PulseAuthenticationProperties
        pulse_connection_properties (PulseConnectionProperties):
        """
        # FIXME use thread event/condition, regular condition?
        # defer initialization to make sure we have an event loop

        self._updates_exist = asyncio.locks.Event()

        self._pp_attribute_lock = set_debug_lock(
            debug_locks, "pyadtpulse.async_attribute_lock"
        )

        self._site: ADTPulseSite | None = None
        self.keepalive_interval = keepalive_interval
        self.relogin_interval = relogin_interval

    @property
    def relogin_interval(self) -> int:
        """Get re-login interval.

        Returns:
            int: number of minutes to re-login to Pulse
                 0 means disabled
        """
        with self._pp_attribute_lock:
            return self._relogin_interval

    @relogin_interval.setter
    @typechecked
    def relogin_interval(self, interval: int | None) -> None:
        """Set re-login interval.

        Args:
            interval (int|None): The number of minutes between logins.
                            If set to None, resets to ADT_DEFAULT_RELOGIN_INTERVAL

        Raises:
            ValueError: if a relogin interval of less than ADT_MIN_RELOGIN_INTERVAL
                        minutes is specified
        """
        if interval is None:
            interval = ADT_DEFAULT_RELOGIN_INTERVAL
        else:
            self._check_relogin_interval(interval)
        with self._pp_attribute_lock:
            self._relogin_interval = interval
            LOG.debug("relogin interval set to %d", self._relogin_interval)

    @property
    def keepalive_interval(self) -> int:
        """Get the keepalive interval in minutes.

        Returns:
            int: the keepalive interval
        """
        with self._pp_attribute_lock:
            return self._keepalive_interval

    @keepalive_interval.setter
    @typechecked
    def keepalive_interval(self, interval: int | None) -> None:
        """Set the keepalive interval in minutes.

        Args:
            interval (int|None): The number of minutes between keepalive calls
                                 If set to None, resets to ADT_DEFAULT_KEEPALIVE_INTERVAL

        Raises:
            ValueError: if a keepalive interval of greater than ADT_MAX_KEEPALIVE_INTERVAL
                        minutes is specified
        """
        if interval is None:
            interval = ADT_DEFAULT_KEEPALIVE_INTERVAL
        else:
            self._check_keepalive_interval(interval)
        with self._pp_attribute_lock:
            self._keepalive_interval = interval
            LOG.debug("keepalive interval set to %d", self._keepalive_interval)

    @property
    def sites(self) -> list[ADTPulseSite]:
        """Return all sites for this ADT Pulse account."""
        warn(
            "multiple sites being removed, use pyADTPulse.site instead",
            PendingDeprecationWarning,
            stacklevel=2,
        )
        with self._pp_attribute_lock:
            if self._site is None:
                raise RuntimeError(
                    "No sites have been retrieved, have you logged in yet?"
                )
            return [self._site]

    @property
    def site(self) -> ADTPulseSite:
        """Return the site associated with the Pulse login."""
        with self._pp_attribute_lock:
            if self._site is None:
                raise RuntimeError(
                    "No sites have been retrieved, have you logged in yet?"
                )
            return self._site

    def set_update_status(self) -> None:
        """Sets updates_exist to notify wait_for_update."""
        with self._pp_attribute_lock:
            self.updates_exist.set()

    @property
    def updates_exist(self) -> asyncio.locks.Event:
        """Check if updates exist."""
        with self._pp_attribute_lock:
            return self._updates_exist
