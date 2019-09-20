#!/usr/local/bin/python3

import os
import sys
import pprint
import logging

from pyadtpulse import PyADTPulse

def setup_logger():
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)

    formatter = logging.Formatter('%(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

def main():
    username = os.getenv('ADTPULSE_USER', None)
    password = os.getenv('ADTPULSE_PASSWORD', None)

    if (username == None) or (password == None):
        print("ERROR! Must define env variables ADTPULSE_USER and ADTPULSE_PASSWORD")
        raise SystemExit

    setup_logger()
    pp = pprint.PrettyPrinter(indent = 2)

    ####

    adt = PyADTPulse(username, password)

    for site in adt.sites:
        print("----")
        print(f"Site: {site.name} (id={site.id})")
        print(f"Alarm Status = {site.status}")

        print("\nZones:")
        pp.pprint(site.zones)

        #    site.arm_away()
        #    site.arm_home()
        #    site.disarm()
        print("\n")

    adt.logout

if __name__ == "__main__":
    main()
