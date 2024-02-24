"""Test Pulse Connection."""

import asyncio
import datetime

import pytest
from lxml import html

from conftest import LoginType, add_custom_response, add_signin
from pyadtpulse.const import ADT_LOGIN_URI, DEFAULT_API_HOST
from pyadtpulse.exceptions import (
    PulseAccountLockedError,
    PulseAuthenticationError,
    PulseMFARequiredError,
    PulseServerConnectionError,
)
from pyadtpulse.pulse_authentication_properties import PulseAuthenticationProperties
from pyadtpulse.pulse_connection import PulseConnection
from pyadtpulse.pulse_connection_properties import PulseConnectionProperties
from pyadtpulse.pulse_connection_status import PulseConnectionStatus
from pyadtpulse.pulse_query_manager import MAX_REQUERY_RETRIES


def setup_pulse_connection() -> PulseConnection:
    s = PulseConnectionStatus()
    pcp = PulseConnectionProperties(DEFAULT_API_HOST)
    pa = PulseAuthenticationProperties(
        "test@example.com", "testpassword", "testfingerprint"
    )
    pc = PulseConnection(s, pcp, pa)
    return pc


@pytest.mark.asyncio
async def test_login(mocked_server_responses, read_file, mock_sleep, get_mocked_url):
    """Test Pulse Connection."""
    pc = setup_pulse_connection()
    add_signin(LoginType.SUCCESS, mocked_server_responses, get_mocked_url, read_file)
    # first call to signin post is successful in conftest.py
    result = await pc.async_do_login_query()
    assert result is not None
    assert html.tostring(result) == read_file("summary.html")
    assert mock_sleep.call_count == 0
    assert pc.login_in_progress is False
    assert pc._login_backoff.backoff_count == 0
    assert pc._connection_status.authenticated_flag.is_set()
    # so logout won't fail
    add_custom_response(
        mocked_server_responses, read_file, get_mocked_url(ADT_LOGIN_URI)
    )
    await pc.async_do_logout_query()
    assert not pc._connection_status.authenticated_flag.is_set()
    assert mock_sleep.call_count == 0
    assert pc._login_backoff.backoff_count == 0


@pytest.mark.asyncio
async def test_login_failure_server_down(mock_server_down):
    pc = setup_pulse_connection()
    with pytest.raises(PulseServerConnectionError):
        await pc.async_do_login_query()
    assert pc.login_in_progress is False
    assert pc._login_backoff.backoff_count == 0


@pytest.mark.asyncio
async def test_multiple_login(
    mocked_server_responses, get_mocked_url, read_file, mock_sleep
):
    """Test Pulse Connection."""
    pc = setup_pulse_connection()
    add_signin(LoginType.SUCCESS, mocked_server_responses, get_mocked_url, read_file)
    result = await pc.async_do_login_query()
    assert result is not None
    assert html.tostring(result) == read_file("summary.html")
    assert mock_sleep.call_count == 0
    assert pc.login_in_progress is False
    assert pc._login_backoff.backoff_count == 0
    assert pc._connection_status.authenticated_flag.is_set()
    add_signin(LoginType.SUCCESS, mocked_server_responses, get_mocked_url, read_file)
    await pc.async_do_login_query()
    assert mock_sleep.call_count == 0
    assert pc.login_in_progress is False
    assert pc._login_backoff.backoff_count == 0
    assert pc._connection_status.get_backoff().backoff_count == 0
    assert pc._connection_status.authenticated_flag.is_set()
    # this should fail
    with pytest.raises(PulseServerConnectionError):
        await pc.async_do_login_query()
    assert mock_sleep.call_count == MAX_REQUERY_RETRIES - 1
    assert pc.login_in_progress is False
    assert pc._login_backoff.backoff_count == 0
    assert pc._connection_status.get_backoff().backoff_count == 1
    assert not pc._connection_status.authenticated_flag.is_set()
    assert not pc.is_connected
    with pytest.raises(PulseServerConnectionError):
        await pc.async_do_login_query()
    assert pc._login_backoff.backoff_count == 0
    # 2 retries first time, 1 for the connection backoff
    assert mock_sleep.call_count == MAX_REQUERY_RETRIES
    assert pc.login_in_progress is False

    assert pc._connection_status.get_backoff().backoff_count == 2
    assert not pc._connection_status.authenticated_flag.is_set()
    assert not pc.is_connected
    add_signin(LoginType.SUCCESS, mocked_server_responses, get_mocked_url, read_file)
    await pc.async_do_login_query()
    # will just to a connection backoff
    assert mock_sleep.call_count == MAX_REQUERY_RETRIES + 1
    assert pc.login_in_progress is False
    assert pc._login_backoff.backoff_count == 0
    assert pc._connection_status.authenticated_flag.is_set()

    add_signin(LoginType.SUCCESS, mocked_server_responses, get_mocked_url, read_file)
    await pc.async_do_login_query()
    # shouldn't sleep at all
    assert mock_sleep.call_count == MAX_REQUERY_RETRIES + 1
    assert pc.login_in_progress is False
    assert pc._login_backoff.backoff_count == 0
    assert pc._connection_status.authenticated_flag.is_set()


