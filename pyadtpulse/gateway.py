"""ADT Pulse Gateway Dataclass."""

import logging
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv6Address, ip_address
from threading import RLock
from typing import Any, Optional

from .const import ADT_DEFAULT_POLL_INTERVAL, ADT_GATEWAY_OFFLINE_POLL_INTERVAL
from .util import parse_pulse_datetime

LOG = logging.getLogger(__name__)

STRING_UPDATEABLE_FIELDS = (
    "manufacturer",
    "model",
    "serial_number",
    "firmware_version",
    "hardware_version",
    "primary_connection_type",
    "broadband_connection_status",
    "cellular_connection_status",
    "cellular_connection_signal_strength",
    "broadband_lan_mac",
    "device_lan_mac",
)

DATETIME_UPDATEABLE_FIELDS = ("next_update", "last_update")

IPADDR_UPDATEABLE_FIELDS = (
    "broadband_lan_ip_address",
    "device_lan_ip_address",
    "router_lan_ip_address",
    "router_wan_ip_address",
)


@dataclass(slots=True)
class ADTPulseGateway:
    """ADT Pulse Gateway information."""

    manufacturer: str = "Unknown"
    _status_text: str = "OFFLINE"
    _current_poll_interval: float = ADT_DEFAULT_POLL_INTERVAL
    _initial_poll_interval: float = ADT_DEFAULT_POLL_INTERVAL
    _attribute_lock = RLock()
    model: Optional[str] = None
    serial_number: Optional[str] = None
    next_update: int = 0
    last_update: int = 0
    firmware_version: Optional[str] = None
    hardware_version: Optional[str] = None
    primary_connection_type: Optional[str] = None
    broadband_connection_status: Optional[str] = None
    cellular_connection_status: Optional[str] = None
    cellular_connection_signal_strength: float = 0.0
    broadband_lan_ip_address: Optional[IPv4Address | IPv6Address] = None
    broadband_lan_mac: Optional[str] = None
    device_lan_ip_address: Optional[IPv4Address | IPv6Address] = None
    device_lan_mac: Optional[str] = None
    router_lan_ip_address: Optional[IPv4Address | IPv6Address] = None
    router_wan_ip_address: Optional[IPv4Address | IPv6Address] = None

    @property
    def is_online(self) -> bool:
        """Returns whether gateway is online.

        Returns:
            bool: True if gateway is online
        """
        with self._attribute_lock:
            return self._status_text == "ONLINE"

    @is_online.setter
    def is_online(self, status: bool) -> None:
        """Set gateway status.

        Args:
            status (bool): True if gateway is online

        Also changes the polling intervals
        """
        with self._attribute_lock:
            if status == self.is_online:
                return

            self._status_text = "ONLINE"
            if not status:
                self._status_text = "OFFLINE"
                self._current_poll_interval = ADT_GATEWAY_OFFLINE_POLL_INTERVAL
            else:
                self._current_poll_interval = self._initial_poll_interval

            LOG.info(
                "ADT Pulse gateway %s, poll interval=%f",
                self._status_text,
                self._current_poll_interval,
            )

    @property
    def poll_interval(self) -> float:
        """Set polling interval.

        Returns:
            float: number of seconds between polls
        """
        with self._attribute_lock:
            return self._current_poll_interval

    @poll_interval.setter
    def poll_interval(self, new_interval: Optional[float]) -> None:
        """Set polling interval.

        Args:
            new_interval (float): polling interval if gateway is online,
                if set to None, resets to ADT_DEFAULT_POLL_INTERVAL

        Raises:
            ValueError: if new_interval is less than 0
        """
        if new_interval is None:
            new_interval = ADT_DEFAULT_POLL_INTERVAL
        elif new_interval < 0.0:
            raise ValueError("ADT Pulse polling interval must be greater than 0")
        with self._attribute_lock:
            self._initial_poll_interval = new_interval
            if self._current_poll_interval != ADT_GATEWAY_OFFLINE_POLL_INTERVAL:
                self._current_poll_interval = new_interval
            LOG.debug("Set poll interval to %f", self._initial_poll_interval)

    def set_gateway_attributes(self, gateway_attributes: dict[str, str]) -> None:
        """Set gateway attributes from dictionary.

        Args:
            gateway_attributes (dict[str,str]): dictionary of gateway attributes
        """ """"""
        for i in (
            STRING_UPDATEABLE_FIELDS
            + IPADDR_UPDATEABLE_FIELDS
            + DATETIME_UPDATEABLE_FIELDS
        ):
            temp: Any = gateway_attributes.get(i)
            if temp == "":
                temp = None
            if temp is None:
                setattr(self, i, None)
                continue
            if i in IPADDR_UPDATEABLE_FIELDS:
                try:
                    temp = ip_address(temp)
                except ValueError:
                    temp = None
            elif i in DATETIME_UPDATEABLE_FIELDS:
                try:
                    temp = int(parse_pulse_datetime(temp).timestamp())
                except ValueError:
                    temp = None
            setattr(self, i, temp)
