"""ADT Pulse Gateway Dataclass."""

import logging
import re
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv6Address, ip_address
from threading import RLock
from typing import Any

from typeguard import typechecked

from .const import ADT_DEFAULT_POLL_INTERVAL, ADT_GATEWAY_MAX_OFFLINE_POLL_INTERVAL
from .pulse_backoff import PulseBackoff
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
    backoff = PulseBackoff(
        "Gateway", ADT_DEFAULT_POLL_INTERVAL, ADT_GATEWAY_MAX_OFFLINE_POLL_INTERVAL
    )
    _attribute_lock = RLock()
    model: str | None = None
    serial_number: str | None = None
    next_update: int = 0
    last_update: int = 0
    firmware_version: str | None = None
    hardware_version: str | None = None
    primary_connection_type: str | None = None
    broadband_connection_status: str | None = None
    cellular_connection_status: str | None = None
    _cellular_connection_signal_strength: float = 0.0
    broadband_lan_ip_address: IPv4Address | IPv6Address | None = None
    _broadband_lan_mac: str | None = None
    device_lan_ip_address: IPv4Address | IPv6Address | None = None
    _device_lan_mac: str | None = None
    router_lan_ip_address: IPv4Address | IPv6Address | None = None
    router_wan_ip_address: IPv4Address | IPv6Address | None = None

    @property
    def is_online(self) -> bool:
        """Returns whether gateway is online.

        Returns:
            bool: True if gateway is online
        """
        with self._attribute_lock:
            return self._status_text == "ONLINE"

    @is_online.setter
    @typechecked
    def is_online(self, status: bool) -> None:
        """Set gateway status.

        Args:
            status (bool): True if gateway is online
        """
        with self._attribute_lock:
            if status == self.is_online:
                return
            old_status = self._status_text
            self._status_text = "ONLINE"
            if not status:
                self._status_text = "OFFLINE"

            LOG.info(
                "ADT Pulse gateway %s",
                self._status_text,
            )
            if old_status == "OFFLINE":
                self.backoff.reset_backoff()
            LOG.debug(
                "Gateway poll interval: %d",
                (
                    self.backoff.initial_backoff_interval
                    if self._status_text == "ONLINE"
                    else self.backoff.get_current_backoff_interval()
                ),
            )

    @property
    def poll_interval(self) -> float:
        """Get initial poll interval."""
        with self._attribute_lock:
            return self.backoff.initial_backoff_interval

    @poll_interval.setter
    @typechecked
    def poll_interval(self, new_interval: float) -> None:
        with self._attribute_lock:
            self.backoff.initial_backoff_interval = new_interval

    @staticmethod
    def _check_mac_address(mac_address: str) -> bool:
        pattern = r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$"
        return re.match(pattern, mac_address) is not None

    @property
    def broadband_lan_mac(self) -> str | None:
        """Get current gateway MAC address."""
        return self._broadband_lan_mac

    @broadband_lan_mac.setter
    @typechecked
    def broadband_lan_mac(self, new_mac: str | None) -> None:
        """Set gateway MAC address."""
        if new_mac is not None and not self._check_mac_address(new_mac):
            raise ValueError("Invalid MAC address")
        self._broadband_lan_mac = new_mac

    @property
    def device_lan_mac(self) -> str | None:
        """Get current gateway MAC address."""
        return self._device_lan_mac

    @device_lan_mac.setter
    @typechecked
    def device_lan_mac(self, new_mac: str | None) -> None:
        """Set gateway MAC address."""
        if new_mac is not None and not self._check_mac_address(new_mac):
            raise ValueError("Invalid MAC address")
        self._device_lan_mac = new_mac

    @property
    def cellular_connection_signal_strength(self) -> float:
        """Get current gateway MAC address."""
        return self._cellular_connection_signal_strength

    @cellular_connection_signal_strength.setter
    @typechecked
    def cellular_connection_signal_strength(
        self, new_signal_strength: float | None
    ) -> None:
        """Set gateway MAC address."""
        if not new_signal_strength:
            new_signal_strength = 0.0
        self._cellular_connection_signal_strength = new_signal_strength

    def set_gateway_attributes(self, gateway_attributes: dict[str, str]) -> None:
        """Set gateway attributes from dictionary.

        Args:
            gateway_attributes (dict[str,str]): dictionary of gateway attributes
        """
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
            if hasattr(self, i):
                setattr(self, i, temp)
