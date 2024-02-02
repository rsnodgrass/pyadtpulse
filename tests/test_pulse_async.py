"""Test Pulse Query Manager."""

import asyncio
import re
from collections.abc import Generator
from http.client import responses
from typing import Any, Callable, Literal
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest
from aioresponses import aioresponses
from pytest_mock import MockerFixture

from conftest import LoginType, add_custom_response, add_logout, add_signin
from pyadtpulse.const import (
    ADT_DEFAULT_POLL_INTERVAL,
    ADT_DEVICE_URI,
    ADT_LOGIN_URI,
    ADT_LOGOUT_URI,
    ADT_MFA_FAIL_URI,
    ADT_ORB_URI,
    ADT_SUMMARY_URI,
    ADT_SYNC_CHECK_URI,
    ADT_TIMEOUT_URI,
    DEFAULT_API_HOST,
)
from pyadtpulse.exceptions import (
    PulseAuthenticationError,
    PulseConnectionError,
    PulseGatewayOfflineError,
    PulseMFARequiredError,
    PulseNotLoggedInError,
    PulseServerConnectionError,
)
from pyadtpulse.pulse_authentication_properties import PulseAuthenticationProperties
from pyadtpulse.pyadtpulse_async import PyADTPulseAsync

DEFAULT_SYNC_CHECK = "234532-456432-0"
NEXT_SYNC_CHECK = "234533-456432-0"


def set_keepalive(get_mocked_url, mocked_server_responses, repeat: bool = False):
    m = mocked_server_responses
    m.post(
        get_mocked_url(ADT_TIMEOUT_URI),
        body="",
        content_type="text/html",
        repeat=repeat,
    )


@pytest.mark.asyncio
async def test_mocked_responses(
    read_file: Callable[..., str],
    mocked_server_responses: aioresponses,
    get_mocked_mapped_static_responses: dict[str, str],
    get_mocked_url: Callable[..., str],
    extract_ids_from_data_directory: list[str],
):
    """Fixture to test mocked responses."""
    static_responses = get_mocked_mapped_static_responses
    m = mocked_server_responses
    async with aiohttp.ClientSession() as session:
        for url, file_name in static_responses.items():
            # Make an HTTP request to the URL
            response = await session.get(url)

            # Assert the status code is 200
            assert response.status == 200

            # Assert the content matches the content of the file
            expected_content = read_file(file_name)
            actual_content = await response.text()
            assert actual_content == expected_content
        devices = extract_ids_from_data_directory
        for device_id in devices:
            response = await session.get(
                f"{get_mocked_url(ADT_DEVICE_URI)}?id={device_id}"
            )
            assert response.status == 200
            expected_content = read_file(f"device_{device_id}.html")
            actual_content = await response.text()
            assert actual_content == expected_content

        # redirects
        add_custom_response(
            mocked_server_responses,
            read_file,
            get_mocked_url(ADT_LOGIN_URI),
            file_name="signin.html",
        )
        response = await session.get(f"{DEFAULT_API_HOST}/", allow_redirects=True)
        assert response.status == 200
        actual_content = await response.text()
        expected_content = read_file("signin.html")
        assert actual_content == expected_content
        add_custom_response(
            mocked_server_responses,
            read_file,
            get_mocked_url(ADT_LOGIN_URI),
            file_name="signin.html",
        )
        response = await session.get(get_mocked_url(ADT_LOGOUT_URI))
        assert response.status == 200
        expected_content = read_file("signin.html")
        actual_content = await response.text()
        assert actual_content == expected_content
        add_signin(
            LoginType.SUCCESS, mocked_server_responses, get_mocked_url, read_file
        )
        response = await session.post(get_mocked_url(ADT_LOGIN_URI))
        assert response.status == 200
        expected_content = read_file(static_responses[get_mocked_url(ADT_SUMMARY_URI)])
        actual_content = await response.text()
        assert actual_content == expected_content
        pattern = re.compile(rf"{re.escape(get_mocked_url(ADT_SYNC_CHECK_URI))}/?.*$")
        m.get(pattern, status=200, body="1-0-0", content_type="text/html")
        response = await session.get(
            get_mocked_url(ADT_SYNC_CHECK_URI), params={"ts": "first call"}
        )
        assert response.status == 200
        actual_content = await response.text()
        expected_content = "1-0-0"
        assert actual_content == expected_content
        set_keepalive(get_mocked_url, m)
        response = await session.post(get_mocked_url(ADT_TIMEOUT_URI))


