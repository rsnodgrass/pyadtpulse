"""Base Python Class for pyadtpulse."""

import logging
import asyncio
import re
import time
from random import uniform
from threading import Lock, RLock, Thread
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

import uvloop
from aiohttp import (
    ClientConnectionError,
    ClientConnectorError,
    ClientResponse,
    ClientResponseError,
    ClientSession,
)
from bs4 import BeautifulSoup

from pyadtpulse.const import (
    ADT_DEFAULT_HTTP_HEADERS,
    ADT_DEFAULT_POLL_INTERVAL,
    ADT_DEFAULT_VERSION,
    ADT_DEVICE_URI,
    ADT_GATEWAY_OFFLINE_POLL_INTERVAL,
    ADT_HTTP_REFERER_URIS,
    ADT_LOGIN_URI,
    ADT_LOGOUT_URI,
    ADT_ORB_URI,
    ADT_SUMMARY_URI,
    ADT_SYNC_CHECK_URI,
    ADT_SYSTEM_URI,
    ADT_TIMEOUT_INTERVAL,
    ADT_TIMEOUT_URI,
    API_PREFIX,
    DEFAULT_API_HOST,
)
from pyadtpulse.util import (
    AuthenticationException,
    DebugRLock,
    handle_response,
    make_soup,
)

# FIXME -- circular reference
# from pyadtpulse.site import ADTPulseSite

if TYPE_CHECKING:
    from pyadtpulse.site import ADTPulseSite

LOG = logging.getLogger(__name__)

RECOVERABLE_ERRORS = [429, 500, 502, 503, 504]
SYNC_CHECK_TASK_NAME = "ADT Pulse Sync Check Task"
KEEPALIVE_TASK_NAME = "ADT Pulse Keepalive Task"


