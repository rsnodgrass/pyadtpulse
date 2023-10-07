"""Utility functions for pyadtpulse."""
import logging
import string
import sys
from base64 import urlsafe_b64encode
from datetime import datetime, timedelta
from pathlib import Path
from random import randint
from threading import RLock, current_thread
from typing import Optional

from aiohttp import ClientResponse
from bs4 import BeautifulSoup

LOG = logging.getLogger(__name__)


def handle_response(
    response: Optional[ClientResponse], level: int, error_message: str
) -> bool:
    """Handle the response from query().

    Args:
        response (Optional[Response]): the response from the query()
        level (int): Level to log on error (i.e. INFO, DEBUG)
        error_message (str): the error message

    Returns:
        bool: True if no error occurred.
    """
    if response is None:
        LOG.log(level, "%s", error_message)
        return False

    if response.ok:
        return True

    LOG.log(level, "%s: error code = %s", error_message, response.status)

    return False


def close_response(response: Optional[ClientResponse]) -> None:
    """Close a response object, handles None.

    Args:
        response (Optional[ClientResponse]): ClientResponse object to close
    """
    if response is not None and not response.closed:
        response.close()


def remove_prefix(text: str, prefix: str) -> str:
    """Remove prefix from a string.

    Args:
        text (str): original text
        prefix (str): prefix to remove

    Returns:
        str: modified string
    """
    return text[text.startswith(prefix) and len(prefix) :]


async def make_soup(
    response: Optional[ClientResponse], level: int, error_message: str
) -> Optional[BeautifulSoup]:
    """Make a BS object from a Response.

    Args:
        response (Optional[Response]): the response
        level (int): the logging level on error
        error_message (str): the error message

    Returns:
        Optional[BeautifulSoup]: a BS object, or None on failure
    """
    if not handle_response(response, level, error_message):
        return None

    if response is None:  # shut up type checker
        return None
    body_text = await response.text()
    response.close()
    return BeautifulSoup(body_text, "html.parser")


FINGERPRINT_LENGTH = 2292
ALLOWABLE_CHARACTERS = list(string.ascii_letters + string.digits)
FINGERPRINT_RANGE_LEN = len(ALLOWABLE_CHARACTERS)


def generate_random_fingerprint() -> str:
    """Generate a random browser fingerprint string.

    Returns:
        str: a fingerprint string
    """
    fingerprint = [
        ALLOWABLE_CHARACTERS[(randint(0, FINGERPRINT_RANGE_LEN - 1))]
        for i in range(FINGERPRINT_LENGTH)
    ]
    return "".join(fingerprint)


def generate_fingerprint_from_browser_json(filename: str) -> str:
    """Generate a browser fingerprint from a JSON file.

    Args:
        filename (str): JSON file containing fingerprint information

    Returns:
        str: the fingerprint
    """
    data = Path(filename).read_text(encoding="utf-8")
    # Pulse just calls JSON.Stringify() and btoa() in javascript, so we need to
    # do this to emulate that
    data2 = "".join(data.split())
    return str(urlsafe_b64encode(data2.encode("utf-8")), "utf-8")


class DebugRLock:
    """Provides a debug lock logging caller who acquired/released."""

    def __init__(self, name: str):
        """Create the lock."""
        self._Rlock = RLock()
        self._lock_name = name

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        """Acquire the lock.

        Args:
            blocking (bool, optional): blocks if can't obtain the lock if True.
                                       Defaults to True.
            timeout (float, optional): timeout to wait to acquire the lock.
                                       Defaults to -1.

        Returns:
            bool: True if lock obtained, False if blocking is False and lock couldn't be
                  obtained
        """
        caller = sys._getframe().f_back
        thread_name = current_thread().name
        if caller is not None:
            caller2 = caller.f_code.co_name
        else:
            caller2 = "*Unknown*"
        LOG.debug(
            "acquiring lock %s blocking: %s from %s from thread %s",
            self._lock_name,
            blocking,
            caller2,
            thread_name,
        )
        retval = self._Rlock.acquire(blocking, timeout)
        LOG.debug(
            "acquisition of %s from %s from thread %s  returned %d info: %s",
            self._lock_name,
            caller2,
            thread_name,
            retval,
            repr(self._Rlock),
        )
        return retval

    __enter__ = acquire

    def release(self) -> None:
        """Releases the lock."""
        caller = sys._getframe().f_back
        if caller is not None:
            caller2 = caller.f_code.co_name
        else:
            caller2 = "*Unknown*"
        thread_name = current_thread().name
        LOG.debug(
            "attempting to release lock %s from %s in thread %s",
            self._lock_name,
            caller2,
            thread_name,
        )
        self._Rlock.release()
        LOG.debug(
            "released lock %s from %s in thread %s info: %s",
            self._lock_name,
            caller2,
            thread_name,
            repr(self._Rlock),
        )

    def __exit__(self, t, v, b):
        """Automatically release lock on exit.

        Args:
            t (_type_): _description_
            v (_type_): _description_
            b (_type_): _description_
        """
        caller = sys._getframe().f_back
        if caller is not None:
            caller2 = caller.f_code.co_name
        else:
            caller2 = "*Unknown*"
        thread_name = current_thread().name
        LOG.debug(
            "released lock %s from %s in thread %s at exit",
            self._lock_name,
            caller2,
            thread_name,
        )

        self._Rlock.release()


def parse_pulse_datetime(datestring: str) -> datetime:
    """Parse pulse date strings.

    Args:
        datestring (str): the string to parse

    Raises:
        ValueError: pass through of value error if string
                    cannot be converted

    Returns:
        datetime: time value of given string
    """
    split_string = datestring.split("\xa0")
    if len(split_string) < 3:
        raise ValueError("Invalid datestring")
    t = datetime.today()
    if split_string[0].lstrip() == "Today":
        last_update = t
    elif split_string[0].lstrip() == "Yesterday":
        last_update = t - timedelta(days=1)
    else:
        tempdate = f"{split_string[0]}/{t.year}"
        last_update = datetime.strptime(tempdate, "%m/%d/%Y")
    if last_update > t:
        last_update = last_update.replace(year=t.year)
    update_time = datetime.time(
        datetime.strptime(split_string[1] + split_string[2], "%I:%M%p")
    )
    last_update = datetime.combine(last_update, update_time)
    return last_update


class AuthenticationException(RuntimeError):
    """Raised when a login failed."""

    def __init__(self, username: str):
        """Create the exception.

        Args:
            username (str): Username used to login
        """
        super().__init__(f"Could not log into ADT site with username {username}")
