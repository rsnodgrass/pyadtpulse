"""Test Pulse Query Manager."""

import logging
import asyncio
import time
from datetime import datetime, timedelta
from typing import Any, Callable

import pytest
from aiohttp import client_exceptions, client_reqrep
from aioresponses import aioresponses
from bs4 import BeautifulSoup
from freezegun.api import FrozenDateTimeFactory, StepTickTimeFactory

from conftest import MOCKED_API_VERSION
from pyadtpulse.const import ADT_ORB_URI, DEFAULT_API_HOST
from pyadtpulse.exceptions import (
    PulseClientConnectionError,
    PulseConnectionError,
    PulseServerConnectionError,
    PulseServiceTemporarilyUnavailableError,
)
from pyadtpulse.pulse_connection_properties import PulseConnectionProperties
from pyadtpulse.pulse_connection_status import PulseConnectionStatus
from pyadtpulse.pulse_query_manager import MAX_REQUERY_RETRIES, PulseQueryManager


@pytest.mark.asyncio
async def test_fetch_version(mocked_server_responses: aioresponses):
    """Test fetch version."""
    s = PulseConnectionStatus()
    cp = PulseConnectionProperties(DEFAULT_API_HOST)
    p = PulseQueryManager(s, cp)
    await p.async_fetch_version()
    assert cp.api_version == MOCKED_API_VERSION


@pytest.mark.asyncio
async def test_fetch_version_fail(mock_server_down: aioresponses):
    """Test fetch version."""
    s = PulseConnectionStatus()
    cp = PulseConnectionProperties(DEFAULT_API_HOST)
    p = PulseQueryManager(s, cp)
    with pytest.raises(PulseServerConnectionError):
        await p.async_fetch_version()
    assert s.get_backoff().backoff_count == 1
    with pytest.raises(PulseServerConnectionError):
        await p.async_query(ADT_ORB_URI, requires_authentication=False)
    assert s.get_backoff().backoff_count == 2
    assert s.get_backoff().get_current_backoff_interval() == 2.0


@pytest.mark.asyncio
async def test_fetch_version_eventually_succeeds(
    mock_server_temporarily_down: aioresponses,
):
    """Test fetch version."""
    s = PulseConnectionStatus()
    cp = PulseConnectionProperties(DEFAULT_API_HOST)
    p = PulseQueryManager(s, cp)
    with pytest.raises(PulseServerConnectionError):
        await p.async_fetch_version()
    assert s.get_backoff().backoff_count == 1
    with pytest.raises(PulseServerConnectionError):
        await p.async_query(ADT_ORB_URI, requires_authentication=False)
    assert s.get_backoff().backoff_count == 2
    assert s.get_backoff().get_current_backoff_interval() == 2.0
    await p.async_fetch_version()
    assert s.get_backoff().backoff_count == 0


@pytest.mark.asyncio
async def test_query_orb(
    mocked_server_responses: aioresponses,
    read_file: Callable[..., str],
    mock_sleep: Any,
    get_mocked_connection_properties: PulseConnectionProperties,
):
    """Test query orb.

    We also check that it waits for authenticated flag.
    """

    async def query_orb_task():
        return await p.query_orb(logging.DEBUG, "Failed to query orb")

    s = PulseConnectionStatus()
    cp = get_mocked_connection_properties
    p = PulseQueryManager(s, cp)
    orb_file = read_file("orb.html")
    mocked_server_responses.get(
        cp.make_url(ADT_ORB_URI), status=200, content_type="text/html", body=orb_file
    )
    task = asyncio.create_task(query_orb_task())
    await asyncio.sleep(2)
    assert not task.done()
    s.authenticated_flag.set()
    await task
    assert task.done()
    assert task.result() == BeautifulSoup(orb_file, "html.parser")
    assert mock_sleep.call_count == 1  # from the asyncio.sleep call above
    mocked_server_responses.get(cp.make_url(ADT_ORB_URI), status=404)
    with pytest.raises(PulseServerConnectionError):
        result = await query_orb_task()
    assert mock_sleep.call_count == 1
    assert s.get_backoff().backoff_count == 1
    mocked_server_responses.get(
        cp.make_url(ADT_ORB_URI), status=200, content_type="text/html", body=orb_file
    )
    result = await query_orb_task()
    assert result == BeautifulSoup(orb_file, "html.parser")
    assert mock_sleep.call_count == 2


