"""Utility functions for pyadtpulse."""
from typing import Optional

from requests import Response

import logging

LOG = logging.getLogger(__name__)


def handle_response(
    response: Optional[Response], level: int, error_message: str
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

    LOG.log(level, f"{error_message}: error code={response.status_code}")
    if response.text is not None:
        LOG.debug(f"ADT Pulse error additional info: {response.text}")

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
