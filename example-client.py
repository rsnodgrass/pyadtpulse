#!/usr/bin/env python

import logging
import json
import os
import sys
from time import sleep
from typing import Dict, Optional

from pyadtpulse import PyADTPulse
from pyadtpulse.site import ADTPulseSite

USER = "adtpulse_user"
PASSWD = "adtpulse_password"
FINGERPRINT = "adtpulse_fingerprint"
PULSE_DEBUG = "debug"


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

    if PULSE_DEBUG in result:
        result.update({PULSE_DEBUG: str(result[PULSE_DEBUG])})
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
    print("")
    print(f"  Set {PULSE_DEBUG} to True to enable debugging")
    print("")
    print("  values can be passed on the command line i.e.")
    print(f"  {USER}=someone@example.com")


def print_site(site: ADTPulseSite) -> None:
    """Print site information.

    Args:
        site (ADTPulseSite): The site to display
    """
    print(f"Site: {site.name} (id={site.id})")
    print(f"Alarm Status = {site.status}")
    print(f"Disarmed? = {site.is_disarmed}")
    print(f"Armed Away? = {site.is_away}")
    print(f"Armed Home? = {site.is_home}")


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

    if args and args[PULSE_DEBUG].casefold() == "True".casefold():
        level = logging.DEBUG
    else:
        level = logging.ERROR

    setup_logger(level)

    ####

    adt = PyADTPulse(args[USER], args[PASSWD], args[FINGERPRINT])

    done = False

    while not done:
        try:
            for site in adt.sites:
                print_site(site)
                print("----")
                if site.updates_may_exist():
                    print("Updates exist, refreshing")
                    if not adt.update():
                        print("Error occurred fetching updates, exiting..")
                        done = True
                        break
                    print("\nZones:")
                    for zone in site.zones:
                        print(zone)
                else:
                    print("No updates exist")

            sleep(10)

        except KeyboardInterrupt:
            print("exiting...")
            done = True

    print("Logging out")
    adt.logout


if __name__ == "__main__":
    main()
