"""Python class representing an ADT Pulse zone."""

import logging
from pyadtpulse.const import ( ADT_ZONES_URI )

LOG = logging.getLogger(__name__)

def assert_is_dict(var):
    """Assert variable is from the type dictionary."""
    if var is None or not isinstance(var, dict):
        return {}
    return var


class ADTZone(object):
    """ADT Pulse zone implementation."""

    def __init__(self, name, attrs, adtpulse_session):
        """Initialize ADT zone object.
        :param name: zone name
        :param attrs: zone attributes
        :param adtpulse_session: PyADTPulse session
        """
        self.name = name
        self._attrs = attrs
        self._session = adtpulse_session

        # make sure self._attrs is a dict
        self._attrs = assert_is_dict(self._attrs)

    def __repr__(self):
        """Representation string of object."""
        return "<{0}: {1}>".format(self.__class__.__name__, self.name)

    @property
    def attrs(self):
        """Return zone attributes."""
        return self._attrs

    @attrs.setter
    def attrs(self, value):
        """Override zones attributes."""
        self._attrs = value

    def update(self):
        """Update object properties."""
        self._attrs = self._session.refresh_attributes(self.name)
        self._attrs = assert_is_dict(self._attrs)

# id
# name
# tags
# state
# status text
# last activity timestamp

 #   {
 #     "state": {
 #       "icon": "devStatOK",
 #       "statusTxt": "South Office Door - Closed\nLast Activity: 10/31 11:20 AM",
 #       "activityTs": 1509474015194
 #     },
 #     "deprecatedAction": "launchDetailsWindow('U291dGggT2ZmaWNlIERvb3I=','672')",
 #     "id": "sensor-4",
 #     "devIndex": "E5VER1",
 #     "name": "South Office Door",
 #     "tags": "sensor,doorWindow"
 #   },
