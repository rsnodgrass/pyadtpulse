"""Utility functions for pyadtpulse."""
from typing import Optional

from aiohttp import ClientResponse
from bs4 import BeautifulSoup
import logging

LOG = logging.getLogger(__name__)


async def handle_response(
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
        LOG.log(level, f"{error_message}")
        return False

    if response.ok:
        return True

    LOG.log(level, f"{error_message}: error code={response.status}")

    return False


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
    if not await handle_response(response, level, error_message):
        return None

    if response is None:  # shut up type checker
        return None
    body_text = await response.text()
    response.close()
    return BeautifulSoup(body_text, "html.parser")
