#!/usr/bin/env python
"""Sample client for using pyadtpulse."""

import logging
import asyncio
import json
import os
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


def setup_logger(level: int):
    """Set up logger."""
    logger = logging.getLogger()
    logger.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    formatter = logging.Formatter("%(name)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def handle_args() -> Optional[Dict]:
    """Handle program arguments.

    Returns:
        Optional[Dict]: parsed parameters.
    """
    result: Dict = {}

    for curr_arg in sys.argv[1:]:
        if "." in curr_arg:
            f = open(curr_arg, "rb")
            parameters = json.load(f)
            result.update(parameters)
        if "=" in curr_arg:
            curr_value = curr_arg.split("=")
            result.update({curr_value[0]: curr_value[1]})

    if USER not in result:
        result.update({USER: os.getenv(USER.upper(), None)})
    if PASSWD not in result:
        result.update({PASSWD: os.getenv(PASSWD.upper(), None)})
    if FINGERPRINT not in result:
        result.update({FINGERPRINT: os.getenv(FINGERPRINT.upper(), None)})
    if PULSE_DEBUG not in result:
        result.update({PULSE_DEBUG: os.getenv(PULSE_DEBUG, None)})
    return result


def usage() -> None:
    """Print program usage."""
    print(f"Usage {sys.argv[0]}: [json-file]")
    print(f"  {USER.upper()}, {PASSWD.upper()}, and {FINGERPRINT.upper()}")
    print("  must be set either through the json file, or environment variables.")
    print()
    print(f"  Set {PULSE_DEBUG} to True to enable debugging")
    print(f"  Set {TEST_ALARM} to True to test alarm arming/disarming")
    print(f"  Set {SLEEP_INTERVAL} to the number of seconds to sleep between each call")
    print("     Default: 10 seconds")
    print(f"  Set {USE_ASYNC} to true to use asyncio (default: false)")
    print(f"  Set {DEBUG_LOCKS} to true to debug thread locks")
    print()
    print("  values can be passed on the command line i.e.")
    print(f"  {USER}=someone@example.com")


def print_site(site: ADTPulseSite) -> None:
    """Print site information.

    Args:
        site (ADTPulseSite): The site to display
    """
    print(f"Site: {site.name} (id={site.id})")
    print(f"Alarm Status = {site.alarm_control_panel.status}")
    print(f"Disarmed? = {site.alarm_control_panel.is_disarmed}")
    print(f"Armed Away? = {site.alarm_control_panel.is_away}")
    print(f"Armed Home? = {site.alarm_control_panel.is_home}")
    print(f"Force armed? = {site.alarm_control_panel.is_force_armed}")
    print(f"Last updated: {site.last_updated}")


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
    """Run main program.

    Raises:
        SystemExit: Environment variables not set.
    """
    args = None
    if len(sys.argv) > 1:
        if sys.argv[1] == "--help":
            usage()
            sys.exit(0)
        args = handle_args()

    if not args or USER not in args or PASSWD not in args or FINGERPRINT not in args:
        print(f"ERROR! {USER}, {PASSWD}, and {FINGERPRINT} must all be set")
        raise SystemExit

    debug = False
    try:
        debug = bool(args[PULSE_DEBUG])
    except ValueError:
        print(f"{PULSE_DEBUG} must be True or False, defaulting to False")
    except KeyError:
        pass

    if debug:
        level = logging.DEBUG
    else:
        level = logging.ERROR

    run_alarm_test = False
    try:
        run_alarm_test = bool(args[TEST_ALARM])
    except ValueError:
        print(f"{TEST_ALARM} must be True or False, defaulting to False")
    except KeyError:
        pass

    use_async = False
    try:
        use_async = bool(args[USE_ASYNC])
    except ValueError:
        print(f"{USE_ASYNC} must be an boolean, defaulting to False")
    except KeyError:
        pass

    debug_locks = False
    try:
        debug_locks = bool(args[DEBUG_LOCKS])
    except ValueError:
        print(f"{DEBUG_LOCKS} must be an boolean, defaulting to False")
    except KeyError:
        pass

    # don't need to sleep with async
    sleep_interval = 10
    try:
        sleep_interval = int(args[SLEEP_INTERVAL])
    except ValueError:
        if use_async:
            print(f"{SLEEP_INTERVAL} must be an integer, defaulting to 10 seconds")
    except KeyError:
        pass

    setup_logger(level)

    ####

    if not use_async:
        sync_example(
            args[USER],
            args[PASSWD],
            args[FINGERPRINT],
            run_alarm_test,
            sleep_interval,
            debug_locks,
        )
    else:
        asyncio.run(
            async_example(
                args[USER], args[PASSWD], args[FINGERPRINT], run_alarm_test, debug_locks
            )
        )


if __name__ == "__main__":
    main()
