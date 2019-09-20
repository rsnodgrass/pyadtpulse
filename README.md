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

## Examples

```python
adt = PyADTPulse(username, password)

adt.panel
adt.zones
```

See also [example-client.py](example-client.py) for a working example.

## See Also

* [ADT Pulse Portal](https://portal.adtpulse.com/)

## Future Enhancements

* support multiple premises (locations) under a single ADT account
* arm/disarm and current status
* current state for all sensors
* alarm history (from /ajax/alarmHistory.jsp)
