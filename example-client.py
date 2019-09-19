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
 
    adt = PyADTPulse(username, password)

    print("\n--Zones--")
    pp.pprint(adt.zones)

#    adt.arm(status='away') # default is away, but can pass state=...'
#    adt.disarm()

    adt.logout

if __name__ == "__main__":
    main()