@pytest.mark.asyncio
async def test_account_lockout(
    mocked_server_responses, mock_sleep, get_mocked_url, read_file, freeze_time_to_now
):
    pc = setup_pulse_connection()
    add_signin(LoginType.SUCCESS, mocked_server_responses, get_mocked_url, read_file)
    await pc.async_do_login_query()
    assert mock_sleep.call_count == 0
    assert pc.login_in_progress is False
    assert pc._login_backoff.backoff_count == 0
    assert pc.is_connected
    assert pc._connection_status.authenticated_flag.is_set()
    add_signin(LoginType.LOCKED, mocked_server_responses, get_mocked_url, read_file)
    with pytest.raises(PulseAccountLockedError):
        await pc.async_do_login_query()
    # won't sleep yet
    assert not pc.is_connected
    assert not pc._connection_status.authenticated_flag.is_set()
    # don't set backoff on locked account, just set expiration time on backoff
    assert pc._login_backoff.backoff_count == 0
    assert mock_sleep.call_count == 0
    freeze_time_to_now.tick(delta=datetime.timedelta(seconds=(60 * 30) + 1))
    add_signin(LoginType.SUCCESS, mocked_server_responses, get_mocked_url, read_file)
    await pc.async_do_login_query()
    assert mock_sleep.call_count == 0
    assert pc.is_connected
    assert pc._connection_status.authenticated_flag.is_set()
    freeze_time_to_now.tick(delta=datetime.timedelta(seconds=60 * 30 + 1))
    add_signin(LoginType.LOCKED, mocked_server_responses, get_mocked_url, read_file)
    with pytest.raises(PulseAccountLockedError):
        await pc.async_do_login_query()
    assert pc._login_backoff.backoff_count == 0
    assert mock_sleep.call_count == 0


@pytest.mark.asyncio
async def test_invalid_credentials(
    mocked_server_responses, mock_sleep, get_mocked_url, read_file
):
    pc = setup_pulse_connection()
    add_signin(LoginType.SUCCESS, mocked_server_responses, get_mocked_url, read_file)
    await pc.async_do_login_query()
    assert mock_sleep.call_count == 0
    assert pc.login_in_progress is False
    assert pc._login_backoff.backoff_count == 0
    add_signin(LoginType.FAIL, mocked_server_responses, get_mocked_url, read_file)
    with pytest.raises(PulseAuthenticationError):
        await pc.async_do_login_query()
    assert pc._login_backoff.backoff_count == 0
    assert mock_sleep.call_count == 0
    add_signin(LoginType.FAIL, mocked_server_responses, get_mocked_url, read_file)

    with pytest.raises(PulseAuthenticationError):
        await pc.async_do_login_query()
    assert pc._login_backoff.backoff_count == 0
    assert mock_sleep.call_count == 0
    add_signin(LoginType.SUCCESS, mocked_server_responses, get_mocked_url, read_file)
    assert pc._login_backoff.backoff_count == 0
    assert mock_sleep.call_count == 0


@pytest.mark.asyncio
async def test_mfa_failure(mocked_server_responses, get_mocked_url, read_file):
    pc = setup_pulse_connection()
    add_signin(LoginType.SUCCESS, mocked_server_responses, get_mocked_url, read_file)
    await pc.async_do_login_query()
    assert pc.login_in_progress is False
    assert pc._login_backoff.backoff_count == 0
    add_signin(LoginType.MFA, mocked_server_responses, get_mocked_url, read_file)
    with pytest.raises(PulseMFARequiredError):
        await pc.async_do_login_query()
    assert pc._login_backoff.backoff_count == 0
    add_signin(LoginType.MFA, mocked_server_responses, get_mocked_url, read_file)
    with pytest.raises(PulseMFARequiredError):
        await pc.async_do_login_query()
    assert pc._login_backoff.backoff_count == 0
    add_signin(LoginType.SUCCESS, mocked_server_responses, get_mocked_url, read_file)
    await pc.async_do_login_query()
    assert pc._login_backoff.backoff_count == 0


@pytest.mark.asyncio
async def test_only_single_login(mocked_server_responses, get_mocked_url, read_file):
    async def login_task():
        await pc.async_do_login_query()

    pc = setup_pulse_connection()
    add_signin(LoginType.SUCCESS, mocked_server_responses, get_mocked_url, read_file)
    # delay one task for a little bit
    for i in range(4):
        pc._login_backoff.increment_backoff()
    task1 = asyncio.create_task(login_task())
    task2 = asyncio.create_task(login_task())
    await task2
    assert pc.login_in_progress
    assert not pc.is_connected
    assert not task1.done()
    await task1
    assert not pc.login_in_progress
    assert pc.is_connected
