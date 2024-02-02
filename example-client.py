#!/usr/bin/env python
"""Sample client for using pyadtpulse."""

import logging
import argparse
import asyncio
import json
import sys
from pprint import pprint
from time import sleep, time

from pyadtpulse import PyADTPulse
from pyadtpulse.const import (
    ADT_DEFAULT_KEEPALIVE_INTERVAL,
    ADT_DEFAULT_POLL_INTERVAL,
    ADT_DEFAULT_RELOGIN_INTERVAL,
    API_HOST_CA,
    DEFAULT_API_HOST,
)
from pyadtpulse.exceptions import (
    PulseAuthenticationError,
    PulseClientConnectionError,
    PulseConnectionError,
    PulseGatewayOfflineError,
    PulseLoginException,
    PulseServerConnectionError,
    PulseServiceTemporarilyUnavailableError,
)
from pyadtpulse.site import ADTPulseSite

USER = "adtpulse_user"
PASSWD = "adtpulse_password"
FINGERPRINT = "adtpulse_fingerprint"
PULSE_DEBUG = "debug"
TEST_ALARM = "test_alarm"
SLEEP_INTERVAL = "sleep_interval"
USE_ASYNC = "use_async"
DEBUG_LOCKS = "debug_locks"
KEEPALIVE_INTERVAL = "keepalive_interval"
RELOGIN_INTERVAL = "relogin_interval"
SERVICE_HOST = "service_host"
POLL_INTERVAL = "poll_interval"
DETAILED_DEBUG_LOGGING = "detailed_debug_logging"

BOOLEAN_PARAMS = {
    USE_ASYNC,
    DEBUG_LOCKS,
    PULSE_DEBUG,
    TEST_ALARM,
    DETAILED_DEBUG_LOGGING,
}
INT_PARAMS = {SLEEP_INTERVAL, KEEPALIVE_INTERVAL, RELOGIN_INTERVAL}
FLOAT_PARAMS = {POLL_INTERVAL}

# Default values
DEFAULT_USE_ASYNC = True
DEFAULT_DEBUG = False
DEFAULT_DETAILED_DEBUG_LOGGING = False
DEFAULT_TEST_ALARM = False
DEFAULT_SLEEP_INTERVAL = 5
DEFAULT_DEBUG_LOCKS = False


# Constants for environment variable names
ENV_USER = "USER"
ENV_PASSWORD = "PASSWORD"
ENV_FINGERPRINT = "FINGERPRINT"