# not sure we need this
@pytest.fixture
def wrap_wait_for_update():
    with patch.object(
        PyADTPulseAsync,
        "wait_for_update",
        new_callable=AsyncMock,
        spec=PyADTPulseAsync,
        wraps=PyADTPulseAsync.wait_for_update,
    ) as wait_for_update:
        yield wait_for_update


@pytest.fixture
@pytest.mark.asyncio
async def adt_pulse_instance(
    mocked_server_responses: aioresponses,
    extract_ids_from_data_directory: list[str],
    get_mocked_url: Callable[..., str],
    read_file: Callable[..., str],
):
    """Create an instance of PyADTPulseAsync and login."""
    p = PyADTPulseAsync("testuser@example.com", "testpassword", "testfingerprint")
    add_signin(LoginType.SUCCESS, mocked_server_responses, get_mocked_url, read_file)
    await p.async_login()
    # Assertions after login
    assert p._pulse_connection_status.authenticated_flag.is_set()
    assert p._pulse_connection_status.get_backoff().backoff_count == 0
    assert p._pulse_connection.login_in_progress is False
    assert p._pulse_connection.login_backoff.backoff_count == 0
    assert p.site.name == "Robert Lippmann"
    assert p._timeout_task is not None
    assert p._timeout_task.get_name() == p._get_timeout_task_name()
    assert p._sync_task is None
    assert p.site.zones_as_dict is not None
    assert len(p.site.zones_as_dict) == len(extract_ids_from_data_directory) - 3
    return p, mocked_server_responses


@pytest.mark.asyncio
async def test_login(
    adt_pulse_instance: tuple[PyADTPulseAsync, Any],
    extract_ids_from_data_directory: list[str],
    get_mocked_url: Callable[..., str],
    read_file: Callable[..., str],
):
    """Fixture to test login."""
    p, response = await adt_pulse_instance
    # make sure everything is there on logout

    assert p._pulse_connection_status.get_backoff().backoff_count == 0
    assert p._pulse_connection.login_in_progress is False
    assert p._pulse_connection.login_backoff.backoff_count == 0
    add_logout(response, get_mocked_url, read_file)
    add_custom_response(
        response,
        read_file,
        get_mocked_url(ADT_LOGIN_URI),
        file_name=LoginType.SUCCESS.value,
    )
    await p.async_logout()
    assert not p._pulse_connection_status.authenticated_flag.is_set()
    assert p._pulse_connection_status.get_backoff().backoff_count == 0
    assert p._pulse_connection.login_in_progress is False
    assert p._pulse_connection.login_backoff.backoff_count == 0
    assert p.site.name == "Robert Lippmann"
    assert p.site.zones_as_dict is not None
    assert len(p.site.zones_as_dict) == len(extract_ids_from_data_directory) - 3
    assert p._timeout_task is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "test_type",
    (
        (LoginType.FAIL, PulseAuthenticationError),
        (LoginType.NOT_SIGNED_IN, PulseNotLoggedInError),
        (LoginType.MFA, PulseMFARequiredError),
    ),
)
async def test_login_failures(
    adt_pulse_instance: tuple[PyADTPulseAsync, Any],
    get_mocked_url: Callable[..., str],
    read_file: Callable[..., str],
    test_type: Literal[LoginType.FAIL, LoginType.NOT_SIGNED_IN, LoginType.MFA],
):
    p, response = await adt_pulse_instance
    assert p._pulse_connection.login_backoff.backoff_count == 0, "initial"
    add_logout(response, get_mocked_url, read_file)
    await p.async_logout()
    assert p._pulse_connection.login_backoff.backoff_count == 0, "post logout"

    assert p._pulse_connection.login_backoff.backoff_count == 0, str(test_type[0])
    add_signin(test_type[0], response, get_mocked_url, read_file)
    with pytest.raises(test_type[1]):
        await p.async_login()
    await asyncio.sleep(1)
    assert p._timeout_task is None or p._timeout_task.done()
    assert p._pulse_connection.login_backoff.backoff_count == 0, str(test_type)
    add_signin(LoginType.SUCCESS, response, get_mocked_url, read_file)
    await p.async_login()
    assert p._pulse_connection.login_backoff.backoff_count == 0


