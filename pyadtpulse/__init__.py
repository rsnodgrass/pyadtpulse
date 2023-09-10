"""Base Python Class for pyadtpulse."""

import logging
import asyncio
import datetime
import re
import time
from contextlib import suppress
from threading import RLock, Thread
from typing import List, Optional, Union
from warnings import warn

import uvloop
from aiohttp import ClientResponse, ClientSession
from bs4 import BeautifulSoup

from .alarm_panel import ADT_ALARM_UNKNOWN
from .const import (
    ADT_DEFAULT_HTTP_HEADERS,
    ADT_DEFAULT_POLL_INTERVAL,
    ADT_GATEWAY_STRING,
    ADT_LOGIN_URI,
    ADT_LOGOUT_URI,
    ADT_RELOGIN_INTERVAL,
    ADT_SUMMARY_URI,
    ADT_SYNC_CHECK_URI,
    ADT_TIMEOUT_INTERVAL,
    ADT_TIMEOUT_URI,
    DEFAULT_API_HOST,
)
from .pulse_connection import ADTPulseConnection
from .site import ADTPulseSite
from .util import (
    AuthenticationException,
    DebugRLock,
    close_response,
    handle_response,
    make_soup,
)

LOG = logging.getLogger(__name__)

SYNC_CHECK_TASK_NAME = "ADT Pulse Sync Check Task"
KEEPALIVE_TASK_NAME = "ADT Pulse Keepalive Task"


