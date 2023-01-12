#!/usr/local/bin/python3

import os
import sys
import logging
import json
from typing import Dict, Optional

from pyadtpulse import PyADTPulse

USER = 'adtpulse_user'
PASSWD = 'adtpulse_password'
FINGERPRINT = 'adtpulse_fingerprint'

def setup_logger():
    """Set up logger."""
    log_level = logging.DEBUG

    logger = logging.getLogger()
    logger.setLevel(log_level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)

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

    return result


def main():
    """Run main program.

    Raises:
        SystemExit: Environment variables not set.
    """
    if sys.argv[1] == "--help":
        print(f"Usage {sys.argv[0]}: [json-file]")
        print(f"  {USER.upper()}, {PASSWD.upper()}, and {FINGERPRINT.upper()}")
        print("  must be set either through the json file, or environment variables.")
        print("")
        print("  values can be passed on the command line i.e.")
        print(f"  {USER}=someone@example.com")
        sys.exit(0)
    args = handle_args()

    if (
        not args
        or USER not in args
        or PASSWD not in args
        or FINGERPRINT not in args
    ):
        print(
            f"ERROR! {USER}, {PASSWD}, and {FINGERPRINT} must all be set"
        )
        raise SystemExit

    setup_logger()

    ####

    adt = PyADTPulse(
        args[USER], args[PASSWD], args[FINGERPRINT]
    )

    #    for i in range(20):
    #        print(f"{i} Updated exists? {adt.updates_exist}")
    #        time.sleep(60)

    for site in adt.sites:
        print("----")
        print(f"Site: {site.name} (id={site.id})")
        print(f"Alarm Status = {site.status}")

        print(f"Disarmed? = {site.is_disarmed}")
        print(f"Armed Away? = {site.is_away}")
        print(f"Armed Home? = {site.is_home}")

        print(f"Changes exist? {site.updates_may_exist}")

        print("\nZones:")
        for zone in site.zones:
            print(zone)

        # site.arm_away()
        # site.arm_home()
        # site.disarm()

    adt.logout


if __name__ == "__main__":
    main()