async def do_wait_for_update(p: PyADTPulseAsync, shutdown_event: asyncio.Event):
    while not shutdown_event.is_set():
        try:
            await p.wait_for_update()
        except asyncio.CancelledError:
            break


@pytest.mark.asyncio
async def test_wait_for_update(
    adt_pulse_instance: tuple[PyADTPulseAsync, Any],
    get_mocked_url: Callable[..., str],
    read_file: Callable[..., str],
):
    p, responses = await adt_pulse_instance
    shutdown_event = asyncio.Event()
    task = asyncio.create_task(do_wait_for_update(p, shutdown_event))
    await p.async_logout()
    assert p._sync_task is None
    assert p.site.name == "Robert Lippmann"
    with pytest.raises(PulseNotLoggedInError):
        await task

    # test exceptions
    # check we can't wait for update if not logged in
    with pytest.raises(PulseNotLoggedInError):
        await p.wait_for_update()

    add_signin(LoginType.SUCCESS, responses, get_mocked_url, read_file)
    await p.async_login()
    await p.async_logout()


def make_sync_check_pattern(get_mocked_url):
    return re.compile(rf"{re.escape(get_mocked_url(ADT_SYNC_CHECK_URI))}/?.*$")


@pytest.mark.asyncio
@pytest.mark.parametrize("test_requests", (False, True))
@pytest.mark.timeout(60)
async def test_orb_update(
    adt_pulse_instance: tuple[PyADTPulseAsync, Any],
    get_mocked_url: Callable[..., str],
    read_file: Callable[..., str],
    test_requests: bool,
):
    p, response = await adt_pulse_instance
    pattern = make_sync_check_pattern(get_mocked_url)

    def signal_status_change():
        response.get(
            pattern,
            body=DEFAULT_SYNC_CHECK,
            content_type="text/html",
        )
        response.get(pattern, body="1-0-0", content_type="text/html")
        response.get(pattern, body="2-0-0", content_type="text/html")
        response.get(
            pattern,
            body=NEXT_SYNC_CHECK,
            content_type="text/html",
        )
        response.get(
            pattern,
            body=NEXT_SYNC_CHECK,
            content_type="text/html",
        )

    def open_patio():
        response.get(
            get_mocked_url(ADT_ORB_URI),
            body=read_file("orb_patio_opened.html"),
            content_type="text/html",
        )
        signal_status_change()

    def close_all():
        response.get(
            get_mocked_url(ADT_ORB_URI),
            body=read_file("orb.html"),
            content_type="text/html",
        )
        signal_status_change()

    def open_garage():
        response.get(
            get_mocked_url(ADT_ORB_URI),
            body=read_file("orb_garage.html"),
            content_type="text/html",
        )
        signal_status_change()

    def open_both_garage_and_patio():
        response.get(
            get_mocked_url(ADT_ORB_URI),
            body=read_file("orb_patio_garage.html"),
            content_type="text/html",
        )
        signal_status_change()

    def setup_sync_check():
        open_patio()
        close_all()

    async def test_sync_check_and_orb():
        code, content, _ = await p._pulse_connection.async_query(
            ADT_ORB_URI, requires_authentication=False
        )
        assert code == 200
        assert content == read_file("orb_patio_opened.html")
        await asyncio.sleep(1)
        code, content, _ = await p._pulse_connection.async_query(
            ADT_ORB_URI, requires_authentication=False
        )
        assert code == 200
        assert content == read_file("orb.html")
        await asyncio.sleep(1)
        for _ in range(1):
            code, content, _ = await p._pulse_connection.async_query(
                ADT_SYNC_CHECK_URI, requires_authentication=False
            )
            assert code == 200
            assert content == DEFAULT_SYNC_CHECK
            code, content, _ = await p._pulse_connection.async_query(
                ADT_SYNC_CHECK_URI, requires_authentication=False
            )
            assert code == 200
            assert content == "1-0-0"
            code, content, _ = await p._pulse_connection.async_query(
                ADT_SYNC_CHECK_URI, requires_authentication=False
            )
            assert code == 200
            assert content == "2-0-0"
            code, content, _ = await p._pulse_connection.async_query(
                ADT_SYNC_CHECK_URI, requires_authentication=False
            )
            assert code == 200
            assert content == NEXT_SYNC_CHECK
            code, content, _ = await p._pulse_connection.async_query(
                ADT_SYNC_CHECK_URI, requires_authentication=False
            )
            assert code == 200
            assert content == NEXT_SYNC_CHECK

    # do a first run though to make sure aioresponses will work ok
    if not test_requests:
        setup_sync_check()
        await test_sync_check_and_orb()
        await p.async_logout()
        assert p._sync_task is None
        assert p._timeout_task is None
        return
    await p.async_logout()
    for j in range(2):
        if j == 0:
            zone = 11
        else:
            zone = 10
        for i in range(2):
            if i == 0:
                if j == 0:
                    open_patio()
                else:
                    open_garage()
                state = "Open"
            else:
                close_all()
                state = "OK"
            add_signin(LoginType.SUCCESS, response, get_mocked_url, read_file)
            await p.async_login()
            await p.wait_for_update()
            await p.async_logout()
            assert len(p.site.zones) == 13
            assert p.site.zones_as_dict[zone].state == state
            assert p._sync_task is not None


