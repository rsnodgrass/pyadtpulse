## 1.2.1 (2024-02-07)

* add timing loggin for zone/site updates
* do full logout once per day
* have keepalive task wait for sync check task to sleep before logging out

## 1.2.0 (2024-01-30)

* add exceptions and exception handling
* make code more robust for error handling
* refactor code into smaller objects
* add testing framework
* add poetry

## 1.1.5 (2023-12-22)

* fix more zone html parsing due to changes in Pulse v27

## 1.1.4 (2023-12-13)

* fix zone html parsing due to changes in Pulse v27

## 1.1.3 (2023-10-11)

* revert sync check logic to check against last check value.  this should hopefully fix the problem of HA alarm status not updating
* use exponential backoff for gateway updates if offline instead of constant 90 seconds
* add jitter to relogin interval
* add quick_relogin/async_quick_relogin to do a quick relogin without requerying devices, exiting tasks
* add more alarm testing in example client

## 1.1.2 (2023-10-06)

* change default poll interval to 2 seconds
* update pyproject.toml
* change source location to github/rlippmann from github/rsnodgrass
* fix gateway attributes not updating
* remove dependency on python_dateutils
* add timestamp to example-client logging

## 1.1.1 (2023-10-02)

* pylint fixes
* set min relogin interval
* set max keepalive interval
* remove poll_interval from pyADTPulse constructor
* expose public methods in ADTPulseConnection object

## 1.1 (2023-09-20)

* bug fixes
* relogin support
* device dataclasses

## 1.0 (2023-03-28)

* async support
* background refresh
* bug fixes

## 0.1.0 (2019-12-16)

* added ability to override the ADT API host (example: Canada endpoint portal-ca.adtpulse.com)

## 0.0.6 (2019-09-23)

* bug fixes and improvements

## 0.0.1 (2019-09-19)

* initial release with minimal error/failure handling