class PyADTPulse:
    """Base object for ADT Pulse service."""

    __slots__ = (
        "_session",
        "_user_agent",
        "_sync_task",
        "_timeout_task",
        "_authenticated",
        "_updates_exist",
        "_loop",
        "_session_thread",
        "_attribute_lock",
        "_last_timeout_reset",
        "_sync_timestamp",
        "_sites",
        "_api_host",
        "_poll_interval",
        "_username",
        "_password",
        "_fingerprint",
        "_login_exception",
        "_gateway_online",
        "_create_task_cb",
    )
    _api_version = ADT_DEFAULT_VERSION
    _class_threadlock = Lock()

    def __init__(
        self,
        username: str,
        password: str,
        fingerprint: str,
        service_host: str = DEFAULT_API_HOST,
        user_agent=ADT_DEFAULT_HTTP_HEADERS["User-Agent"],
        websession: Optional[ClientSession] = None,
        do_login: bool = True,
        poll_interval: float = ADT_DEFAULT_POLL_INTERVAL,
        debug_locks: bool = False,
        create_task_cb=asyncio.create_task,
    ):
        """Create a PyADTPulse object.

        Args:
            username (str): Username.
            password (str): Password.
            fingerprint (str): 2FA fingerprint.
            service_host (str, optional): host prefix to use
                         i.e. https://portal.adtpulse.com or
                              https://portal-ca.adtpulse.com
            user_agent (str, optional): User Agent.
                         Defaults to ADT_DEFAULT_HTTP_HEADERS["User-Agent"].
            websession (ClientSession, optional): an initialized
                        aiohttp.ClientSession to use, defaults to None
            do_login (bool, optional): login synchronously when creating object
                            Should be set to False for asynchronous usage
                            and async_login() should be called instead
                            Setting websession will override this
                            and not login
                        Defaults to True
            poll_interval (float, optional): number of seconds between update checks
            debug_locks: (bool, optional): use debugging locks
                        Defaults to False
            create_task_cb (callback, optional): callback to use to create async tasks
                        Defaults to asyncio.create_task()
        """
        self._gateway_online: bool = False

        self._session = websession
        if self._session is not None:
            self._session.headers.update(ADT_DEFAULT_HTTP_HEADERS)

        self._init_login_info(username, password, fingerprint)
        self._user_agent = user_agent

        self._sync_task: Optional[asyncio.Task] = None
        self._sync_timestamp = 0.0
        self._timeout_task: Optional[asyncio.Task] = None

        # FIXME use thread event/condition, regular condition?
        # defer initialization to make sure we have an event loop
        self._authenticated: Optional[asyncio.locks.Event] = None
        self._login_exception: Optional[BaseException] = None

        self._updates_exist: Optional[asyncio.locks.Event] = None

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._session_thread: Optional[Thread] = None
        self._attribute_lock: Union[RLock, DebugRLock]
        if not debug_locks:
            self._attribute_lock = RLock()
        else:
            self._attribute_lock = DebugRLock("PyADTPulse._attribute_lock")
        self._sync_timestamp = self._last_timeout_reset = time.time()

        # fixme circular import, should be an ADTPulseSite
        if TYPE_CHECKING:
            self._sites: List[ADTPulseSite]
        else:
            self._sites: List[Any] = []

        self._api_host = service_host
        self._poll_interval = poll_interval
        # FIXME: I have no idea how to type hint this
        self._create_task_cb = create_task_cb

        # authenticate the user
        if do_login and self._session is None:
            self.login()

    def _init_login_info(self, username: str, password: str, fingerprint: str) -> None:
        if username is None or username == "":
            raise ValueError("Username is mandatory")

        pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
        if not re.match(pattern, username):
            raise ValueError("Username must be an email address")
        self._username = username

        if password is None or password == "":
            raise ValueError("Password is mandatory")
        self._password = password

        if fingerprint is None or fingerprint == "":
            raise ValueError("Fingerprint is required")
        self._fingerprint = fingerprint

    def __del__(self) -> None:
        """Destructor.

        Closes aiohttp session if one exists
        """
        if self._session is not None and not self._session.closed:
            self._session.detach()

    def __repr__(self) -> str:
        """Object representation."""
        return "<{}: {}>".format(self.__class__.__name__, self._username)

    # ADTPulse API endpoint is configurable (besides default US ADT Pulse endpoint) to
    # support testing as well as alternative ADT Pulse endpoints such as
    # portal-ca.adtpulse.com

    @property
    def service_host(self) -> str:
        """Get the Pulse host.

        Returns: (str): the ADT Pulse endpoint host
        """
        with self._attribute_lock:
            return self._api_host

    @service_host.setter
    def service_host(self, host: str) -> None:
        """Override the Pulse host (i.e. to use portal-ca.adpulse.com).

        Args:
            host (str): name of Pulse endpoint host
        """
        with self._attribute_lock:
            self._api_host = f"https://{host}"
            if self._session is not None:
                self._session.headers.update({"Host": host})
                self._session.headers.update(ADT_DEFAULT_HTTP_HEADERS)

    def set_service_host(self, host: str) -> None:
        """Backward compatibility for service host property setter."""
        self.service_host = host

    def make_url(self, uri: str) -> str:
        """Create a URL to service host from a URI.

        Args:
            uri (str): the URI to convert

        Returns:
            str: the converted string
        """
        with self._attribute_lock:
            return f"{self._api_host}{API_PREFIX}{self.version}{uri}"

    @property
    def poll_interval(self) -> float:
        """Get polling interval.

        Returns:
            float: interval in seconds to poll for updates
        """
        with self._attribute_lock:
            return self._poll_interval

    @poll_interval.setter
    def poll_interval(self, interval: float) -> None:
        """Set polling interval.

        Args:
            interval (float): interval in seconds to poll for updates
        """
        with self._attribute_lock:
            self._poll_interval = interval

    @property
    def username(self) -> str:
        """Get username.

        Returns:
            str: the username
        """
        with self._attribute_lock:
            return self._username

    @property
    def version(self) -> str:
        """Get the ADT Pulse site version.

        Returns:
            str: a string containing the version
        """
        with PyADTPulse._class_threadlock:
            return PyADTPulse._api_version

    @property
    def gateway_online(self) -> bool:
        """Retrieve whether Pulse Gateway is online.

        Returns:
            bool: True if gateway is online
        """
        with self._attribute_lock:
            return self._gateway_online

    def _set_gateway_status(self, status: bool) -> None:
        """Set gateway status.

        Private method used by site object

        Args:
            status (bool): True if gateway is online
        """
        with self._attribute_lock:
            if status == self._gateway_online:
                return

            status_text = "ONLINE"
            if not status:
                status_text = "OFFLINE"
                self._poll_interval = ADT_GATEWAY_OFFLINE_POLL_INTERVAL

            LOG.info(
                f"ADT Pulse gateway {status_text}, poll interval={self._poll_interval}"
            )
            self._gateway_online = status

    async def _async_fetch_version(self) -> None:
        with PyADTPulse._class_threadlock:
            if PyADTPulse._api_version != ADT_DEFAULT_VERSION:
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
                    self._close_response(response)
                    return

            if response is None:
                LOG.warning(
                    "Error occurred during API version fetch, defaulting to"
                    f"{ADT_DEFAULT_VERSION}"
                )
                return

            m = re.search("/myhome/(.+)/[a-z]*/", response.real_url.path)
            self._close_response(response)
            if m is not None:
                PyADTPulse._api_version = m.group(1)
                LOG.debug(
                    "Discovered ADT Pulse version"
                    f" {PyADTPulse._api_version} at {self.service_host}"
                )
                return

            LOG.warning(
                "Couldn't auto-detect ADT Pulse version, "
                f"defaulting to {ADT_DEFAULT_VERSION}"
            )

    async def _update_sites(self, soup: BeautifulSoup) -> None:
        with self._attribute_lock:
            if len(self._sites) == 0:
                await self._initialize_sites(soup)
            else:
                # FIXME: this will have to be fixed once multiple ADT sites
                # are supported, since the summary_html only represents the
                # alarm status of the current site!!
                if len(self._sites) > 1:
                    LOG.error(
                        "pyadtpulse lacks support for ADT accounts "
                        "with multiple sites!!!"
                    )

            for site in self._sites:
                site._update_alarm_from_soup(soup)
                site._update_zone_from_soup(soup)

    async def _initialize_sites(self, soup: BeautifulSoup) -> None:
        # typically, ADT Pulse accounts have only a single site (premise/location)
        singlePremise = soup.find("span", {"id": "p_singlePremise"})
        if singlePremise:
            site_name = singlePremise.text

            # FIXME: this code works, but it doesn't pass the linter
            signout_link = str(
                soup.find("a", {"class": "p_signoutlink"}).get("href")  # type: ignore
            )
            if signout_link:
                m = re.search("networkid=(.+)&", signout_link)
                if m and m.group(1) and m.group(1):
                    from pyadtpulse.site import ADTPulseSite

                    site_id = m.group(1)
                    LOG.debug(f"Discovered site id {site_id}: {site_name}")

                    # FIXME ADTPulseSite circular reference
                    new_site = ADTPulseSite(self, site_id, site_name)

                    # fetch zones first, so that we can have the status
                    # updated with _update_alarm_status
                    await new_site._fetch_zones(None)
                    new_site._update_alarm_from_soup(soup)
                    new_site._update_zone_from_soup(soup)
                    with self._attribute_lock:
                        self._sites.append(new_site)
                    return
            else:
                LOG.warning(
                    f"Couldn't find site id for '{site_name}' in '{signout_link}'"
                )
        else:
            LOG.error("ADT Pulse accounts with MULTIPLE sites not supported!!!")

    # ...and current network id from:
    # <a id="p_signout1" class="p_signoutlink"
    # href="/myhome/16.0.0-131/access/signout.jsp?networkid=150616za043597&partner=adt"
    # onclick="return flagSignOutInProcess();">
    #
    # ... or perhaps better, just extract all from /system/settings.jsp

    def _close_response(self, response: Optional[ClientResponse]) -> None:
        if response is not None and not response.closed:
            response.close()

    async def _keepalive_task(self) -> None:
        if self._timeout_task is not None:
            task_name = self._timeout_task.get_name()
        else:
            task_name = f"{KEEPALIVE_TASK_NAME} - possible internal error"
        LOG.debug(f"creating {task_name}")
        response = None
        with self._attribute_lock:
            if self._authenticated is None:
                raise RuntimeError(
                    "Keepalive task is running without an authenticated event"
                )
        while self._authenticated.is_set():
            try:
                await asyncio.sleep(ADT_TIMEOUT_INTERVAL)
                LOG.debug("Resetting timeout")
                response = await self._async_query(ADT_TIMEOUT_URI, "POST")
                if handle_response(
                    response, logging.INFO, "Failed resetting ADT Pulse cloud timeout"
                ):
                    self._close_response(response)
                    continue
                self._close_response(response)
            except asyncio.CancelledError:
                LOG.debug(f"{task_name} cancelled")
                self._close_response(response)
                return

    def _pulse_session_thread(self) -> None:
        # lock is released in sync_loop()
        self._attribute_lock.acquire()

        LOG.debug("Creating ADT Pulse background thread")
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        self._loop = asyncio.new_event_loop()
        self._loop.run_until_complete(self._sync_loop())

        self._loop.close()
        self._loop = None
        self._session_thread = None

    async def _sync_loop(self) -> None:
        result = await self.async_login()
        self._attribute_lock.release()
        if result:
            if self._timeout_task is not None:
                task_list = (self._timeout_task,)
                try:
                    await asyncio.wait(task_list)
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    LOG.exception(
                        f"Received exception while waiting for ADT Pulse service {e}"
                    )
            else:
                # we should never get here
                raise RuntimeError("Background pyadtpulse tasks not created")
        if self._authenticated is not None:
            while self._authenticated.is_set():
                # busy wait until logout is done
                await asyncio.sleep(0.5)

    def login(self) -> None:
        """Login to ADT Pulse and generate access token.

        Raises:
            AuthenticationException if could not login
        """
        self._attribute_lock.acquire()
        # probably shouldn't be a daemon thread
        self._session_thread = thread = Thread(
            target=self._pulse_session_thread,
            name="PyADTPulse Session",
            daemon=True,
        )
        self._attribute_lock.release()

        self._session_thread.start()
        time.sleep(1)

        # thread will unlock after async_login, so attempt to obtain
        # lock to block current thread until then
        # if it's still alive, no exception
        self._attribute_lock.acquire()
        self._attribute_lock.release()
        if not thread.is_alive():
            raise AuthenticationException(self._username)

    @property
    def attribute_lock(self) -> Union[RLock, DebugRLock]:
        """Get attribute lock for PyADTPulse object.

        Returns:
            RLock: thread Rlock
        """
        return self._attribute_lock

    @property
    def loop(self) -> Optional[asyncio.AbstractEventLoop]:
        """Get event loop.

        Returns:
            Optional[asyncio.AbstractEventLoop]: the event loop object or
                                                 None if no thread is running
        """
        with self._attribute_lock:
            return self._loop

    async def async_login(self) -> bool:
        """Login asynchronously to ADT.

        Returns: True if login successful
        """
        if self._session is None:
            self._session = ClientSession()
        self._session.headers.update(ADT_DEFAULT_HTTP_HEADERS)
        if self._authenticated is None:
            self._authenticated = asyncio.locks.Event()
        else:
            self._authenticated.clear()

        LOG.debug(f"Authenticating to ADT Pulse cloud service as {self._username}")
        await self._async_fetch_version()

        response = await self._async_query(
            ADT_LOGIN_URI,
            method="POST",
            extra_params={
                "partner": "adt",
                "usernameForm": self.username,
                "passwordForm": self._password,
                "fingerprint": self._fingerprint,
                "sun": "yes",
            },
            force_login=False,
            timeout=30,
        )

        if not handle_response(
            response,
            logging.ERROR,
            "Error encountered communicating with Pulse site on login",
        ):
            self._close_response(response)
            return False
        if str(response.url) != self.make_url(ADT_SUMMARY_URI):  # type: ignore
            # more specifically:
            # redirect to signin.jsp = username/password error
            # redirect to mfaSignin.jsp = fingerprint error
            LOG.error("Authentication error encountered logging into ADT Pulse")
            self._close_response(response)
            return False

        soup = await make_soup(
            response, logging.ERROR, "Could not log into ADT Pulse site"
        )
        if soup is None:
            return False

        # FIXME: should probably raise exceptions
        error = soup.find("div", {"id": "warnMsgContents"})
        if error:
            LOG.error(f"Invalid ADT Pulse username/password: {error}")
            return False
        error = soup.find("div", "responsiveContainer")
        if error:
            LOG.error(
                f"2FA authentiation required for ADT pulse username {self.username} "
                f"{error}"
            )
            return False
        # need to set authenticated here to prevent login loop
        self._authenticated.set()
        await self._update_sites(soup)
        if len(self._sites) == 0:
            LOG.error("Could not retrieve any sites, login failed")
            self._authenticated.clear()
            return False
        self._last_timeout_reset = time.time()

        # since we received fresh data on the status of the alarm, go ahead
        # and update the sites with the alarm status.

        self._sync_timestamp = time.time()
        if self._timeout_task is None:
            self._timeout_task = self._create_task_cb(
                self._keepalive_task(), name=f"{KEEPALIVE_TASK_NAME}"
            )
        if self._updates_exist is None:
            self._updates_exist = asyncio.locks.Event()
        await asyncio.sleep(0)
        return True

    async def async_logout(self) -> None:
        """Logout of ADT Pulse async."""
        LOG.info(f"Logging {self._username} out of ADT Pulse")
        if self._timeout_task is not None:
            try:
                self._timeout_task.cancel()
            except asyncio.CancelledError:
                LOG.debug(f"{KEEPALIVE_TASK_NAME} successfully cancelled")
                await self._timeout_task
        if self._sync_task is not None:
            try:
                self._sync_task.cancel()
            except asyncio.CancelledError:
                LOG.debug(f"{SYNC_CHECK_TASK_NAME} successfully cancelled")
                await self._sync_task
        self._timeout_task = self._sync_task = None
        await self._async_query(ADT_LOGOUT_URI, timeout=10)
        self._last_timeout_reset = time.time()
        if self._authenticated is not None:
            self._authenticated.clear()

    def logout(self) -> None:
        """Log out of ADT Pulse."""
        with self._attribute_lock:
            if self._loop is None:
                raise RuntimeError("Attempting to call sync logout without sync login")
            sync_thread = self._session_thread

        coro = self.async_logout()
        asyncio.run_coroutine_threadsafe(coro, self._loop)
        if sync_thread is not None:
            sync_thread.join()

    async def _sync_check_task(self) -> None:
        # this should never be true
        if self._sync_task is not None:
            task_name = self._sync_task.get_name()
        else:
            task_name = f"{SYNC_CHECK_TASK_NAME} - possible internal error"

        LOG.debug(f"creating {task_name}")
        response = None
        if self._updates_exist is None:
            raise RuntimeError(
                "Sync check task started without update event initialized"
            )
        while True:
            try:
                if self.gateway_online:
                    pi = self.poll_interval
                else:
                    LOG.info(
                        "Pulse gateway detected offline, polling every "
                        f"{ADT_GATEWAY_OFFLINE_POLL_INTERVAL} seconds"
                    )
                    pi = ADT_GATEWAY_OFFLINE_POLL_INTERVAL

                await asyncio.sleep(pi)
                response = await self._async_query(
                    ADT_SYNC_CHECK_URI,
                    extra_params={"ts": int(self._sync_timestamp * 1000)},
                )

                if response is None:
                    continue

                text = await response.text()
                if not handle_response(
                    response, logging.ERROR, "Error querying ADT sync"
                ):
                    self._close_response(response)
                    continue

                pattern = r"\d+[-]\d+[-]\d+"
                if not re.match(pattern, text):
                    LOG.warn(
                        f"Unexpected sync check format ({pattern}), forcing re-auth"
                    )
                    LOG.debug(f"Received {text} from ADT Pulse site")
                    self._close_response(response)
                    await self.async_login()
                    continue

                # we can have 0-0-0 followed by 1-0-0 followed by 2-0-0, etc
                # wait until these settle
                if text.endswith("-0-0"):
                    LOG.debug(
                        f"Sync token {text} indicates updates may exist, requerying"
                    )
                    self._close_response(response)
                    self._sync_timestamp = time.time()
                    self._updates_exist.set()
                    if await self.async_update() is False:
                        LOG.debug("Pulse data update from sync task failed")
                    continue

                LOG.debug(f"Sync token {text} indicates no remote updates to process")
                self._close_response(response)
                self._sync_timestamp = time.time()

            except asyncio.CancelledError:
                LOG.debug(f"{task_name} cancelled")
                self._close_response(response)
                return

    @property
    def updates_exist(self) -> bool:
        """Check if updated data exists.

        Returns:
            bool: True if updated data exists
        """
        with self._attribute_lock:
            if self._sync_task is None:
                if self._loop is None:
                    raise RuntimeError(
                        "ADT pulse sync function updates_exist() "
                        "called from async session"
                    )
                coro = self._sync_check_task()
                self._sync_task = self._loop.create_task(
                    coro, name=f"{SYNC_CHECK_TASK_NAME}: Sync session"
                )
            if self._updates_exist is None:
                return False

            if self._updates_exist.is_set():
                self._updates_exist.clear()
                return True
            return False

    async def wait_for_update(self) -> None:
        """Wait for update.

        Blocks current async task until Pulse system
        signals an update
        """
        with self._attribute_lock:
            if self._sync_task is None:
                coro = self._sync_check_task()
                self._sync_task = self._create_task_cb(
                    coro, name=f"{SYNC_CHECK_TASK_NAME}: Async session"
                )
        if self._updates_exist is None:
            raise RuntimeError("Update event does not exist")

        await self._updates_exist.wait()
        self._updates_exist.clear()

    @property
    def is_connected(self) -> bool:
        """Check if connected to ADT Pulse.

        Returns:
            bool: True if connected
        """
        with self._attribute_lock:
            if self._authenticated is None:
                return False
            return self._authenticated.is_set()

    async def _async_query(
        self,
        uri: str,
        method: str = "GET",
        extra_params: Optional[Dict] = None,
        extra_headers: Optional[Dict] = None,
        force_login: Optional[bool] = True,
        timeout=1,
    ) -> Optional[ClientResponse]:
        """Query ADT Pulse async.

        Args:
            uri (str): URI to query
            method (str, optional): method to use. Defaults to "GET".
            extra_params (Optional[Dict], optional): query parameters. Defaults to None.
            extra_headers (Optional[Dict], optional): extra HTTP headers.
                        Defaults to None.
            force_login (Optional[bool], optional): login if not connected.
                        Defaults to True.
            timeout (int, optional): timeout in seconds. Defaults to 1.

        Returns:
            Optional[ClientResponse]: aiohttp.ClientResponse object
                                      None on failure
                                      ClientResponse will already be closed.
        """
        response = None

        # automatically attempt to login, if not connected
        if force_login and not self.is_connected:
            await self.async_login()

        if self._session is None:
            raise RuntimeError("ClientSession not initialized")
        url = self.make_url(uri)
        if uri in ADT_HTTP_REFERER_URIS:
            new_headers = {"Accept": ADT_DEFAULT_HTTP_HEADERS["Accept"]}
        else:
            new_headers = {"Accept": "*/*"}

        LOG.debug(f"Updating HTTP headers: {new_headers}")
        self._session.headers.update(new_headers)

        LOG.debug(f"Attempting {method} {url}")

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
                    LOG.warning(
                        f"pyadtpulse query returned recover error code "
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
                LOG.warning(
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
        extra_params: Optional[Dict] = None,
        extra_headers: Optional[Dict] = None,
        force_login: Optional[bool] = True,
        timeout=1,
    ) -> Optional[ClientResponse]:
        """Query ADT Pulse async.

        Args:
            uri (str): URI to query
            method (str, optional): method to use. Defaults to "GET".
            extra_params (Optional[Dict], optional): query parameters. Defaults to None.
            extra_headers (Optional[Dict], optional): extra HTTP headers.
                                                    Defaults to None.
            force_login (Optional[bool], optional): login if not connected.
                                                    Defaults to True.
            timeout (int, optional): timeout in seconds. Defaults to 1.
        Returns:
            Optional[ClientResponse]: aiohttp.ClientResponse object
                                      None on failure
                                      ClientResponse will already be closed.
        """
        if self._loop is None:
            raise RuntimeError("Attempting to run sync query from async login")
        coro = self._async_query(
            uri, method, extra_params, extra_headers, force_login, timeout
        )
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

    # FIXME? might have to move this to site for multiple sites
    async def _query_orb(
        self, level: int, error_message: str
    ) -> Optional[BeautifulSoup]:
        response = await self._async_query(ADT_ORB_URI)

        return await make_soup(response, level, error_message)

    async def async_update(self) -> bool:
        """Update ADT Pulse data.

        Returns:
            bool: True if update succeeded.
        """
        LOG.debug("Checking ADT Pulse cloud service for updates")

        # FIXME will have to query other URIs for camera/zwave/etc
        soup = await self._query_orb(
            logging.INFO, "Error returned from ADT Pulse service check"
        )
        if soup is not None:
            await self._update_sites(soup)
            return True

        return False

    def update(self) -> bool:
        """Update ADT Pulse data.

        Returns:
            bool: True on success
        """
        if self._loop is None:
            raise RuntimeError("Attempting to run sync update from async login")
        coro = self.async_update()
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

    # FIXME circular reference, should be ADTPulseSite

    @property
    def sites(self) -> List[Any]:
        """Return all sites for this ADT Pulse account."""
        with self._attribute_lock:
            return self._sites
