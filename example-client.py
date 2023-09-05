#!/usr/bin/env python
"""Sample client for using pyadtpulse."""

import logging
import argparse
import asyncio
import json
import sys
from time import sleep
from typing import Dict, Optional

from pyadtpulse import PyADTPulse
from pyadtpulse.site import ADTPulseSite
from pyadtpulse.util import AuthenticationException

USER = "adtpulse_user"
PASSWD = "adtpulse_password"
FINGERPRINT = "adtpulse_fingerprint"
PULSE_DEBUG = "debug"
TEST_ALARM = "test_alarm"
SLEEP_INTERVAL = "sleep_interval"
USE_ASYNC = "use_async"
DEBUG_LOCKS = "debug_locks"

BOOLEAN_PARAMS = {USE_ASYNC, DEBUG_LOCKS, PULSE_DEBUG, TEST_ALARM}
INT_PARAMS = {SLEEP_INTERVAL}

# Default values
DEFAULT_USE_ASYNC = True
DEFAULT_DEBUG = False
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

    formatter = logging.Formatter("%(name)s - %(levelname)s - %(message)s")
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
        f"--{PULSE_DEBUG}",
        type=bool,
        default=None,
        help="Set True to enable debugging",
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
        help="Number of seconds to sleep between each call (default: 10 seconds)",
    )
    parser.add_argument(
        f"--{USE_ASYNC}",
        type=bool,
        default=None,
        help="Set to true to use asyncio (default: true)",
    )
    parser.add_argument(
        f"--{DEBUG_LOCKS}",
        type=bool,
        default=None,
        help="Set to true to debug thread locks",
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
    if args.use_async is None:
        args.use_async = DEFAULT_USE_ASYNC
    if args.debug_locks is None:
        args.debug_locks = DEFAULT_DEBUG_LOCKS
    if args.debug is None:
        args.debug = DEFAULT_DEBUG
    if args.sleep_interval is None:
        args.sleep_interval = DEFAULT_SLEEP_INTERVAL
    return args


def load_parameters_from_json(json_file: str) -> Optional[Dict]:
    """Load parameters from a JSON file.

    Args:
        json_file (str): Path to the JSON file.

    Returns:
        Optional[Dict]: Loaded parameters as a dictionary,
                        or None if there was an error.
    """
    try:
        with open(json_file) as file:
            parameters = json.load(file)
            for key, value in parameters.items():
                if key in BOOLEAN_PARAMS:
                    if not isinstance(value, bool):
                        print(
                            "Invalid boolean value for "
                            f"{key}: {value}"
                            " in JSON file, ignoring..."
                        )
                        parameters.pop(key)
                elif key in INT_PARAMS:
                    if not isinstance(value, int):
                        print(
                            "Invalid integer value for "
                            f"{key}: {value}"
                            " in JSON file, ignoring..."
                        )
                        parameters.pop(key)
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
    print(f"Alarm Model: {site.alarm_control_panel.model}")
    print(f"Manufacturer: {site.alarm_control_panel.manufacturer}")
    print(f"Alarm Online? = {site.alarm_control_panel.online}")
    print(f"Alarm Status = {site.alarm_control_panel.status}")
    print(f"Disarmed? = {site.alarm_control_panel.is_disarmed}")
    print(f"Armed Away? = {site.alarm_control_panel.is_away}")
    print(f"Armed Home? = {site.alarm_control_panel.is_home}")
    print(f"Force armed? = {site.alarm_control_panel.is_force_armed}")
    print(f"Last updated: {site.last_updated}")
    print()
    print(f"Gateway: {site.gateway}")


def check_updates(site: ADTPulseSite, adt: PyADTPulse, test_alarm: bool) -> bool:
    """Check a site for updates and print details.

    We don't really need to do this anymore, as the data will be
    updated in the background

    Args:
        site (ADTPulseSite): site to check
        adt (PyADTPulse): Pulse connection object
        test_alarm: bool: sleep a bit if testing alarm

        Returns: bool: True if update successful
    """
    if test_alarm:
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


def test_alarm(site: ADTPulseSite, adt: PyADTPulse, sleep_interval: int) -> None:
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
            print("Test disarm twice failed")
        else:
            print("Test succeeded")
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
) -> None:
    """Run example of sync pyadtpulse calls.

    Args:
        username (str): Pulse username
        password (str): Pulse password
        fingerprint (str): Pulse fingerprint
        run_alarm_test (bool): True if alarm test to be run
        sleep_interval (int): how long in seconds to sleep between update checks
        debug_locks: bool: True to enable thread lock debugging
    """
    try:
        adt = PyADTPulse(username, password, fingerprint, debug_locks=debug_locks)
    except AuthenticationException:
        print("Invalid credentials for ADT Pulse site")
        sys.exit()
    except BaseException as e:
        print("Received exception logging into ADT Pulse site")
        print(f"{e}")
        sys.exit()

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
    for zone in adt.site.zones:
        print(zone)
    adt.site.site_lock.release()
    if run_alarm_test:
        test_alarm(adt.site, adt, sleep_interval)

    done = False
    while not done:
        try:
            print_site(adt.site)
            print("----")
            if not adt.site.zones:
                print("Error, no zones exist, exiting...")
                done = True
                break
            if adt.updates_exist:
                print("Updates exist, refreshing")
                # Don't need to explicitly call update() anymore
                # Background thread will already have updated
                if not adt.update():
                    print("Error occurred fetching updates, exiting..")
                    done = True
                    break
                print("\nZones:")
                with adt.site.site_lock:
                    for zone in adt.site.zones:
                        print(zone)
                    print(f"{adt.site.zones_as_dict}")
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
        print("Alarm arming home succeeded")
        #        check_updates(site, adt, False)
        print("Testing invalid alarm state change from armed home to armed away")
        if await adt.site.async_arm_away():
            print("Error, armed away while already armed")
        else:
            print("Test succeeded")
            print("Testing changing alarm status to same value")
            if await adt.site.async_arm_home():
                print("Error, allowed arming to same state")
            else:
                print("Test succeeded")

    else:
        print("Alarm arming home failed, attempting force arm")
        if await adt.site.async_arm_home(True):
            print("Force arm succeeded")
        else:
            print("Force arm failed")

    print()
    print_site(adt.site)

    print("Disarming alarm")
    if await adt.site.async_disarm():
        print("Disarming succeeded")
        #        check_updates(site, adt, False)
        print("Testing disarming twice")
        if await adt.site.async_disarm():
            print("Test failed")
        else:
            print("Test succeeded")
    else:
        print("Disarming failed")

    print()
    print_site(adt.site)
    print("Arming alarm away")

    if await adt.site.async_arm_away():
        print("Arm away succeeded")
    #        check_updates(site, adt, False)
    else:
        print("Arm away failed")

    print()
    print_site(adt.site)
    await adt.site.async_disarm()
    print("Disarmed")


