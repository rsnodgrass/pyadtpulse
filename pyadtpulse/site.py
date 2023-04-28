"""Module representing an ADT Pulse Site."""

import logging
import re
from asyncio import get_event_loop, run_coroutine_threadsafe
from datetime import datetime, timedelta
from threading import RLock
from typing import List, Optional, Union

# import dateparser
from bs4 import BeautifulSoup
from dateutil import relativedelta

from pyadtpulse import PyADTPulse
from pyadtpulse.const import ADT_ARM_DISARM_URI, ADT_DEVICE_URI, ADT_SYSTEM_URI
from pyadtpulse.util import DebugRLock, make_soup, remove_prefix
from pyadtpulse.zones import (
    ADT_NAME_TO_DEFAULT_TAGS,
    ADTPulseFlattendZone,
    ADTPulseZoneData,
    ADTPulseZones,
)

ADT_ALARM_AWAY = "away"
ADT_ALARM_HOME = "stay"
ADT_ALARM_OFF = "off"
ADT_ALARM_UNKNOWN = "unknown"
ADT_ALARM_ARMING = "arming"
ADT_ALARM_DISARMING = "disarming"
ADT_ARM_DISARM_TIMEOUT = timedelta(seconds=20)


LOG = logging.getLogger(__name__)


class ADTPulseSite:
    """Represents an individual ADT Pulse site."""

    __slots__ = (
        "_adt_service",
        "_id",
        "_name",
        "_status",
        "_is_force_armed",
        "_sat",
        "_last_updated",
        "_last_arm_disarm",
        "_zones",
        "_site_lock",
    )

    def __init__(self, adt_service: PyADTPulse, site_id: str, name: str):
        """Initialize.

        Args:
            adt_service (PyADTPulse): a PyADTPulse object
            site_id (str): site ID
            name (str): site name
        """
        self._adt_service = adt_service
        self._id = site_id
        self._name = name
        self._status = ADT_ALARM_UNKNOWN
        self._is_force_armed: bool = False
        self._sat = ""
        self._last_updated = self._last_arm_disarm = datetime(1970, 1, 1)
        self._zones = ADTPulseZones()
        self._site_lock: Union[RLock, DebugRLock]
        if isinstance(self._adt_service.attribute_lock, DebugRLock):
            self._site_lock = DebugRLock("ADTPulseSite._site_lock")
        else:
            self._site_lock = RLock()

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
    def status(self) -> str:
        """Get alarm status.

        Returns:
            str: the alarm status
        """
        with self._site_lock:
            return self._status

    @property
    def is_away(self) -> bool:
        """Return wheter the system is armed away.

        Returns:
            bool: True if armed away
        """
        with self._site_lock:
            return self._status == ADT_ALARM_AWAY

    @property
    def is_home(self) -> bool:
        """Return whether system is armed at home/stay.

        Returns:
            bool: True if system is armed home/stay
        """
        with self._site_lock:
            return self._status == ADT_ALARM_HOME

    @property
    def is_disarmed(self) -> bool:
        """Return whether the system is disarmed.

        Returns:
            bool: True if the system is disarmed
        """
        with self._site_lock:
            return self._status == ADT_ALARM_OFF

    @property
    def is_force_armed(self) -> bool:
        """Return whether the system is armed in bypass mode.

        Returns:
            bool: True if system armed in bypass mode
        """
        with self._site_lock:
            return self._is_force_armed

    @property
    def is_arming(self) -> bool:
        """Return if system is attempting to arm.

        Returns:
            bool: True if system is attempting to arm
        """
        with self._site_lock:
            return self._status == ADT_ALARM_ARMING

    @property
    def is_disarming(self) -> bool:
        """Return if system is attempting to disarm.

        Returns:
            bool: True if system is attempting to disarm
        """
        with self._site_lock:
            return self._status == ADT_ALARM_DISARMING

    @property
    def last_updated(self) -> datetime:
        """Return time site last updated.

        Returns:
            datetime: the time site last updated as datetime
        """
        with self._site_lock:
            return self._last_updated

    @property
    def site_lock(self) -> Union[RLock, DebugRLock]:
        """Get thread lock for site data.

        Not needed for async

        Returns:
            RLock: thread RLock
        """
        return self._site_lock

    async def _arm(self, mode: str, force_arm: bool) -> bool:
        """Set arm status.

        Args:
            mode (str)
            force_arm (bool): True if arm force

        Returns:
            bool: True if operation successful
        """
        LOG.debug(f"Setting ADT alarm '{self._name}' to '{mode}, force = {force_arm}'")
        if self._status == mode:
            LOG.warning(
                f"Attempting to set alarm status {mode} to "
                f"existing status {self._status}"
            )
            return False
        if self._status != ADT_ALARM_OFF and mode != ADT_ALARM_OFF:
            LOG.warning(f"Cannot set alarm status from {self._status} to {mode}")
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

        response = await self._adt_service._async_query(
            ADT_ARM_DISARM_URI,
            method="POST",
            extra_params=params,
            timeout=10,
        )

        soup = await make_soup(
            response,
            logging.WARNING,
            f"Failed updating ADT Pulse alarm {self._name} to {mode}",
        )
        if soup is None:
            return False

        arm_result = soup.find("div", {"class": "p_armDisarmWrapper"})
        if arm_result is not None:
            error_block = arm_result.find("div")
            if error_block is not None:
                error_text = arm_result.get_text().replace("Arm AnywayCancel\n\n", "")
                LOG.warning(
                    f"Could not set alarm state to {mode} " f"because {error_text}"
                )
                return False
        with self._site_lock:
            self._is_force_armed = force_arm
            if mode == ADT_ALARM_OFF:
                self._status = ADT_ALARM_DISARMING
            else:
                self._status = ADT_ALARM_ARMING
            self._last_arm_disarm = self._last_updated = datetime.now()
            return True

    def _sync_set_alarm_mode(self, mode: str, force_arm: bool = False) -> bool:
        loop = self._adt_service.loop
        if loop is None:
            raise RuntimeError(
                "Attempting to sync change alarm mode from async session"
            )
        coro = self._arm(mode, force_arm)
        return run_coroutine_threadsafe(coro, loop).result()

    def arm_away(self, force_arm: bool = False) -> bool:
        """Arm the alarm in Away mode.

        Args:
            force_arm (bool, Optional): force system to arm

        Returns:
            bool: True if arm succeeded
        """
        return self._sync_set_alarm_mode(ADT_ALARM_AWAY, force_arm)

    def arm_home(self, force_arm: bool = False) -> bool:
        """Arm the alarm in Home mode.

        Args:
            force_arm (bool, Optional): force system to arm

        Returns:
            bool: True if arm succeeded
        """
        return self._sync_set_alarm_mode(ADT_ALARM_HOME, force_arm)

    def disarm(self) -> bool:
        """Disarm the alarm.

        Returns:
            bool: True if disarm succeeded
        """
        return self._sync_set_alarm_mode(ADT_ALARM_OFF, False)

    async def async_arm_away(self, force_arm: bool = False) -> bool:
        """Arm alarm away async.

        Args:
            force_arm (bool, Optional): force system to arm

        Returns:
            bool: True if arm succeeded
        """
        return await self._arm(ADT_ALARM_AWAY, force_arm)

    async def async_arm_home(self, force_arm: bool = False) -> bool:
        """Arm alarm home async.

        Args:
            force_arm (bool, Optional): force system to arm
        Returns:
            bool: True if arm succeeded
        """
        return await self._arm(ADT_ALARM_HOME, force_arm)

    async def async_disarm(self) -> bool:
        """Disarm alarm async.

        Returns:
            bool: True if disarm succeeded
        """
        return await self._arm(ADT_ALARM_OFF, False)

    @property
    def zones(self) -> Optional[List[ADTPulseFlattendZone]]:
        """Return all zones registered with the ADT Pulse account.

        (cached copy of last fetch)
        See Also fetch_zones()
        """
        with self._site_lock:
            if not self._zones:
                raise RuntimeError("No zones exist")
            return self._zones.flatten()

    @property
    def zones_as_dict(self) -> Optional[ADTPulseZones]:
        """Return zone information in dictionary form.

        Returns:
            ADTPulseZones: all zone information
        """
        with self._site_lock:
            if not self._zones:
                raise RuntimeError("No zones exist")
            return self._zones

    @property
    def history(self):
        """Return log of history for this zone (NOT IMPLEMENTED)."""
        raise NotImplementedError

    def _update_alarm_from_soup(self, summary_html_soup: BeautifulSoup) -> None:
        LOG.debug("Updating alarm status")
        value = summary_html_soup.find("span", {"class": "p_boldNormalTextLarge"})
        sat_location = "security_button_0"
        with self._site_lock:
            if value:
                text = value.text
                last_updated = datetime.now()

                if re.match("Disarmed", text):
                    if (
                        self._status != ADT_ALARM_ARMING
                        or last_updated - self._last_arm_disarm > ADT_ARM_DISARM_TIMEOUT
                    ):
                        self._status = ADT_ALARM_OFF
                        self._last_updated = last_updated
                elif re.match("Armed Away", text):
                    if (
                        self._status != ADT_ALARM_DISARMING
                        or last_updated - self._last_arm_disarm > ADT_ARM_DISARM_TIMEOUT
                    ):
                        self._status = ADT_ALARM_AWAY
                        self._last_updated = last_updated
                elif re.match("Armed Stay", text):
                    if (
                        self._status != ADT_ALARM_DISARMING
                        or last_updated - self._last_arm_disarm > ADT_ARM_DISARM_TIMEOUT
                    ):
                        self._status = ADT_ALARM_HOME
                        self._last_updated = last_updated
                else:
                    LOG.warning(f"Failed to get alarm status from '{text}'")
                    self._adt_service._set_gateway_status(False)
                    self._status = ADT_ALARM_UNKNOWN
                    self._last_updated = last_updated
                    return
                LOG.debug(f"Alarm status = {self._status}")

            if self._sat == "":
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

        #        status_orb = summary_html_soup.find('canvas', {'id': 'ic_orb'})
        #        if status_orb:
        #            self._status = status_orb['orb']
        #            LOG.warning(status_orb)
        #            LOG.debug("Alarm status = %s", self._status)
        #        else:
        #            LOG.error("Failed to find alarm status in ADT summary!")

        # if we should also update the zone details, force a fresh fetch
        # of data from ADT Pulse

    async def _fetch_zones(
        self, soup: Optional[BeautifulSoup]
    ) -> Optional[ADTPulseZones]:
        """Fetch zones for a site.

        Args:
            soup (BeautifulSoup, Optional): a BS4 object with data fetched from
                                            ADT Pulse web site
        Returns:
            ADTPulseZones

            None if an error occurred
        """
        if not soup:
            response = await self._adt_service._async_query(ADT_SYSTEM_URI)
            soup = await make_soup(
                response,
                logging.WARNING,
                "Failed loading zone status from ADT Pulse service",
            )
            if not soup:
                return None

        temp_zone: ADTPulseZoneData
        regexDevice = r"goToUrl\('device.jsp\?id=(\d*)'\);"
        with self._site_lock:
            for row in soup.find_all("tr", {"class": "p_listRow", "onclick": True}):
                onClickValueText = row.get("onclick")
                result = re.findall(regexDevice, onClickValueText)

                # only proceed if regex succeeded, as some users have onClick
                # links that include gateway.jsp
                if not result:
                    LOG.debug(
                        f"Failed regex match #{regexDevice} on #{onClickValueText} "
                        "from ADT Pulse service, ignoring"
                    )
                    continue

                device_id = result[0]
                deviceResponse = await self._adt_service._async_query(
                    ADT_DEVICE_URI, extra_params={"id": device_id}
                )
                deviceResponseSoup = await make_soup(
                    deviceResponse,
                    logging.DEBUG,
                    "Failed loading zone data from ADT Pulse service",
                )
                if deviceResponseSoup is None:
                    return None

                dName = dType = dZone = dStatus = ""
                # dMan = ""
                for devInfoRow in deviceResponseSoup.find_all(
                    "td", {"class", "InputFieldDescriptionL"}
                ):
                    identityText = devInfoRow.get_text().upper()
                    sibling = devInfoRow.find_next_sibling()
                    if not sibling:
                        continue
                    value = sibling.get_text().strip()
                    if identityText == "NAME:":
                        dName = value
                    elif identityText == "TYPE/MODEL:":
                        dType = value
                    elif identityText == "ZONE:":
                        dZone = value
                    elif identityText == "STATUS:":
                        dStatus = value
                #                elif identityText == "MANUFACTURER/PROVIDER:":
                #                   dMan = value

                # NOTE: if empty string, this is the control panel
                if dZone != "":
                    tags = None

                    for search_term, default_tags in ADT_NAME_TO_DEFAULT_TAGS.items():
                        # convert to uppercase first
                        if search_term.upper() in dType.upper():
                            tags = default_tags
                            break

                    if not tags:
                        LOG.warning(
                            f"Unknown sensor type for '{dType}', "
                            "defaulting to doorWindow"
                        )
                        tags = ("sensor", "doorWindow")
                    LOG.debug(f"Adding sensor {dName} id: sensor-{dZone}")
                    LOG.debug(f"Status: {dStatus}, tags {tags}")
                    tmpzone = ADTPulseZoneData(dName, f"sensor-{dZone}", tags, dStatus)
                    self._zones.update({int(dZone): tmpzone})
            self._last_updated = datetime.now()
            return self._zones

        # FIXME: ensure the zones for the correct site are being loaded!!!

    async def _async_update_zones_as_dict(
        self, soup: Optional[BeautifulSoup]
    ) -> Optional[ADTPulseZones]:
        """Update zone status information asynchronously.

        Returns:
            ADTPulseZones: a dictionary of zones with status
            None if an error occurred
        """
        with self._site_lock:
            if self._zones is None:
                self._site_lock.release()
                raise RuntimeError("No zones exist")
            LOG.debug(f"fetching zones for site { self._id}")
            if not soup:
                # call ADT orb uri
                soup = await self._adt_service._query_orb(
                    logging.WARNING, "Could not fetch zone status updates"
                )
            if soup is None:
                return None
            return self._update_zone_from_soup(soup)

    def _update_zone_from_soup(self, soup: BeautifulSoup) -> Optional[ADTPulseZones]:
        # parse ADT's convulated html to get sensor status
        with self._site_lock:
            gateway_online = False
            for row in soup.find_all("tr", {"class": "p_listRow"}):
                temp = row.find("span", {"class": "devStatIcon"})
                if temp is None:
                    break
                t = datetime.today()
                last_update = datetime(1970, 1, 1)
                datestring = remove_prefix(temp.get("title"), "Last Event:").split(
                    "\xa0"
                )
                if len(datestring) < 3:
                    LOG.warning(
                        "Warning, could not retrieve last update for zone, "
                        f"defaulting to {last_update}"
                    )
                else:
                    if datestring[0].lstrip() == "Today":
                        last_update = t
                    else:
                        if datestring[0].lstrip() == "Yesterday":
                            last_update = t - timedelta(days=1)
                        else:
                            tempdate = ("/".join((datestring[0], str(t.year)))).lstrip()
                            try:
                                last_update = datetime.strptime(tempdate, "%m/%d/%Y")
                            except ValueError:
                                LOG.warning(
                                    f"pyadtpulse couldn't convert date {last_update}, "
                                    f"defaulting to {last_update}"
                                )
                            if last_update > t:
                                last_update = last_update - relativedelta.relativedelta(
                                    years=1
                                )
                    try:
                        update_time = datetime.time(
                            datetime.strptime(datestring[1] + datestring[2], "%I:%M%p")
                        )
                    except ValueError:
                        update_time = datetime.time(last_update)
                        LOG.warning(
                            f"pyadtpulse couldn't convert time "
                            f"{datestring[1] + datestring[2]}, "
                            f"defaulting to {update_time}"
                        )
                    last_update = datetime.combine(last_update, update_time)

                # name = row.find("a", {"class": "p_deviceNameText"}).get_text()
                temp = row.find("span", {"class": "p_grayNormalText"})
                if temp is None:
                    break
                zone = int(
                    remove_prefix(
                        temp.get_text(),
                        "Zone\xa0",
                    )
                )
                state = remove_prefix(
                    row.find("canvas", {"class": "p_ic_icon_device"}).get("icon"),
                    "devStat",
                )
                temp_status = row.find("td", {"class": "p_listRow"}).find_next(
                    "td", {"class": "p_listRow"}
                )

                status = "Unknown"
                if temp_status is not None:
                    temp_status = temp_status.get_text()
                    if temp_status is not None:
                        temp_status = str(temp_status.replace("\xa0", ""))
                        if temp_status.startswith("Trouble"):
                            trouble_code = str(temp_status).split()
                            if len(trouble_code) > 1:
                                status = " ".join(trouble_code[1:])
                            else:
                                status = "Unknown trouble code"
                        else:
                            status = "Online"

                # parse out last activity (required dealing with "Yesterday 1:52 PM")
                #           last_activity = time.time()

                # id:    [integer]
                # name:  device name
                # tags:  sensor,[doorWindow,motion,glass,co,fire]
                # timestamp: timestamp of last activity
                # state: OK (device okay)
                #        Open (door/window opened)
                #        Motion (detected motion)
                #        Tamper (glass broken or device tamper)
                #        Alarm (detected CO/Smoke)
                #        Unknown (device offline)

                # update device state from ORB info
                if not self._zones:
                    LOG.warning("No zones exist")
                    return None
                if state != "Unknown":
                    gateway_online = True
                self._zones.update_device_info(zone, state, status, last_update)
                LOG.debug(
                    f"Set zone {zone} - to {state}, status {status} "
                    f"with timestamp {last_update}"
                )
            self._adt_service._set_gateway_status(gateway_online)
            self._last_updated = datetime.now()
            return self._zones

    async def _async_update_zones(self) -> Optional[List[ADTPulseFlattendZone]]:
        """Update zones asynchronously.

        Returns:
            List[ADTPulseFlattendZone]: a list of zones with their status

            None on error
        """
        with self._site_lock:
            if not self._zones:
                return None
            zonelist = await self._async_update_zones_as_dict(None)
            if not zonelist:
                return None
            return zonelist.flatten()

    def update_zones(self) -> Optional[List[ADTPulseFlattendZone]]:
        """Update zone status information.

        Returns:
            Optional[List[ADTPulseFlattendZone]]: a list of zones with status
        """
        coro = self._async_update_zones()
        return run_coroutine_threadsafe(coro, get_event_loop()).result()

    @property
    def updates_may_exist(self) -> bool:
        """Query whether updated sensor data exists.

        Returns:
            bool: True if updated data exists
        """
        # FIXME: this should actually capture the latest version
        # and compare if different!!!
        # ...this doesn't actually work if other components are also checking
        #  if updates exist
        return self._adt_service.updates_exist

    async def async_update(self) -> bool:
        """Force update site/zone data async with current data.

        Returns:
            bool: True if update succeeded
        """
        retval = await self._adt_service.async_update()
        if retval:
            self._last_updated = datetime.now()
        return retval

    def update(self) -> bool:
        """Force update site/zones with current data.

        Returns:
            bool: True if update succeeded
        """
        retval = self._adt_service.update()
        if retval:
            self._last_updated = datetime.now()
        return retval
