"""ADT Pulse connection. End users should probably not call this directly."""

import logging
import asyncio
import re
from random import uniform
from threading import Lock, RLock
from typing import Dict, Optional, Union

from aiohttp import (
    ClientConnectionError,
    ClientConnectorError,
    ClientResponse,
    ClientResponseError,
    ClientSession,
)
from bs4 import BeautifulSoup

from .const import (
    ADT_DEFAULT_HTTP_HEADERS,
    ADT_DEFAULT_VERSION,
    ADT_DEVICE_URI,
    ADT_HTTP_REFERER_URIS,
    ADT_LOGIN_URI,
    ADT_ORB_URI,
    ADT_SYSTEM_URI,
    API_PREFIX,
)
from .util import DebugRLock, close_response, make_soup

RECOVERABLE_ERRORS = [429, 500, 502, 503, 504]
LOG = logging.getLogger(__name__)


class ADTPulseConnection:
    """ADT Pulse connection related attributes."""

    _api_version = ADT_DEFAULT_VERSION
    _class_threadlock = Lock()

    __slots__ = (
        "_api_host",
        "_allocated_session",
        "_session",
        "_attribute_lock",
        "_loop",
    )

    def __init__(
        self,
        host: str,
        session: Optional[ClientSession] = None,
        user_agent: str = ADT_DEFAULT_HTTP_HEADERS["User-Agent"],
        debug_locks: bool = False,
    ):
        """Initialize ADT Pulse connection."""
        self._api_host = host
        self._allocated_session = False
        if session is None:
            self._allocated_session = True
            self._session = ClientSession()
        else:
            self._session = session
        self._session.headers.update({"User-Agent": user_agent})
        self._attribute_lock: Union[RLock, DebugRLock]
        if not debug_locks:
            self._attribute_lock = RLock()
        else:
            self._attribute_lock = DebugRLock("ADTPulseConnection._attribute_lock")
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def __del__(self):
        """Destructor for ADTPulseConnection."""
        if self._allocated_session and self._session is not None:
            self._session.detach()

    @property
    def api_version(self) -> str:
        """Get the API version."""
        with self._class_threadlock:
            return self._api_version

    @property
    def service_host(self) -> str:
        """Get the host prefix for connections."""
        with self._attribute_lock:
            return self._api_host

    @service_host.setter
    def service_host(self, host: str) -> None:
        """Set the host prefix for connections."""
        with self._attribute_lock:
            self._session.headers.update({"Host": host})
            self._api_host = host

    @property
    def loop(self) -> Optional[asyncio.AbstractEventLoop]:
        """Get the event loop."""
        with self._attribute_lock:
            return self._loop

    @loop.setter
    def loop(self, loop: Optional[asyncio.AbstractEventLoop]) -> None:
        """Set the event loop."""
        with self._attribute_lock:
            self._loop = loop

    async def async_query(
        self,
        uri: str,
        method: str = "GET",
        extra_params: Optional[Dict[str, str]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
        timeout=1,
    ) -> Optional[ClientResponse]:
        """Query ADT Pulse async.

        Args:
            uri (str): URI to query
            method (str, optional): method to use. Defaults to "GET".
            extra_params (Optional[Dict], optional): query parameters. Defaults to None.
            extra_headers (Optional[Dict], optional): extra HTTP headers.
                        Defaults to None.
            timeout (int, optional): timeout in seconds. Defaults to 1.

        Returns:
            Optional[ClientResponse]: aiohttp.ClientResponse object
                                      None on failure
                                      ClientResponse will already be closed.
        """
        response = None
        with ADTPulseConnection._class_threadlock:
            if ADTPulseConnection._api_version == ADT_DEFAULT_VERSION:
                await self.async_fetch_version()
        url = self.make_url(uri)
        if uri in ADT_HTTP_REFERER_URIS:
            new_headers = {"Accept": ADT_DEFAULT_HTTP_HEADERS["Accept"]}
        else:
            new_headers = {"Accept": "*/*"}

        LOG.debug("Updating HTTP headers: %s", new_headers)
        self._session.headers.update(new_headers)

        LOG.debug(
            "Attempting %s %s params=%s timeout=%d", method, uri, extra_params, timeout
        )

        # FIXME: reauthenticate if received:
        # "You have not yet signed in or you
        #  have been signed out due to inactivity."

        # define connection method
        retry = 0
        max_retries = 3
        while retry < max_retries:
            try:
                if method == "GET":
                    async with self._session.get(
                        url, headers=extra_headers, params=extra_params, timeout=timeout
                    ) as response:
                        await response.text()
                elif method == "POST":
                    async with self._session.post(
                        url, headers=extra_headers, data=extra_params, timeout=timeout
                    ) as response:
                        await response.text()
                else:
                    LOG.error("Invalid request method %s", method)
                    return None

                if response.status in RECOVERABLE_ERRORS:
                    retry = retry + 1
                    LOG.info(
                        "query returned recoverable error code %s, "
                        "retrying (count = %d)",
                        response.status,
                        retry,
                    )
                    if retry == max_retries:
                        LOG.warning(
                            "Exceeded max retries of %d, giving up", max_retries
                        )
                        response.raise_for_status()
                    await asyncio.sleep(2**retry + uniform(0.0, 1.0))
                    continue

                response.raise_for_status()
                # success, break loop
                retry = 4
            except (
                asyncio.TimeoutError,
                ClientConnectionError,
                ClientConnectorError,
            ) as ex:
                LOG.debug(
                    "Error %s occurred making %s request to %s, retrying",
                    ex.args,
                    method,
                    url,
                    exc_info=True,
                )
                await asyncio.sleep(2**retry + uniform(0.0, 1.0))
                continue
            except ClientResponseError as err:
                code = err.code
                LOG.exception(
                    "Received HTTP error code %i in request to ADT Pulse", code
                )
                return None

        # success!
        # FIXME? login uses redirects so final url is wrong
        if uri in ADT_HTTP_REFERER_URIS:
            if uri == ADT_DEVICE_URI:
                referer = self.make_url(ADT_SYSTEM_URI)
            else:
                if response is not None and response.url is not None:
                    referer = str(response.url)
                    LOG.debug("Setting Referer to: %s", referer)
                    self._session.headers.update({"Referer": referer})

        return response

    def query(
        self,
        uri: str,
        method: str = "GET",
        extra_params: Optional[Dict[str, str]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
        timeout=1,
    ) -> Optional[ClientResponse]:
        """Query ADT Pulse async.

        Args:
            uri (str): URI to query
            method (str, optional): method to use. Defaults to "GET".
            extra_params (Optional[Dict], optional): query parameters. Defaults to None.
            extra_headers (Optional[Dict], optional): extra HTTP headers.
                                                    Defaults to None.
            timeout (int, optional): timeout in seconds. Defaults to 1.
        Returns:
            Optional[ClientResponse]: aiohttp.ClientResponse object
                                      None on failure
                                      ClientResponse will already be closed.
        """
        if self._loop is None:
            raise RuntimeError("Attempting to run sync query from async login")
        coro = self.async_query(uri, method, extra_params, extra_headers, timeout)
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

    async def query_orb(
        self, level: int, error_message: str
    ) -> Optional[BeautifulSoup]:
        """Query ADT Pulse ORB.

        Args:
            level (int): error level to log on failure
            error_message (str): error message to use on failure

        Returns:
            Optional[BeautifulSoup]: A Beautiful Soup object, or None if failure
        """
        response = await self.async_query(ADT_ORB_URI)

        return await make_soup(response, level, error_message)

    def make_url(self, uri: str) -> str:
        """Create a URL to service host from a URI.

        Args:
            uri (str): the URI to convert

        Returns:
            str: the converted string
        """
        with self._attribute_lock:
            return f"{self._api_host}{API_PREFIX}{ADTPulseConnection._api_version}{uri}"

    async def async_fetch_version(self) -> None:
        """Fetch ADT Pulse version."""
        with ADTPulseConnection._class_threadlock:
            if ADTPulseConnection._api_version != ADT_DEFAULT_VERSION:
                return
            response = None
            signin_url = f"{self.service_host}/myhome{ADT_LOGIN_URI}"
            if self._session:
                try:
                    async with self._session.get(signin_url) as response:
                        # we only need the headers here, don't parse response
                        response.raise_for_status()
                except (ClientResponseError, ClientConnectionError):
                    LOG.warning(
                        "Error occurred during API version fetch, defaulting to %s",
                        ADT_DEFAULT_VERSION,
                    )
                    close_response(response)
                    return

            if response is None:
                LOG.warning(
                    "Error occurred during API version fetch, defaulting to %s",
                    ADT_DEFAULT_VERSION,
                )
                return

            m = re.search("/myhome/(.+)/[a-z]*/", response.real_url.path)
            close_response(response)
            if m is not None:
                ADTPulseConnection._api_version = m.group(1)
                LOG.debug(
                    "Discovered ADT Pulse version %s at %s",
                    ADTPulseConnection._api_version,
                    self.service_host,
                )
                return

            LOG.warning(
                "Couldn't auto-detect ADT Pulse version, defaulting to %s",
                ADT_DEFAULT_VERSION,
            )
