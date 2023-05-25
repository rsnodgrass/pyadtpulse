"""ADT Pulse connection."""

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
    LOG,
)
from .util import DebugRLock, close_response, make_soup

RECOVERABLE_ERRORS = [429, 500, 502, 503, 504]


class ADTPulseConnection:
    """ADT Pulse connection related attributes."""

    _api_version = ADT_DEFAULT_VERSION
    _class_threadlock = Lock()

    def __init__(
        self,
        host: str,
        version: str,
        session: Optional[ClientSession] = None,
        user_agent: str = ADT_DEFAULT_HTTP_HEADERS["User-Agent"],
        debug_locks: bool = False,
    ):
        """Initialize ADT Pulse connection."""
        self._api_host = host
        self._version = version
        self._allocated_session = False
        if session is None:
            self._allocate_session = True
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

    async def _async_query(
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
        if self._session is None:
            raise RuntimeError("ClientSession not initialized")
        url = self.make_url(uri)
        if uri in ADT_HTTP_REFERER_URIS:
            new_headers = {"Accept": ADT_DEFAULT_HTTP_HEADERS["Accept"]}
        else:
            new_headers = {"Accept": "*/*"}

        LOG.debug(f"Updating HTTP headers: {new_headers}")
        self._session.headers.update(new_headers)

        LOG.debug(f"Attempting {method} {url} params={extra_params} timeout={timeout}")

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
                    LOG.error(f"Invalid request method {method}")
                    return None

                if response.status in RECOVERABLE_ERRORS:
                    retry = retry + 1
                    LOG.info(
                        f"pyadtpulse query returned recoverable error code "
                        f"{response.status}, retrying (count ={retry})"
                    )
                    if retry == max_retries:
                        LOG.warning(
                            "pyadtpulse exceeded max retries of "
                            f"{max_retries}, giving up"
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
                LOG.info(
                    f"Error {ex} occurred making {method} request to {url}, retrying"
                )
                await asyncio.sleep(2**retry + uniform(0.0, 1.0))
                continue
            except ClientResponseError as err:
                code = err.code
                LOG.exception(
                    f"Received HTTP error code {code} in request to ADT Pulse"
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
                    LOG.debug(f"Setting Referer to: {referer}")
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
        coro = self._async_query(uri, method, extra_params, extra_headers, timeout)
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

    async def _query_orb(
        self, level: int, error_message: str
    ) -> Optional[BeautifulSoup]:
        response = await self._async_query(ADT_ORB_URI)

        return await make_soup(response, level, error_message)

    def make_url(self, uri: str) -> str:
        """Create a URL to service host from a URI.

        Args:
            uri (str): the URI to convert

        Returns:
            str: the converted string
        """
        with self._attribute_lock:
            return f"{self._api_host}{API_PREFIX}{self._version}{uri}"

    async def _async_fetch_version(self) -> None:
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
                        "Error occurred during API version fetch, defaulting to"
                        f"{ADT_DEFAULT_VERSION}"
                    )
                    close_response(response)
                    return

            if response is None:
                LOG.warning(
                    "Error occurred during API version fetch, defaulting to"
                    f"{ADT_DEFAULT_VERSION}"
                )
                return

            m = re.search("/myhome/(.+)/[a-z]*/", response.real_url.path)
            close_response(response)
            if m is not None:
                ADTPulseConnection._api_version = m.group(1)
                LOG.debug(
                    "Discovered ADT Pulse version"
                    f" {ADTPulseConnection._api_version} at {self.service_host}"
                )
                return

            LOG.warning(
                "Couldn't auto-detect ADT Pulse version, "
                f"defaulting to {ADT_DEFAULT_VERSION}"
            )
