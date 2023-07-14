"""ADT Pulse Gateway Dataclass."""

from dataclasses import dataclass
from ipaddress import IPv4Address
from threading import RLock

from .const import ADT_DEFAULT_POLL_INTERVAL, ADT_GATEWAY_OFFLINE_POLL_INTERVAL, LOG


@dataclass(slots=True)
class ADTPulseGateway:
    """ADT Pulse Gateway information."""

    manufacturer: str = "Unknown"
    _is_online: bool = False
    _status_text: str = "OFFLINE"
    _current_poll_interval: float = ADT_DEFAULT_POLL_INTERVAL
    _initial_poll_interval: float = ADT_DEFAULT_POLL_INTERVAL
    _attribute_lock = RLock()
    model: str = "Unknown"
    serial_number: str = "Unknown"
    next_update: float = 0.0
    last_update: float = 0.0
    firmware_version: str = "Unknown"
    hardware_version: str = "Unknown"
    primary_connection_type: str = "Unknown"
    broadband_connection_status: str = "Unknown"
    cellular_connection_status: str = "Unknown"
    cellular_connection_signal_strength: float = 0.0
    broadband_lan_ip_address: IPv4Address = IPv4Address("0.0.0.0")
    broadband_lan_mac_address: str = "Unknown"
    device_lan_ip_address: IPv4Address = IPv4Address("0.0.0.0")
    device_lan_mac_address: str = "Unknown"
    router_lan_ip_address: IPv4Address = IPv4Address("0.0.0.0")
    router_wan_ip_address: IPv4Address = IPv4Address("0.0.0.0")

    @property
    def is_online(self) -> bool:
        """Returns whether gateway is online.

        Returns:
            bool: True if gateway is online
        """
        with self._attribute_lock:
            return self._is_online

    @is_online.setter
    def is_online(self, status: bool) -> None:
        """Set gateway status.

        Args:
            status (bool): True if gateway is online

        Also changes the polling intervals
        """
        with self._attribute_lock:
            if status == self._is_online:
                return

            self._status_text = "ONLINE"
            if not status:
                self._status_text = "OFFLINE"
                self._current_poll_interval = ADT_GATEWAY_OFFLINE_POLL_INTERVAL
            else:
                self._current_poll_interval = self._initial_poll_interval

            LOG.info(
                f"ADT Pulse gateway {self._status_text}, "
                "poll interval={self._current_poll_interval}"
            )
            self._is_online = status

    @property
    def poll_interval(self) -> float:
        """Set polling interval.

        Returns:
            float: number of seconds between polls
        """
        with self._attribute_lock:
            return self._current_poll_interval

    @poll_interval.setter
    def poll_interval(self, new_interval: float) -> None:
        """Set polling interval.

        Args:
            new_interval (float): polling interval if gateway is online

        Raises:
            ValueError: if new_interval is less than 0
        """
        if new_interval < 0.0:
            raise ValueError("ADT Pulse polling interval must be greater than 0")
        with self._attribute_lock:
            self._initial_poll_interval = new_interval
            if self._current_poll_interval != ADT_GATEWAY_OFFLINE_POLL_INTERVAL:
                self._current_poll_interval = new_interval
            LOG.debug(f"Set poll interval to {self._initial_poll_interval}")
