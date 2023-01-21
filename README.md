# pyadtpulse - Python interface for ADT Pulse

Python client interface to the ADT Pulse security system.

[![PyPi](https://img.shields.io/pypi/v/pyadtpulse.svg)](https://pypi.python.org/pypi/pyadtpulse)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Donate](https://img.shields.io/badge/Donate-PayPal-green.svg)](https://www.paypal.com/cgi-bin/webscr?cmd=_donations&business=WREP29UDAMB6G)

## UNSUPPORTED

**This is an unsupported interface provided only as a basis for others to explore integrating
their ADT system wtih their own tools.**

While two or three Python clients to ADT Pulse existed, they generally only provided
arm/disarm support and none provided support for ADT Pulse when multiple sites existed
under a single account. This attempts to provide APIs to both all the zones (motion 
sensors, door sensors, etc) as well as arming and disarming individual sites.

NOTE: Since this interacts with the unofficial ADT Pulse AJAX web service, the
behavior is subject to change by ADT without notice.

## WARNING

Do not refresh status of sensors often as the ADT service is not designed for high volume requests. E.g. updating every 5 minutes, not seconds. Keep your authenticated session to avoid logging in repeatedly.

## Installation

```
pip3 install pyadtpulse
```

## Usage

Since ADT Pulse automatically logs out other sessions accessing the same account, a best practice is
to **create a new username/password combination for each client** accessing ADT Pulse.

Additionally, since pyadtpulse currently does not support multiple sites (premises/locations), a
simple approach is to create a separate username/password for each site and configured such that
the username only has access to ONE site. This ensures that clients are always interacting with
that one site (and not accidentally with another site location).

#### Notes

* any changes to the name/count of sites are not automatically updated for existing site objects 

## Examples

```python
adt = PyADTPulse(username, password)

for site in adt.sites:
    site.status
    site.zones

    site.disarm()
    site.arm_away()
```

See [example-client.py](example-client.py) for a working example.

## See Also

* [ADT Pulse Portal](https://portal.adtpulse.com/)
* [Home Assistant ADT Pulse integration](https://github.com/rsnodgrass/hass-adtpulse/)
* [adt-pulse-mqtt](https://github.com/haruny/adt-pulse-mqtt) – MQTT integration with ADT Pulse alarm panels

## Future Enhancements

Feature ideas, but no plans to implement:

* support OFFLINE status checking
* support multiple sites (premises/locations) under a single ADT account
* implement lightweight status pings to check if cache needs to be invalidated (every 5 seconds) (https://portal.adtpulse.com/myhome/16.0.0-131/Ajax/SyncCheckServ?t=1568950496392)
* alarm history (/ajax/alarmHistory.jsp)