@pytest.mark.asyncio
async def test_keepalive_check(
    adt_pulse_instance: tuple[PyADTPulseAsync, Any],
    get_mocked_url: Callable[..., str],
    read_file: Callable[..., str],
):
    p, response = await adt_pulse_instance
    assert p._timeout_task is not None
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_infinite_sync_check(
    adt_pulse_instance: tuple[PyADTPulseAsync, Any],
    get_mocked_url: Callable[..., str],
    read_file: Callable[..., str],
):
    p, response = await adt_pulse_instance
    pattern = re.compile(rf"{re.escape(get_mocked_url(ADT_SYNC_CHECK_URI))}/?.*$")
    response.get(
        pattern,
        body=DEFAULT_SYNC_CHECK,
        content_type="text/html",
        repeat=True,
    )
    shutdown_event = asyncio.Event()
    shutdown_event.clear()
    task = asyncio.create_task(do_wait_for_update(p, shutdown_event))
    await asyncio.sleep(5)
    shutdown_event.set()
    task.cancel()
    await task


@pytest.mark.asyncio
async def test_sync_check_errors(
    adt_pulse_instance: tuple[PyADTPulseAsync, Any],
    get_mocked_url: Callable[..., str],
    read_file: Callable[..., str],
    mocker: Callable[..., Generator[MockerFixture, None, None]],
):
    p, response = await adt_pulse_instance
    pattern = re.compile(rf"{re.escape(get_mocked_url(ADT_SYNC_CHECK_URI))}/?.*$")

    shutdown_event = asyncio.Event()
    shutdown_event.clear()
    for test_type in (
        (LoginType.FAIL, PulseAuthenticationError),
        (LoginType.NOT_SIGNED_IN, PulseNotLoggedInError),
        (LoginType.MFA, PulseMFARequiredError),
    ):
        redirect = ADT_LOGIN_URI
        if test_type[0] == LoginType.MFA:
            redirect = ADT_MFA_FAIL_URI
        response.get(
            pattern, status=302, headers={"Location": get_mocked_url(redirect)}
        )
        add_signin(test_type[0], response, get_mocked_url, read_file)
        task = asyncio.create_task(do_wait_for_update(p, shutdown_event))
        with pytest.raises(test_type[1]):
            await task
        await asyncio.sleep(0.5)
        assert p._sync_task is None or p._sync_task.done()
        assert p._timeout_task is None or p._timeout_task.done()
        if test_type[0] == LoginType.MFA:
            # pop the post MFA redirect from the responses
            with pytest.raises(PulseMFARequiredError):
                await p.async_login()
        add_signin(LoginType.SUCCESS, response, get_mocked_url, read_file)
        if test_type[0] != LoginType.LOCKED:
            await p.async_login()


