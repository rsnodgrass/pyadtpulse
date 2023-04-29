"""ADT Pulse zone info."""
from collections import UserDict
from dataclasses import dataclass
from datetime import datetime
from typing import List, Tuple, TypedDict

ADT_NAME_TO_DEFAULT_TAGS = {
    "Door": ("sensor", "doorWindow"),
    "Window": ("sensor", "doorWindow"),
    "Motion": ("sensor", "motion"),
    "Glass": ("sensor", "glass"),
    "Gas": ("sensor", "co"),
    "Carbon": ("sensor", "co"),
    "Smoke": ("sensor", "smoke"),
    "Flood": ("sensor", "flood"),
    "Floor": ("sensor", "flood"),
    "Moisture": ("sensor", "flood"),
}


@dataclass(slots=True)
class ADTPulseZoneData:
    """Data for an ADT Pulse zone.

    Fields:
        name (str): the zone name
        id_ (str): zone name in ADT Pulse (Note, not id as this is a reserved word)
        tags (Tuple): sensor and type(s)
        status (str): sensor status (i.e. Online, Low Battery, etc.)
        state (str): sensor state (i.e. Opened, Closed, etc)
        timestamp (datetime): timestamp of last activity

    Will set unknown type defaults to all but name and id_
    """

    name: str
    id_: str
    tags: Tuple = ADT_NAME_TO_DEFAULT_TAGS["Window"]
    status: str = "Unknown"
    state: str = "Unknown"
    last_activity_timestamp: float = 0.0


class ADTPulseFlattendZone(TypedDict):
    """Represent ADTPulseZones as a "flattened" dictionary.

    Fields:
        zone (int): the zone id
        name (str): the zone name
        id_ (str): zone name in ADT Pulse (Note, not id as this is a reserved word)
        tags (Tuple): sensor and type(s)
        status (str): sensor status (i.e. Online, Low Battery, etc.)
        state (str): sensor state (i.e. Opened, Closed, etc)
        timestamp (datetime): timestamp of last activity
    """

    zone: int
    name: str
    id_: str
    tags: Tuple
    status: str
    state: str
    last_activity_timestamp: float


class ADTPulseZones(UserDict):
    """Dictionary containing ADTPulseZoneData with zone as the key."""

    def __getitem__(self, key: int) -> ADTPulseZoneData:
        """Get a Zone.

        Args:
            key (int): zone id

        Returns:
            ADTPulseZoneData: zone data
        """
        return super().__getitem__(key)

    @staticmethod
    def _check_value(value: ADTPulseZoneData) -> None:
        if not isinstance(value, ADTPulseZoneData):
            raise ValueError("ADT Pulse zone data must be of type ADTPulseZoneData")

    @staticmethod
    def _check_key(key: int) -> None:
        if not isinstance(key, int):
            raise ValueError("ADT Pulse Zone must be an integer")

    def _get_zonedata(self, key: int) -> ADTPulseZoneData:
        self._check_key(key)
        result: ADTPulseZoneData = self.data[key]
        self._check_value(result)
        return result

    def __setitem__(self, key: int, value: ADTPulseZoneData) -> None:
        """Validate types and sets defaults for ADTPulseZones.

        ADTPulseZoneData.id_ and name will be set to generic defaults if not set

        Raises:
            ValueError: if key is not an int or value is not ADTPulseZoneData
        """
        self._check_key(key)
        self._check_value(value)
        if not value.id_:
            value.id_ = "sensor-" + str(key)
        if not value.name:
            value.name = "Sensor for Zone " + str(key)
        super().__setitem__(key, value)

    def update_status(self, key: int, status: str) -> None:
        """Update zone status.

        Args:
            key (int): zone id to change
            status (str): status to set
        """ """"""
        temp = self._get_zonedata(key)
        temp.status = status
        self.__setitem__(key, temp)

    def update_state(self, key: int, state: str) -> None:
        """Update zone state.

        Args:
            key (int): zone id to change
            state (str): state to set
        """
        temp = self._get_zonedata(key)
        temp.state = state
        self.__setitem__(key, temp)

    def update_last_activity_timestamp(self, key: int, dt: datetime) -> None:
        """Update timestamp.

        Args:
            key (int): zone id to change
            dt (datetime): timestamp to set
        """
        temp = self._get_zonedata(key)
        temp.last_activity_timestamp = dt.timestamp()
        self.__setitem__(key, temp)

    def update_device_info(
        self,
        key: int,
        state: str,
        status: str = "Online",
        last_activity: datetime = datetime.now(),
    ) -> None:
        """Update the device info.

        Convenience method to update all common device info
        at once.

        Args:
            key (int): zone id
            state (str): state
            status (str, optional): status. Defaults to "Online".
            last_activity (datetime, optional): last_activity_datetime.
                Defaults to datetime.now().
        """
        temp = self._get_zonedata(key)
        temp.state = state
        temp.status = status
        temp.last_activity_timestamp = last_activity.timestamp()
        self.__setitem__(key, temp)

    def flatten(self) -> List[ADTPulseFlattendZone]:
        """Flattens ADTPulseZones into a list of ADTPulseFlattenedZones.

        Returns:
            List[ADTPulseFlattendZone]
        """
        result: List[ADTPulseFlattendZone] = []
        for k, i in self.items():
            if not isinstance(i, ADTPulseZoneData):
                raise ValueError("Invalid Zone data in ADTPulseZones")
            result.append(
                {
                    "zone": k,
                    "name": i.name,
                    "id_": i.id_,
                    "tags": i.tags,
                    "status": i.status,
                    "state": i.state,
                    "last_activity_timestamp": i.last_activity_timestamp,
                }
            )
        return result
