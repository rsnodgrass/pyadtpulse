from typing import Optional

from requests import Response

from pyadtpulse import LOG


def handle_response(
    response: Optional[Response], level: int, error_message: str
) -> bool:
    """Convenience method to check query()'s response
     and log an error if necessary.
    response.ok will be appended to the end of the error message

    returns true if operation succeeded"""

    if response is None:
        LOG.log(level, f"{error_message}")
        return False

    if not response.ok:
        LOG.log(level, f"{error_message}: error code={response.status_code}")
        if response.text is not None:
            LOG.debug(f"ADT Pulse error additional info: {response.text}")
        return False

    return True


def remove_prefix(text: str, prefix: str) -> str:
    return text[text.startswith(prefix) and len(prefix) :]
