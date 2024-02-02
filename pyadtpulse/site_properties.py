"""Pulse Site Properties."""

from threading import RLock
from warnings import warn

from typeguard import typechecked

from .alarm_panel import ADTPulseAlarmPanel
from .gateway import ADTPulseGateway
from .util import DebugRLock, set_debug_lock
from .zones import ADTPulseFlattendZone, ADTPulseZones


class ADTPulseSiteProperties:
    """Pulse Site Properties."""

    __slots__ = (
        "_id",
        "_name",
        "_last_updated",
        "_alarm_panel",
        "_zones",
        "_site_lock",
        "_gateway",
    )

    @typechecked
    def __init__(self, site_id: str, name: str, debug_locks: bool = False):
        self._id = site_id
        self._name = name
        self._last_updated: int = 0
        self._zones = ADTPulseZones()
        self._site_lock: RLock | DebugRLock
        self._site_lock = set_debug_lock(debug_locks, "pyadtpulse.site_property_lock")
        self._alarm_panel = ADTPulseAlarmPanel()
        self._gateway = ADTPulseGateway()

    @property
    def id(self) -> str:
        """Get site id.

        Returns:
            str: the site id
        """
        return self._id

    @property
    def name(self) -> str:
        """Get site name.

        Returns:
            str: the site name
        """
        return self._name

    # FIXME: should this actually return if the alarm is going off!?  How do we
    # return state that shows the site is compromised??

    @property
    def last_updated(self) -> int:
        """Return time site last updated.

        Returns:
            int: the time site last updated as datetime
        """
        with self._site_lock:
            return self._last_updated

    @property
    def site_lock(self) -> "RLock| DebugRLock":
        """Get thread lock for site data.

        Not needed for async

        Returns:
            RLock: thread RLock
        """
        return self._site_lock

    @property
    def zones(self) -> list[ADTPulseFlattendZone] | None:
        """Return all zones registered with the ADT Pulse account.

        (cached copy of last fetch)
        See Also fetch_zones()
        """
        with self._site_lock:
            if not self._zones:
                raise RuntimeError("No zones exist")
            return self._zones.flatten()

    @property
    def zones_as_dict(self) -> ADTPulseZones | None:
        """Return zone information in dictionary form.

        Returns:
            ADTPulseZones: all zone information
        """
        with self._site_lock:
            if not self._zones:
                raise RuntimeError("No zones exist")
            return self._zones

    @property
    def alarm_control_panel(self) -> ADTPulseAlarmPanel:
        """Return the alarm panel object for the site.

        Returns:
            Optional[ADTPulseAlarmPanel]: the alarm panel object
        """
        return self._alarm_panel

    @property
    def gateway(self) -> ADTPulseGateway:
        """Get gateway device object.

        Returns:
            ADTPulseGateway: Gateway device
        """
        return self._gateway

    @property
    def updates_may_exist(self) -> bool:
        """Query whether updated sensor data exists.

        Deprecated, use method on pyADTPulse object instead
        """
        # FIXME: this should actually capture the latest version
        # and compare if different!!!
        # ...this doesn't actually work if other components are also checking
        #  if updates exist
        warn(
            "updates_may_exist on site object is deprecated, "
            "use method on pyADTPulse object instead",
            DeprecationWarning,
            stacklevel=2,
        )
        return False

    async def async_update(self) -> bool:
        """Force update site/zone data async with current data.

        Deprecated, use method on pyADTPulse object instead
        """
        warn(
            "updating zones from site object is deprecated, "
            "use method on pyADTPulse object instead",
            DeprecationWarning,
            stacklevel=2,
        )
        return False

    def update(self) -> bool:
        """Force update site/zones with current data.

        Deprecated, use method on pyADTPulse object instead
        """
        warn(
            "updating zones from site object is deprecated, "
            "use method on pyADTPulse object instead",
            DeprecationWarning,
            stacklevel=2,
        )
        return False
