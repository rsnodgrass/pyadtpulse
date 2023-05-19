"""ADT Alarm Panel Dataclass."""
from dataclasses import dataclass


@dataclass(slots=True)
class ADTPulseAlarmPanel:
    """ADT Alarm Panel information."""

    model: str
    manufacturer: str = "ADT"
    online: bool = True