class PyADTPulse:
    """Base object for ADT Pulse service."""

    __slots__ = (
        "_pulse_connection",
        "_sync_task",
        "_timeout_task",
        "_authenticated",
        "_updates_exist",
        "_session_thread",
        "_attribute_lock",
        "_last_login_time",
        "_site",
        "_poll_interval",
        "_username",
        "_password",
        "_fingerprint",
        "_login_exception",
        "_relogin_interval",
    )

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
        """
        self._init_login_info(username, password, fingerprint)
        self._pulse_connection = ADTPulseConnection(
            service_host,
            session=websession,
            user_agent=user_agent,
            debug_locks=debug_locks,
        )

        self._sync_task: Optional[asyncio.Task] = None
        self._timeout_task: Optional[asyncio.Task] = None

        # FIXME use thread event/condition, regular condition?
        # defer initialization to make sure we have an event loop
        self._authenticated: Optional[asyncio.locks.Event] = None
        self._login_exception: Optional[BaseException] = None

        self._updates_exist: Optional[asyncio.locks.Event] = None

        self._session_thread: Optional[Thread] = None
        self._attribute_lock: Union[RLock, DebugRLock]
        if not debug_locks:
            self._attribute_lock = RLock()
        else:
            self._attribute_lock = DebugRLock("PyADTPulse._attribute_lock")
        self._last_login_time = 0.0

        self._site: Optional[ADTPulseSite] = None
        self._poll_interval = poll_interval
        self._relogin_interval: int = ADT_RELOGIN_INTERVAL

        # authenticate the user
        if do_login and websession is None:
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
        return self._pulse_connection.service_host

    @service_host.setter
    def service_host(self, host: str) -> None:
        """Override the Pulse host (i.e. to use portal-ca.adpulse.com).

        Args:
            host (str): name of Pulse endpoint host
        """
        self._pulse_connection.service_host = host

    def set_service_host(self, host: str) -> None:
        """Backward compatibility for service host property setter."""
        self.service_host = host

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
        with ADTPulseConnection._class_threadlock:
            return ADTPulseConnection._api_version

    @property
    def relogin_interval(self) -> int:
        """Get re-login interval.

        Returns:
            int: number of minutes to re-login to Pulse
                 0 means disabled
        """
        with self._attribute_lock:
            return self._relogin_interval

    @relogin_interval.setter
    def relogin_interval(self, interval: int) -> None:
        """Set re-login interval.

        Args:
            interval (int): The number of minutes between logins.
                            0 means disable

        Raises:
            ValueError: if a relogin interval of less than 10 minutes
                        is specified
        """
        if interval > 0 and interval < 10:
            raise ValueError("Cannot set relogin interval to less than 10 minutes")
        with self._attribute_lock:
            self._relogin_interval = interval

    async def _update_sites(self, soup: BeautifulSoup) -> None:
        with self._attribute_lock:
            if self._site is None:
                await self._initialize_sites(soup)
                if self._site is None:
                    raise RuntimeError("pyadtpulse could not retrieve site")
            self._site.alarm_control_panel._update_alarm_from_soup(soup)
            self._site._update_zone_from_soup(soup)

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
                    site_id = m.group(1)
                    LOG.debug(f"Discovered site id {site_id}: {site_name}")
                    new_site = ADTPulseSite(self._pulse_connection, site_id, site_name)

                    # fetch zones first, so that we can have the status
                    # updated with _update_alarm_status
                    if not await new_site._fetch_devices(None):
                        LOG.error("Could not fetch zones from ADT site")
                    new_site.alarm_control_panel._update_alarm_from_soup(soup)
                    if new_site.alarm_control_panel.status == ADT_ALARM_UNKNOWN:
                        new_site.gateway.is_online = False
                    new_site._update_zone_from_soup(soup)
                    with self._attribute_lock:
                        self._site = new_site
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

    def _check_retry_after(
        self, response: Optional[ClientResponse], task_name: str
    ) -> int:
        if response is None:
            return 0
        header_value = response.headers.get("Retry-After")
        if header_value is None:
            return 0
        if header_value.isnumeric():
            retval = int(header_value)
        else:
            try:
                retval = (
                    datetime.datetime.strptime(header_value, "%a, %d %b %G %T %Z")
                    - datetime.datetime.now()
                ).seconds
            except ValueError:
                return 0
        reason = "Unknown"
        if response.status == 429:
            reason = "Too many requests"
        elif response.status == 503:
            reason = "Service unavailable"
        LOG.warning(f"Task {task_name} received Retry-After {retval} due to {reason}")
        return retval

    async def _keepalive_task(self) -> None:
        retry_after = 0
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
            relogin_interval = self.relogin_interval * 60
            if (
                relogin_interval != 0
                and time.time() - self._last_login_time > relogin_interval
            ):
                LOG.info("Login timeout reached, re-logging in")
                # FIXME?: should we just pause the task?
                with self._attribute_lock:
                    if self._sync_task is not None:
                        self._sync_task.cancel()
                        with suppress(Exception):
                            await self._sync_task
                    await self._do_logout_query()
                    response = await self._do_login_query()
                    if response is None:
                        LOG.error(
                            f"{task_name} could not re-login to ADT Pulse, exiting..."
                        )
                        return
                    close_response(response)
                    if self._sync_task is not None:
                        coro = self._sync_check_task()
                        self._sync_task = asyncio.create_task(
                            coro, name=f"{SYNC_CHECK_TASK_NAME}: Async session"
                        )
            try:
                await asyncio.sleep(ADT_TIMEOUT_INTERVAL * 60.0 + retry_after)
                LOG.debug("Resetting timeout")
                response = await self._pulse_connection._async_query(
                    ADT_TIMEOUT_URI, "POST"
                )
                if handle_response(
                    response, logging.INFO, "Failed resetting ADT Pulse cloud timeout"
                ):
                    retry_after = self._check_retry_after(response, "Keepalive task")
                    close_response(response)
                    continue
                close_response(response)
                if self.site.gateway.next_update < time.time():
                    await self.site._set_device(ADT_GATEWAY_STRING)
            except asyncio.CancelledError:
                LOG.debug(f"{task_name} cancelled")
                close_response(response)
                return

    def _pulse_session_thread(self) -> None:
        # lock is released in sync_loop()
        self._attribute_lock.acquire()

        LOG.debug("Creating ADT Pulse background thread")
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        loop = asyncio.new_event_loop()
        self._pulse_connection.loop = loop
        loop.run_until_complete(self._sync_loop())

        loop.close()
        self._pulse_connection.loop = None
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
        return self._pulse_connection.loop

    async def _do_login_query(self, timeout: int = 30) -> ClientResponse | None:
        try:
            retval = await self._pulse_connection._async_query(
                ADT_LOGIN_URI,
                method="POST",
                extra_params={
                    "partner": "adt",
                    "e": "ns",
                    "usernameForm": self.username,
                    "passwordForm": self._password,
                    "fingerprint": self._fingerprint,
                    "sun": "yes",
                },
                timeout=timeout,
            )
        except Exception as e:
            LOG.error(f"Could not log into Pulse site: {e}")
            return None
        if retval is None:
            LOG.error("Could not log into Pulse site.")
            return None
        if not handle_response(
            retval,
            logging.ERROR,
            "Error encountered communicating with Pulse site on login",
        ):
            close_response(retval)
            return None
        self._last_login_time = time.time()
        return retval

    async def _do_logout_query(self) -> None:
        params = {}
        network: ADTPulseSite = self.site
        if network is not None:
            params.update({"network": str(network.id)})
        params.update({"partner": "adt"})
        await self._pulse_connection._async_query(
            ADT_LOGOUT_URI, extra_params=params, timeout=10
        )

    async def async_login(self) -> bool:
        """Login asynchronously to ADT.

        Returns: True if login successful
        """
        if self._authenticated is None:
            self._authenticated = asyncio.locks.Event()
        else:
            self._authenticated.clear()

        LOG.debug(f"Authenticating to ADT Pulse cloud service as {self._username}")
        await self._pulse_connection._async_fetch_version()

        response = await self._do_login_query()
        if response is None:
            return False
        if self._pulse_connection.make_url(ADT_SUMMARY_URI) != str(response.url):  # type: ignore
            # more specifically:
            # redirect to signin.jsp = username/password error
            # redirect to mfaSignin.jsp = fingerprint error
            LOG.error("Authentication error encountered logging into ADT Pulse")
            close_response(response)
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
        if self._site is None:
            LOG.error("Could not retrieve any sites, login failed")
            self._authenticated.clear()
            return False

        # since we received fresh data on the status of the alarm, go ahead
        # and update the sites with the alarm status.

        if self._timeout_task is None:
            self._timeout_task = asyncio.create_task(
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
        await self._do_logout_query()
        if self._authenticated is not None:
            self._authenticated.clear()

    def logout(self) -> None:
        """Log out of ADT Pulse."""
        loop = self._pulse_connection.loop
        if loop is None:
            raise RuntimeError("Attempting to call sync logout without sync login")
        sync_thread = self._session_thread

        coro = self.async_logout()
        asyncio.run_coroutine_threadsafe(coro, loop)
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
        retry_after = 0
        if self._updates_exist is None:
            raise RuntimeError(f"{task_name} started without update event initialized")
        have_update = False
        while True:
            try:
                pi = self.site.gateway.poll_interval
                if have_update:
                    pi = pi / 2.0
                if retry_after == 0:
                    await asyncio.sleep(pi)
                else:
                    await asyncio.sleep(retry_after)
                response = await self._pulse_connection._async_query(
                    ADT_SYNC_CHECK_URI,
                    extra_params={"ts": str(int(time.time() * 1000))},
                )

                if response is None:
                    continue
                retry_after = self._check_retry_after(response, f"{task_name}")
                if retry_after != 0:
                    close_response(response)
                    continue
                text = await response.text()
                if not handle_response(
                    response, logging.ERROR, "Error querying ADT sync"
                ):
                    close_response(response)
                    continue

                pattern = r"\d+[-]\d+[-]\d+"
                if not re.match(pattern, text):
                    LOG.warn(
                        f"Unexpected sync check format ({pattern}), forcing re-auth"
                    )
                    LOG.debug(f"Received {text} from ADT Pulse site")
                    close_response(response)
                    await self._do_logout_query()
                    await self.async_login()
                    continue

                # we can have 0-0-0 followed by 1-0-0 followed by 2-0-0, etc
                # wait until these settle
                if text.endswith("-0-0"):
                    LOG.debug(
                        f"Sync token {text} indicates updates may exist, requerying"
                    )
                    close_response(response)
                    have_update = True
                    continue
                if have_update:
                    have_update = False
                    if await self.async_update() is False:
                        LOG.debug(f"Pulse data update from {task_name} failed")
                        continue
                    self._updates_exist.set()
                LOG.debug(f"Sync token {text} indicates no remote updates to process")
                close_response(response)

            except asyncio.CancelledError:
                LOG.debug(f"{task_name} cancelled")
                close_response(response)
                return

    @property
    def updates_exist(self) -> bool:
        """Check if updated data exists.

        Returns:
            bool: True if updated data exists
        """
        with self._attribute_lock:
            if self._sync_task is None:
                loop = self._pulse_connection.loop
                if loop is None:
                    raise RuntimeError(
                        "ADT pulse sync function updates_exist() "
                        "called from async session"
                    )
                coro = self._sync_check_task()
                self._sync_task = loop.create_task(
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
                self._sync_task = asyncio.create_task(
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

    # FIXME? might have to move this to site for multiple sites

    async def async_update(self) -> bool:
        """Update ADT Pulse data.

        Returns:
            bool: True if update succeeded.
        """
        LOG.debug("Checking ADT Pulse cloud service for updates")

        # FIXME will have to query other URIs for camera/zwave/etc
        soup = await self._pulse_connection._query_orb(
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
        loop = self._pulse_connection.loop
        if loop is None:
            raise RuntimeError("Attempting to run sync update from async login")
        coro = self.async_update()
        return asyncio.run_coroutine_threadsafe(coro, loop).result()

    # FIXME circular reference, should be ADTPulseSite

    @property
    def sites(self) -> List[ADTPulseSite]:
        """Return all sites for this ADT Pulse account."""
        warn(
            "multiple sites being removed, use pyADTPulse.site instead",
            PendingDeprecationWarning,
            stacklevel=2,
        )
        with self._attribute_lock:
            if self._site is None:
                raise RuntimeError(
                    "No sites have been retrieved, have you logged in yet?"
                )
            return [self._site]

    @property
    def site(self) -> ADTPulseSite:
        """Return the site associated with the Pulse login."""
        with self._attribute_lock:
            if self._site is None:
                raise RuntimeError(
                    "No sites have been retrieved, have you logged in yet?"
                )
            return self._site