@pytest.mark.asyncio
async def test_retry_after(
    mocked_server_responses: aioresponses,
    freeze_time_to_now: FrozenDateTimeFactory | StepTickTimeFactory,
    get_mocked_connection_properties: PulseConnectionProperties,
    mock_sleep: Any,
):
    """Test retry after."""

    retry_after_time = 120
    frozen_time = freeze_time_to_now
    now = time.time()

    s = PulseConnectionStatus()
    cp = get_mocked_connection_properties
    p = PulseQueryManager(s, cp)

    mocked_server_responses.get(
        cp.make_url(ADT_ORB_URI),
        status=429,
        headers={"Retry-After": str(retry_after_time)},
    )
    with pytest.raises(PulseServiceTemporarilyUnavailableError):
        await p.async_query(ADT_ORB_URI, requires_authentication=False)
    # make sure we can't override the retry
    s.get_backoff().reset_backoff()
    assert s.get_backoff().expiration_time == int(now + float(retry_after_time))
    with pytest.raises(PulseServiceTemporarilyUnavailableError):
        await p.async_query(ADT_ORB_URI, requires_authentication=False)
    frozen_time.tick(timedelta(seconds=retry_after_time + 1))
    mocked_server_responses.get(
        cp.make_url(ADT_ORB_URI),
        status=200,
    )
    # this should succeed
    await p.async_query(ADT_ORB_URI, requires_authentication=False)

    now = time.time()
    retry_date = now + float(retry_after_time)
    retry_date_str = datetime.fromtimestamp(retry_date).strftime(
        "%a, %d %b %Y %H:%M:%S GMT"
    )
    # need to get the new retry after time since it doesn't have fractions of seconds
    new_retry_after = (
        datetime.strptime(retry_date_str, "%a, %d %b %Y %H:%M:%S GMT").timestamp() - now
    )
    mocked_server_responses.get(
        cp.make_url(ADT_ORB_URI),
        status=503,
        headers={"Retry-After": retry_date_str},
    )
    with pytest.raises(PulseServiceTemporarilyUnavailableError):
        await p.async_query(ADT_ORB_URI, requires_authentication=False)

    frozen_time.tick(timedelta(seconds=new_retry_after - 1))
    with pytest.raises(PulseServiceTemporarilyUnavailableError):
        await p.async_query(ADT_ORB_URI, requires_authentication=False)
    frozen_time.tick(timedelta(seconds=2))
    mocked_server_responses.get(
        cp.make_url(ADT_ORB_URI),
        status=200,
    )
    # should succeed
    await p.async_query(ADT_ORB_URI, requires_authentication=False)
    # unavailable with no retry after
    mocked_server_responses.get(
        cp.make_url(ADT_ORB_URI),
        status=503,
    )
    frozen_time.tick(timedelta(seconds=retry_after_time + 1))
    with pytest.raises(PulseServiceTemporarilyUnavailableError):
        await p.async_query(ADT_ORB_URI, requires_authentication=False)
    mocked_server_responses.get(
        cp.make_url(ADT_ORB_URI),
        status=200,
    )
    # should succeed
    frozen_time.tick(timedelta(seconds=1))
    await p.async_query(ADT_ORB_URI, requires_authentication=False)

    # retry after in the past
    mocked_server_responses.get(
        cp.make_url(ADT_ORB_URI),
        status=503,
        headers={"Retry-After": retry_date_str},
    )
    with pytest.raises(PulseServiceTemporarilyUnavailableError):
        await p.async_query(ADT_ORB_URI, requires_authentication=False)
    mocked_server_responses.get(
        cp.make_url(ADT_ORB_URI),
        status=200,
    )
    frozen_time.tick(timedelta(seconds=1))
    # should succeed
    await p.async_query(ADT_ORB_URI, requires_authentication=False)


