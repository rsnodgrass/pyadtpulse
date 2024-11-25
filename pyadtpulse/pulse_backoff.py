"""Pulse backoff object."""

import asyncio
import datetime
from logging import getLogger
from time import time

from typeguard import typechecked

from .const import ADT_MAX_BACKOFF
from .util import set_debug_lock

LOG = getLogger(__name__)


class PulseBackoff:
    """Pulse backoff object."""

    __slots__ = (
        "_b_lock",
        "_initial_backoff_interval",
        "_max_backoff_interval",
        "_backoff_count",
        "_expiration_time",
        "_name",
        "_detailed_debug_logging",
        "_threshold",
    )

    @typechecked
    def __init__(
        self,
        name: str,
        initial_backoff_interval: float,
        max_backoff_interval: float = ADT_MAX_BACKOFF,
        threshold: int = 0,
        debug_locks: bool = False,
        detailed_debug_logging=False,
    ) -> None:
        """Initialize backoff.

        Args:
            name (str): Name of the backoff.
            initial_backoff_interval (float): Initial backoff interval in seconds.
            max_backoff_interval (float, optional): Maximum backoff interval in seconds.
                Defaults to ADT_MAX_BACKOFF.
            threshold (int, optional): Threshold for backoff. Defaults to 0.
            debug_locks (bool, optional): Enable debug locks. Defaults to False.
            detailed_debug_logging (bool, optional): Enable detailed debug logging.
                Defaults to False.
        """
        self._check_intervals(initial_backoff_interval, max_backoff_interval)
        self._b_lock = set_debug_lock(debug_locks, "pyadtpulse._b_lock")
        self._initial_backoff_interval = initial_backoff_interval
        self._max_backoff_interval = max_backoff_interval
        self._backoff_count = 0
        self._expiration_time = 0.0
        self._name = name
        self._detailed_debug_logging = detailed_debug_logging
        self._threshold = threshold

    def _calculate_backoff_interval(self) -> float:
        """Calculate backoff time."""
        if self._backoff_count == 0:
            return 0.0
        if self._backoff_count <= (self._threshold + 1):
            return self._initial_backoff_interval
        return min(
            self._initial_backoff_interval
            * 2 ** (self._backoff_count - self._threshold - 1),
            self._max_backoff_interval,
        )

    @staticmethod
    def _check_intervals(
        initial_backoff_interval: float, max_backoff_interval: float
    ) -> None:
        """Check max_backoff_interval is >= initial_backoff_interval
        and that both invervals are positive."""
        if initial_backoff_interval <= 0:
            raise ValueError("initial_backoff_interval must be greater than 0")
        if max_backoff_interval < initial_backoff_interval:
            raise ValueError("max_backoff_interval must be >= initial_backoff_interval")

    def get_current_backoff_interval(self) -> float:
        """Return current backoff time."""
        with self._b_lock:
            return self._calculate_backoff_interval()

    def increment_backoff(self) -> None:
        """Increment backoff."""
        with self._b_lock:
            self._backoff_count += 1
            if self._detailed_debug_logging:
                LOG.debug(
                    "Pulse backoff %s: incremented to %s",
                    self._name,
                    self._backoff_count,
                )

    def reset_backoff(self) -> None:
        """Reset backoff."""
        with self._b_lock:
            if self._expiration_time < time():
                if self._detailed_debug_logging and self._backoff_count != 0:
                    LOG.debug("Pulse backoff %s reset", self._name)
                self._backoff_count = 0
                self._expiration_time = 0.0

    @typechecked
    def set_absolute_backoff_time(self, backoff_time: float) -> None:
        """Set absolute backoff time."""
        curr_time = time()
        if backoff_time < curr_time:
            raise ValueError("Absolute backoff time must be greater than current time")
        with self._b_lock:
            if self._detailed_debug_logging:
                LOG.debug(
                    "Pulse backoff %s: set to %s",
                    self._name,
                    datetime.datetime.fromtimestamp(backoff_time).strftime(
                        "%m/%d/%Y %H:%M:%S"
                    ),
                )
            self._expiration_time = backoff_time
            self._backoff_count = 0

    async def wait_for_backoff(self) -> None:
        """Wait for backoff."""
        with self._b_lock:
            curr_time = time()
            if self._expiration_time < curr_time:
                if self.backoff_count == 0:
                    return
                diff = self._calculate_backoff_interval()
            else:
                diff = self._expiration_time - curr_time
            if diff > 0:
                if self._detailed_debug_logging:
                    LOG.debug("Backoff %s: waiting for %s", self._name, diff)
                await asyncio.sleep(diff)

    def will_backoff(self) -> bool:
        """Return if backoff is needed."""
        with self._b_lock:
            return (
                self._backoff_count > self._threshold or self._expiration_time >= time()
            )

    @property
    def backoff_count(self) -> int:
        """Return backoff count."""
        with self._b_lock:
            return self._backoff_count

    @property
    def expiration_time(self) -> float:
        """Return backoff expiration time."""
        with self._b_lock:
            return self._expiration_time

    @property
    def initial_backoff_interval(self) -> float:
        """Return initial backoff interval."""
        with self._b_lock:
            return self._initial_backoff_interval

    @initial_backoff_interval.setter
    @typechecked
    def initial_backoff_interval(self, new_interval: float) -> None:
        """Set initial backoff interval."""
        with self._b_lock:
            self._check_intervals(new_interval, self._max_backoff_interval)
            self._initial_backoff_interval = new_interval

    @property
    def name(self) -> str:
        """Return name."""
        return self._name

    @property
    def detailed_debug_logging(self) -> bool:
        """Return detailed debug logging."""
        with self._b_lock:
            return self._detailed_debug_logging

    @detailed_debug_logging.setter
    @typechecked
    def detailed_debug_logging(self, new_value: bool) -> None:
        """Set detailed debug logging."""
        with self._b_lock:
            self._detailed_debug_logging = new_value