@pytest.mark.asyncio
async def test_multiple_login(
    adt_pulse_instance: tuple[PyADTPulseAsync, Any],
    extract_ids_from_data_directory: list[str],
    get_mocked_url: Callable[..., str],
    read_file: Callable[..., str],
):
    p, response = await adt_pulse_instance
    add_signin(LoginType.SUCCESS, response, get_mocked_url, read_file)
    await p.async_login()
    assert p.site.zones_as_dict is not None
    assert len(p.site.zones_as_dict) == len(extract_ids_from_data_directory) - 3
    add_logout(response, get_mocked_url, read_file)
    await p.async_logout()
    assert p.site.zones_as_dict is not None
    assert len(p.site.zones_as_dict) == len(extract_ids_from_data_directory) - 3
    add_signin(LoginType.SUCCESS, response, get_mocked_url, read_file)
    await p.async_login()
    assert p.site.zones_as_dict is not None
    assert len(p.site.zones_as_dict) == len(extract_ids_from_data_directory) - 3
    add_signin(LoginType.SUCCESS, response, get_mocked_url, read_file)
    assert p.site.zones_as_dict is not None
    assert len(p.site.zones_as_dict) == len(extract_ids_from_data_directory) - 3


@pytest.mark.timeout(180)
@pytest.mark.asyncio
async def test_gateway_offline(
    get_mocked_url: Callable[..., str],
    read_file: Callable[..., str],
    adt_pulse_instance: tuple[PyADTPulseAsync, Any],
):
    p, response = await adt_pulse_instance
    pattern = make_sync_check_pattern(get_mocked_url)
    response.get(
        get_mocked_url(ADT_ORB_URI), body=read_file("orb_gateway_offline.html")
    )
    response.get(
        pattern,
        body=DEFAULT_SYNC_CHECK,
        content_type="text/html",
    )
    response.get(
        pattern,
        body="1-0-0",
        content_type="text/html",
    )
    response.get(
        pattern,
        body=DEFAULT_SYNC_CHECK,
        content_type="text/html",
    )
    response.get(
        pattern,
        body=DEFAULT_SYNC_CHECK,
        content_type="text/html",
    )
    num_backoffs = 3
    for i in range(3):
        response.get(
            pattern,
            body=DEFAULT_SYNC_CHECK,
            content_type="text/html",
        )
    # success case
    response.get(get_mocked_url(ADT_ORB_URI), body=read_file("orb.html"), repeat=True)
    response.get(
        pattern,
        body="1-0-0",
        content_type="text/html",
    )
    response.get(
        pattern, body=DEFAULT_SYNC_CHECK, content_type="text/html", repeat=True
    )
    add_logout(response, get_mocked_url, read_file)
    assert p.site.gateway.poll_interval == 2.0
    # FIXME: why + 2?
    for i in range(num_backoffs + 2):
        with pytest.raises(PulseGatewayOfflineError):
            await p.wait_for_update()

    await p.wait_for_update()
    assert p.site.gateway.is_online
    assert p.site.gateway.backoff.get_current_backoff_interval() == 0

    await p.async_logout()


