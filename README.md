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

## Developer Note

NOTE: This package use [pre-commit](https://pre-commit.com/) hooks for maintaining code quality.
Please install pre-commit and enable it for your local git copy before committing.

## WARNING

Do not reauthenticate to the ADT service frequently as ADT's service is not designed for high volume requests. E.g. every 5 minutes, not seconds. Keep your authenticated session to avoid logging in repeatedly.

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

- any changes to the name/count of sites are not automatically updated for existing site objects

## Examples

```python
adt = PyADTPulse(username, password, fingerprint)

for site in adt.sites:
    site.status
    site.zones

    site.disarm()
    site.arm_away()
    site.arm_away(force=True)
```

Async version (preferred for new integrations):

```python
adt = PyADTPulse(username, password, fingerprint, do_login=false)

await adt.async_login()

for site in adt.sites:
    site.status
    site.zones

    await site.async_disarm()
    await site.async_arm_away()
    await site.async_arm_away(force=True)
```

The pyadtpulse object runs background tasks and refreshes its data automatically.

Certain parameters can be set to control how often certain actions are run.

Namely:

```python
adt.poll_interval = 0.75  # check for updates every 0.75 seconds
adt.relogin_interval = 60 # relogin every 60 minutes
adt.keepalive_interval = 10 # run keepalive (prevent logout) every 10 minutes
```

See [example-client.py](example-client.py) for a working example.

## Browser Fingerprinting

ADT Pulse requires 2 factor authentication to log into their site. When you perform the 2 factor authentication, you will see an option to save the browser to not have to re-authenticate through it.

Internally, ADT uses some Javascript code to create a browser fingerprint. This (very long) string is used to check that the browser has been saved upon subsequent logins. It is the "fingerprint" parameter required to be passed in to the PyADTPulse object constructor.

### Notes:

The browser fingerprint will change with a browser/OS upgrade.  While it is not strictly necessary to create a separate username/password for logging in through pyadtpulse, it is recommended to do so.

**<ins>Warning:</ins> If another connection is made to the Pulse portal with the same fingerprint, the first connection will be logged out.  For this reason it is recommended to use a browser/machine you would not normally use to log into the Pulse web site to generate the fingerprint.**


There are 2 ways to determine this fingerprint:

1. Visit [this link](https://rawcdn.githack.com/rlippmann/pyadtpulse/b3a0e7097e22446623d170f0a971726fbedb6a2d/doc/browser_fingerprint.html) using the same browser you used to authenticate with ADT Pulse. This should determine the correct browser fingerprint

2. Follow the instructions [here](https://github.com/mrjackyliang/homebridge-adt-pulse#configure-2-factor-authentication)

## See Also

- [ADT Pulse Portal](https://portal.adtpulse.com/)
- [Home Assistant ADT Pulse integration](https://github.com/rsnodgrass/hass-adtpulse/)
- [adt-pulse-mqtt](https://github.com/haruny/adt-pulse-mqtt) – MQTT integration with ADT Pulse alarm panels

## Future Enhancements

Feature ideas:

- 2 factor authenciation
- Cameras (via Janus)

Feature ideas, but no plans to implement:

- support OFFLINE status checking
- support multiple sites (premises/locations) under a single ADT account
  ~~- implement lightweight status pings to check if cache needs to be invalidated (every 5 seconds) (https://portal.adtpulse.com/myhome/16.0.0-131/Ajax/SyncCheckServ?t=1568950496392)~~
- alarm history (/ajax/alarmHistory.jsp)
