"""ADT Pulse Gateway Dataclass."""

from dataclasses import dataclass
from ipaddress import IPv4Address


@dataclass(slots=True)
class ADTPulseGateway:
    """ADT Pulse Gateway information."""

    manufacturer: str
    model: str
    serial_number: str
    next_update: float
    last_update: float
    firmware_version: str
    hardware_version: str
    primary_connection_type: str
    broadband_connection_status: str
    cellular_connection_status: str
    cellular_connection_signal_strength: float
    broadband_lan_ip_address: IPv4Address
    broadband_lan_mac_address: str
    device_lan_ip_address: IPv4Address
    device_lan_mac_address: str
    router_lan_ip_address: IPv4Address
    router_wan_ip_address: IPv4Address
