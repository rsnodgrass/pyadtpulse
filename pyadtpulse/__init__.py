"""Base Python Class for pyadtpulse."""

import logging
import asyncio
import time
from threading import RLock, Thread
from warnings import warn

import aiohttp_zlib_ng
import uvloop

from .const import (
    ADT_DEFAULT_HTTP_USER_AGENT,
    ADT_DEFAULT_KEEPALIVE_INTERVAL,
    ADT_DEFAULT_RELOGIN_INTERVAL,
    DEFAULT_API_HOST,
)
from .pyadtpulse_async import SYNC_CHECK_TASK_NAME, PyADTPulseAsync
from .util import DebugRLock, set_debug_lock

aiohttp_zlib_ng.enable_zlib_ng()
LOG = logging.getLogger(__name__)


class PyADTPulse(PyADTPulseAsync):
    """Base object for ADT Pulse service."""

    __slots__ = ("_session_thread", "_p_attribute_lock", "_login_exception")

    def __init__(
        self,
        username: str,
        password: str,
        fingerprint: str,
        service_host: str = DEFAULT_API_HOST,
        user_agent=ADT_DEFAULT_HTTP_USER_AGENT["User-Agent"],
        do_login: bool = True,
        debug_locks: bool = False,
        keepalive_interval: int = ADT_DEFAULT_KEEPALIVE_INTERVAL,
        relogin_interval: int = ADT_DEFAULT_RELOGIN_INTERVAL,
        detailed_debug_logging: bool = False,
    ):
        self._p_attribute_lock = set_debug_lock(
            debug_locks, "pyadtpulse._p_attribute_lockattribute_lock"
        )
        warn(
            "PyADTPulse is deprecated, please use PyADTPulseAsync instead",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(
            username,
            password,
            fingerprint,
            service_host,
            user_agent,
            debug_locks,
            keepalive_interval,
            relogin_interval,
            detailed_debug_logging,
        )
        self._session_thread: Thread | None = None
        self._login_exception: Exception | None = None
        if do_login:
            self.login()

    def __repr__(self) -> str:
        """Object representation."""
        return (
            f"<{self.__class__.__name__}: {self._authentication_properties.username}>"
        )

    # ADTPulse API endpoint is configurable (besides default US ADT Pulse endpoint) to
    # support testing as well as alternative ADT Pulse endpoints such as
    # portal-ca.adtpulse.com

    def _pulse_session_thread(self) -> None:
        """
        Pulse the session thread.

        Acquires the attribute lock and creates a background thread for the ADT
        Pulse API. The thread runs the synchronous loop `_sync_loop()` until completion.
        Once the loop finishes, the thread is closed, the pulse connection's event loop
        is set to `None`, and the session thread is set to `None`.
        """
        # lock is released in sync_loop()
        self._p_attribute_lock.acquire()

        LOG.debug("Creating ADT Pulse background thread")
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        loop = asyncio.new_event_loop()
        self._pulse_connection_properties.loop = loop
        loop.run_until_complete(self._sync_loop())

        loop.close()
        self._pulse_connection_properties.loop = None
        self._session_thread = None

    async def _sync_loop(self) -> None:
        """
        Asynchronous function that represents the main loop of the synchronization
        process.

        This function is responsible for executing the synchronization logic. It starts
        by calling the `async_login` method to perform the login operation. After that,
        it releases the `_p_attribute_lock` to allow other tasks to access the
        attributes.
        If the login operation was successful, it waits for the `_timeout_task` to
        complete using the `asyncio.wait` function.  If the `_timeout_task` is not set,
        it raises a `RuntimeError` to indicate that background tasks were not created.

        After the waiting process, it enters a while loop that continues as long as the
        `_authenticated` event is set. Inside the loop, it waits for 0.5 seconds using
        the `asyncio.sleep` function. This wait allows the logout process to complete
        before continuing with the synchronization logic.
        """
        try:
            await self.async_login()
        except Exception as e:
            self._login_exception = e
        self._p_attribute_lock.release()
        if self._login_exception is not None:
            return
        if self._timeout_task is not None:
            task_list = (self._timeout_task,)
            try:
                await asyncio.wait(task_list)
            except asyncio.CancelledError:
                pass
            except Exception as e:  # pylint: disable=broad-except
                LOG.exception(
                    "Received exception while waiting for ADT Pulse service %s", e
                )
        else:
            # we should never get here
            raise RuntimeError("Background pyadtpulse tasks not created")
        while self._pulse_connection_status.authenticated_flag.is_set():
            # busy wait until logout is done
            await asyncio.sleep(0.5)

    def login(self) -> None:
        """Login to ADT Pulse and generate access token.

        Raises:
            Exception from async_login
        """
        self._p_attribute_lock.acquire()
        # probably shouldn't be a daemon thread
        self._session_thread = thread = Thread(
            target=self._pulse_session_thread,
            name="PyADTPulse Session",
            daemon=True,
        )
        self._p_attribute_lock.release()

        self._session_thread.start()
        time.sleep(1)

        # thread will unlock after async_login, so attempt to obtain
        # lock to block current thread until then
        # if it's still alive, no exception
        self._p_attribute_lock.acquire()
        self._p_attribute_lock.release()
        if not thread.is_alive():
            if self._login_exception is not None:
                raise self._login_exception

    def logout(self) -> None:
        """Log out of ADT Pulse."""
        loop = self._pulse_connection.check_sync(
            "Attempting to call sync logout without sync login"
        )
        sync_thread = self._session_thread

        coro = self.async_logout()
        asyncio.run_coroutine_threadsafe(coro, loop)
        if sync_thread is not None:
            sync_thread.join()

    @property
    def attribute_lock(self) -> "RLock| DebugRLock":
        """Get attribute lock for PyADTPulse object.

        Returns:
            RLock: thread Rlock
        """
        return self._p_attribute_lock

    @property
    def loop(self) -> asyncio.AbstractEventLoop | None:
        """Get event loop.

        Returns:
            Optional[asyncio.AbstractEventLoop]: the event loop object or
                                                 None if no thread is running
        """
        return self._pulse_connection_properties.loop

    @property
    def updates_exist(self) -> bool:
        """Check if updated data exists.

        Returns:
            bool: True if updated data exists
        """
        with self._p_attribute_lock:
            if self._sync_task is None:
                loop = self._pulse_connection_properties.loop
                if loop is None:
                    raise RuntimeError(
                        "ADT pulse sync function updates_exist() "
                        "called from async session"
                    )
                coro = self._sync_check_task()
                self._sync_task = loop.create_task(
                    coro, name=f"{SYNC_CHECK_TASK_NAME}: Sync session"
                )
            if self._pulse_properties.updates_exist.is_set():
                self._pulse_properties.updates_exist.clear()
                return True
            return False

    def update(self) -> bool:
        """Update ADT Pulse data.

        Returns:
            bool: True on success
        """
        coro = self.async_update()
        return asyncio.run_coroutine_threadsafe(
            coro,
            self._pulse_connection.check_sync(
                "Attempting to run sync update from async login"
            ),
        ).result()

    async def async_login(self) -> None:
        self._pulse_connection_properties.check_async(
            "Cannot login asynchronously with a synchronous session"
        )
        await super().async_login()

    async def async_logout(self) -> None:
        self._pulse_connection_properties.check_async(
            "Cannot logout asynchronously with a synchronous session"
        )
        await super().async_logout()

    async def async_update(self) -> bool:
        self._pulse_connection_properties.check_async(
            "Cannot update asynchronously with a synchronous session"
        )
        return await super().async_update()