@pytest.mark.asyncio
async def test_not_logged_in(
    mocked_server_responses: aioresponses,
    get_mocked_url: Callable[..., str],
    read_file: Callable[..., str],
):
    p = PyADTPulseAsync("testuser@example.com", "testpassword", "testfingerprint")
    add_signin(LoginType.SUCCESS, mocked_server_responses, get_mocked_url, read_file)
    add_logout(mocked_server_responses, get_mocked_url, read_file)
    with pytest.raises(PulseNotLoggedInError):
        await p.wait_for_update()
    with pytest.raises(PulseNotLoggedInError):
        await p.wait_for_update()
    await p.async_login()
    await p.async_logout()
    with pytest.raises(PulseNotLoggedInError):
        await p.wait_for_update()
    with pytest.raises(PulseNotLoggedInError):
        await p.wait_for_update()
    add_signin(LoginType.SUCCESS, mocked_server_responses, get_mocked_url, read_file)
    add_logout(mocked_server_responses, get_mocked_url, read_file)
    pattern = make_sync_check_pattern(get_mocked_url)
    mocked_server_responses.get(
        pattern, body=DEFAULT_SYNC_CHECK, content_type="text/html", repeat=True
    )
    mocked_server_responses.get(
        get_mocked_url(ADT_ORB_URI), body=read_file("orb.html"), repeat=True
    )
    await p.async_login()
    task = asyncio.create_task(do_wait_for_update(p, asyncio.Event()))
    await asyncio.sleep(ADT_DEFAULT_POLL_INTERVAL * 5)
    await p.async_logout()
    with pytest.raises(PulseNotLoggedInError):
        await task
    with pytest.raises(PulseNotLoggedInError):
        await p.wait_for_update()
    await asyncio.sleep(ADT_DEFAULT_POLL_INTERVAL * 2)
    with pytest.raises(PulseNotLoggedInError):
        await p.wait_for_update()


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_connection_fails_wait_for_update(
    mocked_server_responses: aioresponses,
    get_mocked_url: Callable[..., str],
    read_file: Callable[..., str],
):
    p = PyADTPulseAsync("testuser@example.com", "testpassword", "testfingerprint")
    add_signin(LoginType.SUCCESS, mocked_server_responses, get_mocked_url, read_file)
    add_logout(mocked_server_responses, get_mocked_url, read_file)
    mocked_server_responses.get(
        get_mocked_url(ADT_ORB_URI), body=read_file("orb.html"), repeat=True
    )
    await p.async_login()
    with pytest.raises(PulseConnectionError):
        await do_wait_for_update(p, asyncio.Event())
    await p.async_logout()


@pytest.mark.timeout(180)
@pytest.mark.asyncio
async def test_sync_check_disconnect(
    adt_pulse_instance: tuple[PyADTPulseAsync, Any],
    read_file: Callable[..., str],
    get_mocked_url: Callable[..., str],
):
    p, responses = await adt_pulse_instance
    add_logout(responses, get_mocked_url, read_file)
    pattern = make_sync_check_pattern(get_mocked_url)
    responses.get(pattern, body=DEFAULT_SYNC_CHECK, content_type="text/html")
    responses.get(get_mocked_url(ADT_ORB_URI), body=read_file("orb.html"), repeat=True)
    while p._pulse_connection_status.get_backoff().get_current_backoff_interval() < 15:
        with pytest.raises(PulseServerConnectionError):
            await p.wait_for_update()
    # check recovery
    responses.get(pattern, body="1-0-0", content_type="text/html")
    responses.get(
        pattern, body=DEFAULT_SYNC_CHECK, content_type="text/html", repeat=True
    )
    await p.wait_for_update()
    await p.async_logout()


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_sync_check_relogin(
    adt_pulse_instance: tuple[PyADTPulseAsync, Any],
    get_mocked_url: Callable[..., str],
    read_file: Callable[..., str],
):
    p, responses = await adt_pulse_instance
    pa: PulseAuthenticationProperties = p._authentication_properties
    login_time = pa.last_login_time
    # fail redirect
    add_signin(LoginType.NOT_SIGNED_IN, responses, get_mocked_url, read_file)
    # successful login afterward
    add_signin(LoginType.SUCCESS, responses, get_mocked_url, read_file)
    add_logout(responses, get_mocked_url, read_file)
    pattern = make_sync_check_pattern(get_mocked_url)
    for _ in range(3):
        responses.get(pattern, body=DEFAULT_SYNC_CHECK, content_type="text/html")
    responses.get(
        pattern,
        body="",
        content_type="text/html",
        status=307,
        headers={"Location": get_mocked_url(ADT_LOGIN_URI)},
    )
    # resume normal operation
    # signal update to stop wait for update
    responses.get(pattern, body="1-0-0", content_type="text/html")
    responses.get(
        pattern, body=DEFAULT_SYNC_CHECK, content_type="text/html", repeat=True
    )
    responses.get(get_mocked_url(ADT_ORB_URI), body=read_file("orb.html"), repeat=True)

    await p.wait_for_update()
    assert p._authentication_properties.last_login_time > login_time
    await p.async_logout()
