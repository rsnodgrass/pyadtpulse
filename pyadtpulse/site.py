"""Module representing an ADT Pulse Site."""

import logging
import re
from asyncio import get_event_loop, run_coroutine_threadsafe
from datetime import datetime, timedelta
from threading import RLock
from typing import List, Optional, Union
from warnings import warn

# import dateparser
from bs4 import BeautifulSoup
from dateutil import relativedelta

from .alarm_panel import ADTPulseAlarmPanel
from .const import ADT_DEVICE_URI, ADT_SYSTEM_URI, LOG
from .pulse_connection import ADTPulseConnection
from .util import DebugRLock, make_soup, remove_prefix
from .zones import (
    ADT_NAME_TO_DEFAULT_TAGS,
    ADTPulseFlattendZone,
    ADTPulseZoneData,
    ADTPulseZones,
)


class ADTPulseSite:
    """Represents an individual ADT Pulse site."""

    __slots__ = (
        "_adt_service",
        "_id",
        "_name",
        "_last_updated",
        "_alarm_panel",
        "_zones",
        "_site_lock",
    )

    def __init__(self, adt_service: ADTPulseConnection, site_id: str, name: str):
        """Initialize.

        Args:
            adt_service (PyADTPulse): a PyADTPulse object
            site_id (str): site ID
            name (str): site name
        """
        self._adt_service = adt_service
        self._id = site_id
        self._name = name
        self._last_updated = datetime(1970, 1, 1)
        self._zones = ADTPulseZones()
        self._site_lock: Union[RLock, DebugRLock]
        if isinstance(self._adt_service._attribute_lock, DebugRLock):
            self._site_lock = DebugRLock("ADTPulseSite._site_lock")
        else:
            self._site_lock = RLock()
        self._alarm_panel: Optional[ADTPulseAlarmPanel] = None

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

    def arm_home(self, force_arm: bool) -> bool:
        """Arm system home."""
        if self.alarm_control_panel is None:
            raise RuntimeError("Cannot arm system home, no control panels exist")
        return self.alarm_control_panel.arm_home(self._adt_service, force_arm=force_arm)

    def arm_away(self, force_arm: bool) -> bool:
        """Arm system away."""
        if self.alarm_control_panel is None:
            raise RuntimeError("Cannot arm system away, no control panels exist")
        return self.alarm_control_panel.arm_away(self._adt_service, force_arm=force_arm)

    def disarm(self) -> bool:
        """Disarm system."""
        if self.alarm_control_panel is None:
            raise RuntimeError("Cannot disarm system, no control panels exist")
        return self.alarm_control_panel.disarm(self._adt_service)

    async def async_arm_home(self, force_arm: bool) -> bool:
        """Arm system home async."""
        if self.alarm_control_panel is None:
            raise RuntimeError("Cannot arm system home, no control panels exist")
        return await self.alarm_control_panel.async_arm_home(
            self._adt_service, force_arm=force_arm
        )

    async def async_arm_away(self, force_arm: bool) -> bool:
        """Arm system away async."""
        if self.alarm_control_panel is None:
            raise RuntimeError("Cannot arm system away, no control panels exist")
        return await self.alarm_control_panel.async_arm_away(
            self._adt_service, force_arm=force_arm
        )

    async def async_disarm(self) -> bool:
        """Disarm system async."""
        if self.alarm_control_panel is None:
            raise RuntimeError("Cannot disarm system, no control panels exist")
        return await self.alarm_control_panel.async_disarm(self._adt_service)

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
    def alarm_control_panel(self) -> Optional[ADTPulseAlarmPanel]:
        """Return the alarm panel object for the site.

        Returns:
            Optional[ADTPulseAlarmPanel]: the alarm panel object
        """
        return self._alarm_panel

    @property
    def history(self):
        """Return log of history for this zone (NOT IMPLEMENTED)."""
        raise NotImplementedError

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
            # FIXME: fix when have gateway device
            # self._adt_service._set_gateway_status(gateway_online)
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