async def run_query_exception_test(
    mocked_server_responses,
    mock_sleep,
    get_mocked_connection_properties,
    aiohttp_exception: client_exceptions.ClientError,
    pulse_exception: PulseConnectionError,
):
    s = PulseConnectionStatus()
    cp = get_mocked_connection_properties
    p = PulseQueryManager(s, cp)
    # need to do ClientConnectorError, but it requires initialization
    for _ in range(MAX_REQUERY_RETRIES + 1):
        mocked_server_responses.get(
            cp.make_url(ADT_ORB_URI),
            exception=aiohttp_exception,
        )
    mocked_server_responses.get(
        cp.make_url(ADT_ORB_URI),
        status=200,
    )
    with pytest.raises(pulse_exception):
        await p.async_query(
            ADT_ORB_URI,
            requires_authentication=False,
        )

    # only MAX_REQUERY_RETRIES - 1 sleeps since first call won't sleep
    assert (
        mock_sleep.call_count == MAX_REQUERY_RETRIES - 1
    ), f"Failure on exception {aiohttp_exception.__name__}"
    for i in range(MAX_REQUERY_RETRIES - 1):
        assert mock_sleep.call_args_list[i][0][0] == 1 * 2 ** (
            i
        ), f"Failure on exception sleep count {i} on exception {aiohttp_exception.__name__}"
    assert (
        s.get_backoff().backoff_count == 1
    ), f"Failure on exception {aiohttp_exception.__name__}"
    with pytest.raises(pulse_exception):
        await p.async_query(ADT_ORB_URI, requires_authentication=False)
    # pqm backoff should trigger here

    # MAX_REQUERY_RETRIES - 1 backoff for query, 1 for connection backoff
    assert mock_sleep.call_count == MAX_REQUERY_RETRIES
    assert (
        mock_sleep.call_args_list[MAX_REQUERY_RETRIES - 1][0][0]
        == s.get_backoff().initial_backoff_interval
    )
    mocked_server_responses.get(
        cp.make_url(ADT_ORB_URI),
        status=200,
    )
    # this should trigger a sleep
    await p.async_query(ADT_ORB_URI, requires_authentication=False)
    assert mock_sleep.call_count == MAX_REQUERY_RETRIES + 1
    assert (
        mock_sleep.call_args_list[MAX_REQUERY_RETRIES][0][0]
        == s.get_backoff().initial_backoff_interval * 2
    )
    # this shouldn't trigger a sleep
    await p.async_query(ADT_ORB_URI, requires_authentication=False)
    assert mock_sleep.call_count == MAX_REQUERY_RETRIES + 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "test_exception",
    (
        (client_exceptions.ClientConnectionError, PulseClientConnectionError),
        (client_exceptions.ClientError, PulseClientConnectionError),
        (client_exceptions.ClientOSError, PulseClientConnectionError),
        (client_exceptions.ServerDisconnectedError, PulseServerConnectionError),
        (client_exceptions.ServerTimeoutError, PulseServerConnectionError),
        (client_exceptions.ServerConnectionError, PulseServerConnectionError),
        (asyncio.TimeoutError, PulseServerConnectionError),
    ),
)
async def test_async_query_exceptions(
    mocked_server_responses: aioresponses,
    mock_sleep: Any,
    get_mocked_connection_properties: PulseConnectionProperties,
    test_exception,
):
    await run_query_exception_test(
        mocked_server_responses,
        mock_sleep,
        get_mocked_connection_properties,
        *test_exception,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "test_exception",
    (
        (ConnectionRefusedError, PulseServerConnectionError),
        (ConnectionResetError, PulseServerConnectionError),
        (TimeoutError, PulseClientConnectionError),
        (BrokenPipeError, PulseClientConnectionError),
    ),
)
async def test_async_query_connector_errors(
    mocked_server_responses: aioresponses,
    mock_sleep: Any,
    get_mocked_connection_properties: PulseConnectionProperties,
    test_exception,
):
    aiohttp_exception = client_exceptions.ClientConnectorError(
        client_reqrep.ConnectionKey(
            DEFAULT_API_HOST,
            443,
            is_ssl=True,
            ssl=True,
            proxy=None,
            proxy_auth=None,
            proxy_headers_hash=None,
        ),
        os_error=test_exception[0],
    )
    await run_query_exception_test(
        mocked_server_responses,
        mock_sleep,
        get_mocked_connection_properties,
        aiohttp_exception,
        test_exception[1],
    )


async def test_wait_for_authentication_flag(
    mocked_server_responses: aioresponses,
    get_mocked_connection_properties: PulseConnectionProperties,
    read_file: Callable[..., str],
):
    async def query_orb_task(lock: asyncio.Lock):
        async with lock:
            try:
                result = await p.query_orb(logging.DEBUG, "Failed to query orb")
            except asyncio.CancelledError:
                result = None
            return result

    s = PulseConnectionStatus()
    cp = get_mocked_connection_properties
    p = PulseQueryManager(s, cp)
    mocked_server_responses.get(
        cp.make_url(ADT_ORB_URI),
        status=200,
        body=read_file("orb.html"),
    )
    lock = asyncio.Lock()
    task = asyncio.create_task(query_orb_task(lock))
    try:
        await asyncio.wait_for(query_orb_task(lock), 10)
    except asyncio.TimeoutError:
        task.cancel()
        await task
        # if we time out, the test has passed
    else:
        pytest.fail("Query should have timed out")
    await lock.acquire()
    task = asyncio.create_task(query_orb_task(lock))
    lock.release()
    await asyncio.sleep(1)
    assert not task.done()
    await asyncio.sleep(3)
    assert not task.done()
    s.authenticated_flag.set()
    result = await task
    assert result == BeautifulSoup(read_file("orb.html"), "html.parser")

    # test query with retry will wait for authentication
    # don't set an orb response so that we will backoff on the query
    await lock.acquire()
    task = asyncio.create_task(query_orb_task(lock))
    lock.release()
    await asyncio.sleep(0.5)
    assert not task.done()
    s.authenticated_flag.clear()
    await asyncio.sleep(5)
    assert not task.done()
    s.authenticated_flag.set()
    with pytest.raises(PulseServerConnectionError):
        await task
