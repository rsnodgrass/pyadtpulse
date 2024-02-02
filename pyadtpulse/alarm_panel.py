"""ADT Alarm Panel Dataclass."""

import logging
import re
from asyncio import run_coroutine_threadsafe
from dataclasses import dataclass
from threading import RLock
from time import time

from bs4 import BeautifulSoup
from typeguard import typechecked

from .const import ADT_ARM_DISARM_URI
from .pulse_connection import PulseConnection
from .util import make_soup

LOG = logging.getLogger(__name__)
ADT_ALARM_AWAY = "away"
ADT_ALARM_HOME = "stay"
ADT_ALARM_OFF = "off"
ADT_ALARM_UNKNOWN = "unknown"
ADT_ALARM_ARMING = "arming"
ADT_ALARM_DISARMING = "disarming"

ALARM_STATUSES = (
    ADT_ALARM_AWAY,
    ADT_ALARM_HOME,
    ADT_ALARM_OFF,
    ADT_ALARM_UNKNOWN,
    ADT_ALARM_ARMING,
    ADT_ALARM_DISARMING,
)

ADT_ARM_DISARM_TIMEOUT: float = 20


@dataclass(slots=True)
class ADTPulseAlarmPanel:
    """ADT Alarm Panel information."""

    model: str = "Unknown"
    _sat: str = ""
    _status: str = "Unknown"
    manufacturer: str = "ADT"
    online: bool = True
    _is_force_armed: bool = False
    _state_lock = RLock()
    _last_arm_disarm: int = int(time())

    @property
    def status(self) -> str:
        """Get alarm status.

        Returns:
            str: the alarm status
        """
        with self._state_lock:
            return self._status

    @status.setter
    def status(self, new_status: str) -> None:
        """Set alarm status.

        Args:
            new_status (str): the new alarm status
        """
        with self._state_lock:
            if new_status not in ALARM_STATUSES:
                raise ValueError(f"Alarm status must be one of {ALARM_STATUSES}")
            self._status = new_status

    @property
    def is_away(self) -> bool:
        """Return wheter the system is armed away.

        Returns:
            bool: True if armed away
        """
        with self._state_lock:
            return self._status == ADT_ALARM_AWAY

    @property
    def is_home(self) -> bool:
        """Return whether system is armed at home/stay.

        Returns:
            bool: True if system is armed home/stay
        """
        with self._state_lock:
            return self._status == ADT_ALARM_HOME

    @property
    def is_disarmed(self) -> bool:
        """Return whether the system is disarmed.

        Returns:
            bool: True if the system is disarmed
        """
        with self._state_lock:
            return self._status == ADT_ALARM_OFF

    @property
    def is_force_armed(self) -> bool:
        """Return whether the system is armed in bypass mode.

        Returns:
            bool: True if system armed in bypass mode
        """
        with self._state_lock:
            return self._is_force_armed

    @property
    def is_arming(self) -> bool:
        """Return if system is attempting to arm.

        Returns:
            bool: True if system is attempting to arm
        """
        with self._state_lock:
            return self._status == ADT_ALARM_ARMING

    @property
    def is_disarming(self) -> bool:
        """Return if system is attempting to disarm.

        Returns:
            bool: True if system is attempting to disarm
        """
        with self._state_lock:
            return self._status == ADT_ALARM_DISARMING

    @property
    def last_update(self) -> float:
        """Return last update time.

        Returns:
            float: last arm/disarm time
        """
        with self._state_lock:
            return self._last_arm_disarm

    @typechecked
    async def _arm(
        self, connection: PulseConnection, mode: str, force_arm: bool
    ) -> bool:
        """Set arm status.

        Args:
            mode (str)
            force_arm (bool): True if arm force

        Returns:
            bool: True if operation successful
        """
        LOG.debug("Setting ADT alarm %s to %s, force = %s", self._sat, mode, force_arm)
        with self._state_lock:
            if self._status == mode:
                LOG.warning(
                    "Attempting to set alarm status %s to existing status %s",
                    mode,
                    self._status,
                )
            if self._status != ADT_ALARM_OFF and mode != ADT_ALARM_OFF:
                LOG.warning("Cannot set alarm status from %s to %s", self._status, mode)
                return False
            params = {
                "href": "rest/adt/ui/client/security/setArmState",
                "armstate": self._status,  # existing state
                "arm": mode,  # new state
                "sat": self._sat,
            }
            if force_arm and mode != ADT_ALARM_OFF:
                params = {
                    "href": "rest/adt/ui/client/security/setForceArm",
                    "armstate": "forcearm",  # existing state
                    "arm": mode,  # new state
                    "sat": self._sat,
                }

            response = await connection.async_query(
                ADT_ARM_DISARM_URI,
                method="POST",
                extra_params=params,
                timeout=10,
            )

            soup = make_soup(
                response[0],
                response[1],
                response[2],
                logging.WARNING,
                f"Failed updating ADT Pulse alarm {self._sat} to {mode}",
            )
            if soup is None:
                return False

            arm_result = soup.find("div", {"class": "p_armDisarmWrapper"})
            if arm_result is not None:
                error_block = arm_result.find("div")
                if error_block is not None:
                    error_text = arm_result.get_text().replace(
                        "Arm AnywayCancel\n\n", ""
                    )
                    LOG.warning(
                        "Could not set alarm state to %s because %s", mode, error_text
                    )
                    return False
        self._is_force_armed = force_arm
        if mode == ADT_ALARM_OFF:
            self._status = ADT_ALARM_DISARMING
        else:
            self._status = ADT_ALARM_ARMING
        self._last_arm_disarm = int(time())
        return True

    @typechecked
    def _sync_set_alarm_mode(
        self,
        connection: PulseConnection,
        mode: str,
        force_arm: bool = False,
    ) -> bool:
        coro = self._arm(connection, mode, force_arm)
        return run_coroutine_threadsafe(
            coro,
            connection.check_sync(
                "Attempting to sync change alarm mode from async session"
            ),
        ).result()

    @typechecked
    def arm_away(self, connection: PulseConnection, force_arm: bool = False) -> bool:
        """Arm the alarm in Away mode.

        Args:
            force_arm (bool, Optional): force system to arm

        Returns:
            bool: True if arm succeeded
        """
        return self._sync_set_alarm_mode(connection, ADT_ALARM_AWAY, force_arm)

    @typechecked
    def arm_home(self, connection: PulseConnection, force_arm: bool = False) -> bool:
        """Arm the alarm in Home mode.

        Args:
            force_arm (bool, Optional): force system to arm

        Returns:
            bool: True if arm succeeded
        """
        return self._sync_set_alarm_mode(connection, ADT_ALARM_HOME, force_arm)

    @typechecked
    def disarm(self, connection: PulseConnection) -> bool:
        """Disarm the alarm.

        Returns:
            bool: True if disarm succeeded
        """
        return self._sync_set_alarm_mode(connection, ADT_ALARM_OFF, False)

    @typechecked
    async def async_arm_away(
        self, connection: PulseConnection, force_arm: bool = False
    ) -> bool:
        """Arm alarm away async.

        Args:
            force_arm (bool, Optional): force system to arm

        Returns:
            bool: True if arm succeeded
        """
        return await self._arm(connection, ADT_ALARM_AWAY, force_arm)

    @typechecked
    async def async_arm_home(
        self, connection: PulseConnection, force_arm: bool = False
    ) -> bool:
        """Arm alarm home async.

        Args:
            force_arm (bool, Optional): force system to arm
        Returns:
            bool: True if arm succeeded
        """
        return await self._arm(connection, ADT_ALARM_HOME, force_arm)

    @typechecked
    async def async_disarm(self, connection: PulseConnection) -> bool:
        """Disarm alarm async.

        Returns:
            bool: True if disarm succeeded
        """
        return await self._arm(connection, ADT_ALARM_OFF, False)

    @typechecked
    def update_alarm_from_soup(self, summary_html_soup: BeautifulSoup) -> None:
        """
        Updates the alarm status based on the information extracted from the provided
        HTML soup.

        Args:
            summary_html_soup (BeautifulSoup): The BeautifulSoup object representing
            the HTML soup.

        Returns:
            None: This function does not return anything.
        """
        LOG.debug("Updating alarm status")
        value = summary_html_soup.find("span", {"class": "p_boldNormalTextLarge"})
        sat_location = "security_button_0"
        with self._state_lock:
            if value:
                text = value.text.lstrip().splitlines()[0]
                last_updated = int(time())

                if text.startswith("Disarmed"):
                    if (
                        self._status != ADT_ALARM_ARMING
                        or last_updated - self._last_arm_disarm > ADT_ARM_DISARM_TIMEOUT
                    ):
                        self._status = ADT_ALARM_OFF
                        self._last_arm_disarm = last_updated
                elif text.startswith("Armed Away"):
                    if (
                        self._status != ADT_ALARM_DISARMING
                        or last_updated - self._last_arm_disarm > ADT_ARM_DISARM_TIMEOUT
                    ):
                        self._status = ADT_ALARM_AWAY
                        self._last_arm_disarm = last_updated
                elif text.startswith("Armed Stay"):
                    if (
                        self._status != ADT_ALARM_DISARMING
                        or last_updated - self._last_arm_disarm > ADT_ARM_DISARM_TIMEOUT
                    ):
                        self._status = ADT_ALARM_HOME
                        self._last_arm_disarm = last_updated
                else:
                    LOG.warning("Failed to get alarm status from '%s'", text)
                    self._status = ADT_ALARM_UNKNOWN
                    self._last_arm_disarm = last_updated
                    return
                LOG.debug("Alarm status = %s", self._status)

            sat_button = summary_html_soup.find(
                "input", {"type": "button", "id": sat_location}
            )
            if sat_button and sat_button.has_attr("onclick"):
                on_click = sat_button["onclick"]
                match = re.search(r"sat=([a-z0-9\-]+)", on_click)
                if match:
                    self._sat = match.group(1)
            elif len(self._sat) == 0:
                LOG.warning("No sat recorded and was unable extract sat.")

            if len(self._sat) > 0:
                LOG.debug("Extracted sat = %s", self._sat)
            else:
                LOG.warning("Unable to extract sat")

    @typechecked
    def set_alarm_attributes(self, alarm_attributes: dict[str, str]) -> None:
        """
        Set alarm attributes including model, manufacturer, and online status.

        Args:
            self (object): The instance of the alarm.
            alarm_attributes (dict[str, str]): A dictionary containing alarm attributes.

        Returns:
            None
        """
        self.model = alarm_attributes.get("type_model", "Unknown")
        self.manufacturer = alarm_attributes.get("manufacturer_provider", "ADT")
        self.online = alarm_attributes.get("status", "Offline") == "Online"
        LOG.debug(
            "Set alarm attributes: Model = %s, Manufacturer = %s, Online = %s",
            self.model,
            self.manufacturer,
            self.online,
        )