async def async_example(
    username: str,
    password: str,
    fingerprint: str,
    run_alarm_test: bool,
    debug_locks: bool,
) -> None:
    """Run example of pytadtpulse async usage.

    Args:
        username (str): Pulse username
        password (str): Pulse password
        fingerprint (str): Pulse fingerprint
        run_alarm_test (bool): True if alarm tests should be run
        debug_locks (bool): True to enable thread lock debugging
    """
    adt = PyADTPulse(
        username, password, fingerprint, do_login=False, debug_locks=debug_locks
    )

    if not await adt.async_login():
        print("ADT Pulse login failed")
        return

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

    for zone in adt.site.zones:
        print(zone)
    if run_alarm_test:
        await async_test_alarm(adt)

    done = False
    while not done:
        try:
            print(f"Gateway online: {adt.site.gateway.is_online}")
            print_site(adt.site)
            print("----")
            if not adt.site.zones:
                print("No zones exist, exiting...")
                done = True
                break
            print("\nZones:")
            for zone in adt.site.zones:
                print(zone)
                #               print(f"{site.zones_as_dict}")

            await adt.wait_for_update()
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

    debug = args.debug
    if debug:
        level = logging.DEBUG
    else:
        level = logging.ERROR

    run_alarm_test = args.test_alarm
    use_async = args.use_async
    debug_locks = args.debug_locks
    sleep_interval = args.sleep_interval

    setup_logger(level)

    if not use_async:
        sync_example(
            args.adtpulse_user,
            args.adtpulse_password,
            args.adtpulse_fingerprint,
            run_alarm_test,
            sleep_interval,
            debug_locks,
        )
    else:
        asyncio.run(
            async_example(
                args.adtpulse_user,
                args.adtpulse_password,
                args.adtpulse_fingerprint,
                run_alarm_test,
                debug_locks,
            )
        )


if __name__ == "__main__":
    main()
