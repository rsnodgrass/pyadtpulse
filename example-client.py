#!/usr/local/bin/python3

import os
import sys
import time
import pprint
import logging

from pyadtpulse import PyADTPulse

def setup_logger():
    log_level = logging.DEBUG

    logger = logging.getLogger()
    logger.setLevel(log_level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)

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

        print(f"Changed exist? {site.updates_may_exist}")

        print("\nZones:")
        for zone in site.zones:
            print(zone)

        #site.arm_away()
        #site.arm_home()
        #site.disarm()

    adt.logout

if __name__ == "__main__":
    main()
