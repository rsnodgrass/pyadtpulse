# pyadtpulse - Python interface for ADT Pulse

Python client interface to the ADT Pulse security system.

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Donate](https://img.shields.io/badge/Donate-PayPal-green.svg)](https://www.paypal.com/cgi-bin/webscr?cmd=_donations&business=WREP29UDAMB6G)

NOTE: Since this interacts with the ADT Pulse AJAX web service, it is dependent on the
behavior of the production ADT websute and thus behavior is subject to change without notice.

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
* Home Assistant ADT Pulse integration

## Future Enhancements

* arm/disarm
* support multiple sites (premises/locations) under a single ADT account
* implement lightweight status pings to check if cache needs to be invalidated (every 5 seconds) (https://portal.adtpulse.com/myhome/16.0.0-131/Ajax/SyncCheckServ?t=1568950496392)
* alarm history (/ajax/alarmHistory.jsp)