def setup_logger(level: int):
    """Set up logger."""
    logger = logging.getLogger()
    logger.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    formatter = logging.Formatter("%(asctime)s %(name)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def handle_args() -> argparse.Namespace:
    """Handle program arguments using argparse.

    Returns:
        argparse.Namespace: Parsed command-line arguments.
    """
    parser = argparse.ArgumentParser(description="ADT Pulse example client")
    parser.add_argument("json_file", nargs="?", help="JSON file containing parameters")
    parser.add_argument(
        f"--{USER}",
        help="Pulse username (can be set in JSON file or environment variable)",
    )
    parser.add_argument(
        f"--{PASSWD}",
        help="Pulse password (can be set in JSON file or environment variable)",
    )
    parser.add_argument(
        f"--{FINGERPRINT}",
        help="Pulse fingerprint (can be set in JSON file or environment variable)",
    )
    parser.add_argument(
        f"--{SERVICE_HOST}",
        help=f"Pulse service host, must be {DEFAULT_API_HOST} or {API_HOST_CA}, "
        f"default is {DEFAULT_API_HOST}",
    )
    parser.add_argument(
        f"--{PULSE_DEBUG}",
        type=bool,
        default=None,
        help="Set True to enable debugging",
    )
    parser.add_argument(
        f"--{DETAILED_DEBUG_LOGGING}",
        type=bool,
        default=None,
        help="Set True to enable detailed debug logging",
    )
    parser.add_argument(
        f"--{TEST_ALARM}",
        type=bool,
        default=None,
        help="Set True to test alarm arming/disarming",
    )
    parser.add_argument(
        f"--{SLEEP_INTERVAL}",
        type=int,
        default=None,
        help="Number of seconds to sleep between each call "
        f"(default: {DEFAULT_SLEEP_INTERVAL} seconds),"
        " not used for async",
    )
    parser.add_argument(
        f"--{USE_ASYNC}",
        type=bool,
        default=None,
        help=f"Set to true to use asyncio (default: {DEFAULT_USE_ASYNC})",
    )
    parser.add_argument(
        f"--{DEBUG_LOCKS}",
        type=bool,
        default=None,
        help=f"Set to true to debug thread locks, default: {DEFAULT_DEBUG_LOCKS}",
    )
    parser.add_argument(
        f"--{KEEPALIVE_INTERVAL}",
        type=int,
        default=None,
        help="Number of minutes to wait between keepalive calls (default: "
        f"{ADT_DEFAULT_KEEPALIVE_INTERVAL} minutes)",
    )
    parser.add_argument(
        f"--{RELOGIN_INTERVAL}",
        type=int,
        default=None,
        help="Number of minutes to wait between relogin calls "
        f"(default: {ADT_DEFAULT_RELOGIN_INTERVAL} minutes)",
    )

    parser.add_argument(
        f"--{POLL_INTERVAL}",
        type=float,
        default=None,
        help="Number of seconds to wait between polling calls "
        f"(default: {ADT_DEFAULT_POLL_INTERVAL} seconds)",
    )

    args = parser.parse_args()

    json_params = load_parameters_from_json(args.json_file)

    # Update arguments with values from the JSON file
    # load_parameters_from_json() will handle incorrect types
    if json_params is not None:
        for key, value in json_params.items():
            if getattr(args, key) is None and value is not None:
                setattr(args, key, value)

    # Set default values for specific parameters
    args.use_async = args.use_async if args.use_async is not None else DEFAULT_USE_ASYNC
    args.debug_locks = (
        args.debug_locks if args.debug_locks is not None else DEFAULT_DEBUG_LOCKS
    )
    args.debug = args.debug if args.debug is not None else DEFAULT_DEBUG
    args.detailed_debug_logging = (
        args.detailed_debug_logging
        if args.detailed_debug_logging is not None
        else DEFAULT_DETAILED_DEBUG_LOGGING
    )
    args.test_alarm = (
        args.test_alarm if args.test_alarm is not None else DEFAULT_TEST_ALARM
    )
    if args.use_async is False and args.sleep_interval is None:
        args.sleep_interval = DEFAULT_SLEEP_INTERVAL
    args.keepalive_interval = (
        args.keepalive_interval
        if args.keepalive_interval is not None
        else ADT_DEFAULT_KEEPALIVE_INTERVAL
    )
    args.relogin_interval = (
        args.relogin_interval
        if args.relogin_interval is not None
        else ADT_DEFAULT_RELOGIN_INTERVAL
    )
    args.service_host = (
        args.service_host if args.service_host is not None else DEFAULT_API_HOST
    )
    args.poll_interval = (
        args.poll_interval
        if args.poll_interval is not None
        else ADT_DEFAULT_POLL_INTERVAL
    )

    return args


def load_parameters_from_json(json_file: str) -> dict | None:
    """Load parameters from a JSON file.

    Args:
        json_file (str): Path to the JSON file.

    Returns:
        Optional[Dict]: Loaded parameters as a dictionary,
                        or None if there was an error.
    """
    try:
        with open(json_file, encoding="utf-8") as file:
            parameters = json.load(file)
            invalid_keys = []
            for key, value in parameters.items():
                if key in BOOLEAN_PARAMS and not isinstance(value, bool):
                    print(
                        "Invalid boolean value for "
                        f"{key}: {value}"
                        " in JSON file, ignoring..."
                    )
                    invalid_keys.append(key)
                elif key in INT_PARAMS and not isinstance(value, int):
                    print(
                        "Invalid integer value for "
                        f"{key}: {value}"
                        " in JSON file, ignoring..."
                    )
                    invalid_keys.append(key)
                elif (
                    key in FLOAT_PARAMS
                    and not isinstance(value, float)
                    and not isinstance(value, int)
                ):
                    print(
                        "Invalid float value for "
                        f"{key}: {value}"
                        " in JSON file, ignoring..."
                    )
                    invalid_keys.append(key)
            for key in invalid_keys:
                del parameters[key]
            return parameters
    except FileNotFoundError:
        print(f"JSON file not found: {json_file}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")
        return None


def print_site(site: ADTPulseSite) -> None:
    """Print site information.

    Args:
        site (ADTPulseSite): The site to display
    """
    print(f"Site: {site.name} (id={site.id})")
    print("Alarm panel: ")
    pprint(site.alarm_control_panel, compact=True)
    print("Gateway: ")
    pprint(site.gateway, compact=True)


def check_updates(site: ADTPulseSite, adt: PyADTPulse, run_alarm_test: bool) -> bool:
    """Check a site for updates and print details.

    We don't really need to do this anymore, as the data will be
    updated in the background

    Args:
        site (ADTPulseSite): site to check
        adt (PyADTPulse): Pulse connection object
        test_alarm: bool: sleep a bit if testing alarm

        Returns: bool: True if update successful
    """
    if run_alarm_test:
        while (
            site.alarm_control_panel.is_arming or site.alarm_control_panel.is_disarming
        ):
            print(
                f"site is_arming: {site.alarm_control_panel.is_arming}, "
                f"site is_disarming: {site.alarm_control_panel.is_disarming}"
            )
            sleep(1)
    print(f"Gateway online: {adt.site.gateway.is_online}")
    if adt.update():
        print("ADT Data updated, at " f"{site.last_updated}, refreshing")
        return True
    print("Site update failed")
    return False


def test_alarm(site: ADTPulseSite, adt: PyADTPulse) -> None:
    """Test alarm functions.

    Args:
        site (ADTPulseSite): site to test
        adt (PyADTPulse): ADT Pulse connection objecct
        sleep_interval (int): length to sleep between tests
    """
    print("Arming alarm stay")
    if site.arm_home():
        print("Alarm arming home succeeded")
        check_updates(site, adt, True)
        print("Testing invalid alarm state change from armed home to armed away")
        if site.arm_away():
            print("Error, armed away while already armed")
        else:
            print("Test succeeded")
            print("Testing changing alarm status to same value")
            if site.arm_home():
                print("Error, allowed arming to same state")
            else:
                print("Test succeeded")
    else:
        print("Alarm arming home failed, attempting force arm")
        if site.arm_home(True):
            print("Force arm succeeded")
        else:
            print("Force arm failed")

    print()
    print_site(site)

    print("Disarming alarm")
    if site.disarm():
        print("Disarming succeeded")
        check_updates(site, adt, True)
        print("Testing disarming twice")
        if site.disarm():
            print("Test disarm twice suceeded")
        else:
            print("Test disarm twice failed")
    else:
        print("Disarming failed")

    print()
    print_site(site)
    print("Arming alarm away")

    if site.arm_away():
        print("Arm away succeeded")
        check_updates(site, adt, True)
    else:
        print("Arm away failed")

    print()
    print_site(site)
    site.disarm()
    print("Disarmed")


def sync_example(
    username: str,
    password: str,
    fingerprint: str,
    run_alarm_test: bool,
    sleep_interval: int,
    debug_locks: bool,
    poll_interval: float,
    keepalive_interval: int,
    relogin_interval: int,
    detailed_debug_logging: bool,
) -> None:
    """Run example of sync pyadtpulse calls.

    Args:
        username (str): Pulse username
        password (str): Pulse password
        fingerprint (str): Pulse fingerprint
        run_alarm_test (bool): True if alarm test to be run
        sleep_interval (int): how long in seconds to sleep between update checks
        debug_locks: bool: True to enable thread lock debugging
        keepalive_interval (int): keepalive interval in minutes
        relogin_interval (int): relogin interval in minutes
        detailed_debug_logging (bool): True to enable detailed debug logging
    """
    while True:
        try:
            adt = PyADTPulse(
                username,
                password,
                fingerprint,
                debug_locks=debug_locks,
                keepalive_interval=keepalive_interval,
                relogin_interval=relogin_interval,
                detailed_debug_logging=detailed_debug_logging,
            )
            break
        except PulseLoginException as e:
            print(f"ADT Pulse login failed with authentication error: {e}")
            return
        except (PulseClientConnectionError, PulseServerConnectionError) as e:
            backoff_interval = e.backoff.get_current_backoff_interval()
            print(
                f"ADT Pulse login failed with connection error: {e}, retrying in {backoff_interval} seconds"
            )
            sleep(backoff_interval)
            continue
        except PulseServiceTemporarilyUnavailableError as e:
            backoff_interval = e.backoff.expiration_time - time()
            print(
                f"ADT Pulse login failed with service unavailable error: {e}, retrying in {backoff_interval} seconds"
            )
            sleep(backoff_interval)
            continue

    if not adt.is_connected:
        print("Error: Could not log into ADT Pulse site")
        return
    if len(adt.sites) == 0:
        print("Error: could not retrieve sites")
        adt.logout()
        return

    adt.site.site_lock.acquire()
    print(f"Gateway online: {adt.site.gateway.is_online}")
    print_site(adt.site)
    if not adt.site.zones:
        print("Error: no zones exist, exiting")
        adt.site.site_lock.release()
        adt.logout()
        return
    adt.site.gateway.poll_interval = poll_interval
    pprint(adt.site.zones, compact=True)
    adt.site.site_lock.release()
    if run_alarm_test:
        test_alarm(adt.site, adt)

    done = False
    have_exception = False
    while not done:
        try:
            if not have_exception:
                print_site(adt.site)
                print("----")
                if not adt.site.zones:
                    print("Error, no zones exist, exiting...")
                    done = True
                    break
            have_updates = False
            try:
                have_updates = adt.updates_exist
                have_exception = False
            except PulseGatewayOfflineError:
                print("ADT Pulse gateway is offline, re-polling")
                have_exception = True
                continue
            except PulseConnectionError as ex:
                print("ADT Pulse connection error: %s, re-polling", ex.args[0])
                have_exception = True
                continue
            except PulseAuthenticationError as ex:
                print("ADT Pulse authentication error: %s, exiting...", ex.args[0])
                done = True
                break
            if have_updates and not have_exception:
                print("Updates exist, refreshing")
                # Don't need to explicitly call update() anymore
                # Background thread will already have updated
                if not adt.update():
                    print("Error occurred fetching updates, exiting..")
                    done = True
                    break
                print("\nZones:")
                with adt.site.site_lock:
                    pprint(adt.site.zones, compact=True)
            else:
                print("No updates exist")
            sleep(sleep_interval)
        except KeyboardInterrupt:
            print("exiting...")
            done = True

    print("Logging out")
    adt.logout()


async def async_test_alarm(adt: PyADTPulse) -> None:
    """Test alarm functions.

    Args:
        site (ADTPulseSite): site to test
        adt (PyADTPulse): ADT Pulse connection objecct
    """
    print("Arming alarm stay")
    if await adt.site.async_arm_home():
        print("Arming stay call succeeded")
        if adt.site.alarm_control_panel.is_arming:
            print("Arming stay pending check succeeded")
        else:
            print(
                "FAIL: Arming home pending check failed "
                f"{adt.site.alarm_control_panel} "
            )
        await adt.wait_for_update()
        if adt.site.alarm_control_panel.is_home:
            print("Arm stay no longer pending")
        else:
            while not adt.site.alarm_control_panel.is_home:
                pprint(f"FAIL: Arm stay value incorrect {adt.site.alarm_control_panel}")
                await adt.wait_for_update()
        print("Testing invalid alarm state change from armed home to armed away")
        if await adt.site.async_arm_away():
            print(
                f"FAIL: armed away while already armed {adt.site.alarm_control_panel}"
            )
        else:
            print("Test succeeded")
            print("Testing changing alarm status to same value")
            if await adt.site.async_arm_home():
                print(
                    f"FAIL: allowed arming to same state {adt.site.alarm_control_panel}"
                )
            else:
                print("Test succeeded")

    else:
        print("Alarm arming home failed, attempting force arm")
        if await adt.site.async_arm_home(True):
            print("Force arm succeeded")
        else:
            print(f"FAIL: Force arm failed {adt.site.alarm_control_panel}")
    print("Disarming alarm")
    if await adt.site.async_disarm():
        print("Disarming succeeded")
        if adt.site.alarm_control_panel.is_disarming:
            print("Disarm pending success")
        else:
            pprint(f"FAIL: Disarm pending fail {adt.site.alarm_control_panel}")
        await adt.wait_for_update()
        if adt.site.alarm_control_panel.is_disarmed:
            print("Success update to disarm")
        else:
            while not adt.site.alarm_control_panel.is_disarmed:
                pprint(
                    "FAIL: did not set to disarm after update "
                    f"{adt.site.alarm_control_panel}"
                )
                await adt.wait_for_update()
        print("Test finally succeeded")
        print("Testing disarming twice")
        if await adt.site.async_disarm():
            print("Double disarm call succeeded")
        else:
            pprint(f"FAIL: Double disarm call failed {adt.site.alarm_control_panel}")
        if adt.site.alarm_control_panel.is_disarming:
            print("Double disarm state is disarming")
        else:
            pprint(
                "FAIL: Double disarm state is not disarming "
                f"{adt.site.alarm_control_panel}"
            )
        await adt.wait_for_update()
        if adt.site.alarm_control_panel.is_disarmed:
            print("Double disarm success")
        else:
            while not adt.site.alarm_control_panel.is_disarmed:
                pprint(
                    "FAIL: Double disarm state is not disarmed "
                    f"{adt.site.alarm_control_panel}"
                )
                await adt.wait_for_update()
        print("Test finally succeeded")
    else:
        print("Disarming failed")
    print("Arming alarm away")
    if await adt.site.async_arm_away():
        print("Arm away call succeeded")
        if adt.site.alarm_control_panel.is_arming:
            print("Arm away arm pending")
        else:
            pprint(f"FAIL: arm away call not pending {adt.site.alarm_control_panel}")
        await adt.wait_for_update()
        if adt.site.alarm_control_panel.is_away:
            print("Arm away call after update succeed")
        else:
            while not adt.site.alarm_control_panel.is_away:
                pprint(
                    "FAIL: arm away call after update failed "
                    "f{adt.site.alarm_control_panel}"
                )
                await adt.wait_for_update()
        print("Test finally succeeded")
    else:
        print("Arm away failed")
    await adt.site.async_disarm()
    print("Disarmed")


async def async_example(
    username: str,
    password: str,
    fingerprint: str,
    run_alarm_test: bool,
    debug_locks: bool,
    poll_interval: float,
    keepalive_interval: int,
    relogin_interval: int,
    detailed_debug_logging: bool,
) -> None:
    """Run example of pytadtpulse async usage.

    Args:
        username (str): Pulse username
        password (str): Pulse password
        fingerprint (str): Pulse fingerprint
        run_alarm_test (bool): True if alarm tests should be run
        debug_locks (bool): True to enable thread lock debugging
        poll_interval (float): polling interval in seconds
        keepalive_interval (int): keepalive interval in minutes
        relogin_interval (int): relogin interval in minutes
        detailed_debug_logging (bool): enable detailed debug logging
    """
    adt = PyADTPulse(
        username,
        password,
        fingerprint,
        do_login=False,
        debug_locks=debug_locks,
        keepalive_interval=keepalive_interval,
        relogin_interval=relogin_interval,
        detailed_debug_logging=detailed_debug_logging,
    )

    while True:
        try:
            await adt.async_login()
            break
        except PulseLoginException as e:
            print(f"ADT Pulse login failed with authentication error: {e}")
            return
        except (PulseClientConnectionError, PulseServerConnectionError) as e:
            backoff_interval = e.backoff.get_current_backoff_interval()
            print(
                f"ADT Pulse login failed with connection error: {e}, retrying in {backoff_interval} seconds"
            )
            await asyncio.sleep(backoff_interval)
            continue
        except PulseServiceTemporarilyUnavailableError as e:
            backoff_interval = e.backoff.expiration_time - time()
            print(
                f"ADT Pulse login failed with service unavailable error: {e}, retrying in {backoff_interval} seconds"
            )
            await asyncio.sleep(backoff_interval)
            continue

    if not adt.is_connected:
        print("Error: could not log into ADT Pulse site")
        return

    if adt.site is None:
        print("Error: could not retrieve sites")
        await adt.async_logout()
        return

    print_site(adt.site)
    if adt.site.zones is None:
        print("Error: no zones exist")
        await adt.async_logout()
        return
    adt.site.gateway.poll_interval = poll_interval
    pprint(adt.site.zones, compact=True)
    if run_alarm_test:
        await async_test_alarm(adt)

    done = False
    have_exception = False
    while not done:
        try:
            if not have_exception:
                print(f"Gateway online: {adt.site.gateway.is_online}")
                print_site(adt.site)
                print("----")
                if not adt.site.zones:
                    print("No zones exist, exiting...")
                    done = True
                    break
                print("\nZones:")
                pprint(adt.site.zones, compact=True)
            try:
                await adt.wait_for_update()
                have_exception = False
            except PulseGatewayOfflineError as ex:
                print(
                    f"ADT Pulse gateway is offline, re-polling in {ex.backoff.get_current_backoff_interval()}"
                )
                have_exception = True
                continue
            except (PulseClientConnectionError, PulseServerConnectionError) as ex:
                print(
                    f"ADT Pulse connection error: {ex.args[0]}, re-polling in {ex.backoff.get_current_backoff_interval()}"
                )
                have_exception = True
                continue
            except PulseAuthenticationError as ex:
                print("ADT Pulse authentication error: %s, exiting...", ex.args[0])
                done = True
                break
            print("Updates exist, refreshing")
        # no need to call an update method
        except KeyboardInterrupt:
            print("exiting...")
            done = True

    print("Logging out")
    await adt.async_logout()


def main():
    """Run main program."""
    args = handle_args()

    if not args or not any(
        [args.adtpulse_user, args.adtpulse_password, args.adtpulse_fingerprint]
    ):
        print(f"ERROR! {USER}, {PASSWD}, and {FINGERPRINT} must all be set")
        raise SystemExit

    if args.debug:
        level = logging.DEBUG
    else:
        level = logging.ERROR

    use_async = args.use_async

    setup_logger(level)

    if not use_async:
        sync_example(
            args.adtpulse_user,
            args.adtpulse_password,
            args.adtpulse_fingerprint,
            args.test_alarm,
            args.sleep_interval,
            args.debug_locks,
            args.poll_interval,
            args.keepalive_interval,
            args.relogin_interval,
            args.detailed_debug_logging,
        )
    else:
        asyncio.run(
            async_example(
                args.adtpulse_user,
                args.adtpulse_password,
                args.adtpulse_fingerprint,
                args.test_alarm,
                args.debug_locks,
                args.poll_interval,
                args.keepalive_interval,
                args.relogin_interval,
                args.detailed_debug_logging,
            )
        )


if __name__ == "__main__":
    main()
