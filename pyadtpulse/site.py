"""Module representing an ADT Pulse Site."""
import logging
import re
import time
from asyncio import get_event_loop, run_coroutine_threadsafe
from typing import List, Optional

# import dateparser
from bs4 import BeautifulSoup

from pyadtpulse import PyADTPulse
from pyadtpulse.const import ADT_ARM_DISARM_URI, ADT_DEVICE_URI, ADT_SYSTEM_URI
from pyadtpulse.util import handle_response, make_soup, remove_prefix
from pyadtpulse.zones import (
    ADT_NAME_TO_DEFAULT_TAGS,
    ADTPulseZoneData,
    ADTPulseFlattendZone,
    ADTPulseZones,
)

ADT_ALARM_AWAY = "away"
ADT_ALARM_HOME = "stay"
ADT_ALARM_OFF = "off"
ADT_ALARM_UNKNOWN = "unknown"


LOG = logging.getLogger(__name__)


class ADTPulseSite(object):
    """Represents an individual ADT Pulse site."""

    def __init__(
        self,
        adt_service: PyADTPulse,
        site_id: str,
        name: str,
        summary_html_soup: Optional[BeautifulSoup] = None,
    ):
        """Initialize.

        Args:
            adt_service (PyADTPulse): a PyADTPulse object
            site_id (str): site ID
            name (str): site name
            summary_html_soup (Optional[BeautifulSoup], optional):
                A BeautifulSoup Object. Defaults to None.
        """
        self._adt_service = adt_service
        self._id = site_id
        self._name = name
        coro = self._fetch_zones()
        run_coroutine_threadsafe(coro, get_event_loop()).done()
        self._status = ADT_ALARM_UNKNOWN
        self._sat = ""
        self._last_updated = 0.0
        self._zones = ADTPulseZones()
        if summary_html_soup is not None:
            coro2 = self._update_alarm_status(summary_html_soup)
            run_coroutine_threadsafe(coro2, get_event_loop())

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
        return self._status

    @property
    def is_away(self) -> bool:
        """Return wheter the system is armed away.

        Returns:
            bool: True if armed away
        """
        return self._status == ADT_ALARM_AWAY

    @property
    def is_home(self) -> bool:
        """Return whether system is armed at home/stay.

        Returns:
            bool: True if system is armed home/stay
        """
        return self._status == ADT_ALARM_HOME

    @property
    def is_disarmed(self) -> bool:
        """Return whether the system is disarmed.

        Returns:
            bool: True if the system is disarmed
        """
        return self._status == ADT_ALARM_OFF

    @property
    def last_updated(self) -> float:
        """Return time site last updated.

        Returns:
            float: the time site last updated in UTC
        """
        return self._last_updated

    async def _arm(self, mode: str) -> bool:
        """Set the alarm arm mode to one of: off, home, away.

        :param mode: alarm mode to set
        """
        LOG.debug(f"Setting ADT alarm '{self._name}' to '{mode}'")
        params = {
            "href": "rest/adt/ui/client/security/setArmState",
            "armstate": self._status,  # existing state
            "arm": mode,  # new state
            "sat": self._sat,
        }
        response = await self._adt_service._async_query(
            ADT_ARM_DISARM_URI,
            method="POST",
            extra_params=params,
            timeout=10,
        )

        if not handle_response(
            response,
            logging.WARNING,
            f"Failed updating ADT Pulse alarm {self._name} to {mode}",
        ):
            return False
        self._last_updated = time.time()
        self._status = mode
        return True

    def arm_away(self) -> bool:
        """Arm the alarm in Away mode.

        Returns:
            bool: True if arm succeeded
        """
        coro = self._arm(ADT_ALARM_AWAY)
        return run_coroutine_threadsafe(coro, get_event_loop()).result()

    def arm_home(self) -> bool:
        """Arm the alarm in Home mode.

        Returns:
            bool: True if arm succeeded
        """
        coro = self._arm(ADT_ALARM_HOME)
        return run_coroutine_threadsafe(coro, get_event_loop()).result()

    def disarm(self) -> bool:
        """Disarm the alarm.

        Returns:
            bool: True if disarm succeeded
        """
        coro = self._arm(ADT_ALARM_OFF)
        return run_coroutine_threadsafe(coro, get_event_loop()).result()

    async def async_arm_away(self) -> bool:
        """Arm alarm away async.

        Returns:
            bool: True if arm succeeded
        """
        return await self._arm(ADT_ALARM_AWAY)

    async def async_arm_home(self) -> bool:
        """Arm alarm home async.

        Returns:
            bool: True if arm succeeded
        """
        return await self._arm(ADT_ALARM_HOME)

    async def async_disarm(self) -> bool:
        """Disarm alarm async.

        Returns:
            bool: True if disarm succeeded
        """
        return await self._arm(ADT_ALARM_OFF)

    @property
    def zones(self) -> Optional[List[ADTPulseFlattendZone]]:
        """Return all zones registered with the ADT Pulse account.

        (cached copy of last fetch)
        See Also fetch_zones()
        """
        if self._zones:
            return self._zones.flatten()
        coro = self._fetch_zones()
        result = run_coroutine_threadsafe(coro, get_event_loop()).result()
        if not result:
            return None
        return result.flatten()

    @property
    def zones_as_dict(self) -> Optional[ADTPulseZones]:
        """Return zone information in dictionary form.

        Returns:
            ADTPulseZones: all zone information
        """
        return self._zones

    @property
    def history(self):
        """Return log of history for this zone (NOT IMPLEMENTED)."""
        raise NotImplementedError

    async def _update_alarm_status(
        self, summary_html_soup: BeautifulSoup, update_zones: Optional[bool] = False
    ) -> None:
        LOG.debug("Updating alarm status")
        value = summary_html_soup.find("span", {"class": "p_boldNormalTextLarge"})
        sat_location = "security_button_0"
        if value:
            text = value.text
            if re.match("Disarmed", text):
                self._status = ADT_ALARM_OFF
            elif re.match("Armed Away", text):
                self._status = ADT_ALARM_AWAY
            elif re.match("Armed Stay", text):
                self._status = ADT_ALARM_HOME
            else:
                LOG.warning(f"Failed to get alarm status from '{text}'")
                self._status = ADT_ALARM_UNKNOWN

            LOG.debug(f"Alarm status = {self._status}")

        self._last_updated = time.time()

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

        if update_zones:
            await self.async_update_zones()

    async def _fetch_zones(self) -> Optional[ADTPulseZones]:
        """Fetch zones for a site.

        Returns:
            ADTPulseZones

            None if an error occurred
        """
        # summary.jsp contains more device id details
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

                # FIXME: parse last activity
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
                        f"Unknown sensor type for '{dType}', defaulting to doorWindow"
                    )
                    tags = ("sensor", "doorWindow")
                LOG.debug(f"Adding sensor {dName} id: sensor-{dZone}")
                LOG.debug(f"Status: {dStatus}, tags {tags}")

                self._zones.update(
                    {int(dZone): {"name": dName, "status": dStatus, "tags": tags}}
                )
        self._last_updated = time.time()
        return self._zones

        # FIXME: ensure the zones for the correct site are being loaded!!!

    async def async_update_zones_as_dict(self) -> Optional[ADTPulseZones]:
        """Update zone status information asynchronously.

        Returns:
            ADTPulseZones: a dictionary of zones with status
            None if an error occurred
        """
        if self._zones is None:
            if await self._fetch_zones() is None:
                LOG.error("Could not update zones, none found")
                return None

        LOG.debug(f"fetching zones for site { self._id}")
        # call ADT orb uri
        soup = await self._adt_service._query_orb(
            logging.WARNING, "Could not fetch zone status updates"
        )

        if soup is None:
            return None

        # parse ADT's convulated html to get sensor status
        for row in soup.find_all("tr", {"class": "p_listRow"}):
            # name = row.find("a", {"class": "p_deviceNameText"}).get_text()
            zone = int(
                remove_prefix(
                    row.find("span", {"class": "p_grayNormalText"}).get_text(),
                    "Zone\xa0",
                )
            )
            state = remove_prefix(
                row.find("canvas", {"class": "p_ic_icon_device"}).get("icon"), "devStat"
            )

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
            self._zones.update_state(zone, state)

            LOG.debug(f"Setting zone {zone} - to {state}")

        self._last_updated = time.time()
        return self._zones

    async def async_update_zones(self) -> Optional[List[ADTPulseFlattendZone]]:
        """Update zones asynchronously.

        Returns:
            List[ADTPulseFlattendZone]: a list of zones with their status

            None on error
        """
        if not self._zones:
            return None
        zonelist = await self.async_update_zones_as_dict()
        if not zonelist:
            return None
        return zonelist.flatten()

    def update_zones(self) -> Optional[List[ADTPulseFlattendZone]]:
        """Update zone status information.

        Returns:
            Optional[List[ADTPulseFlattendZone]]: a list of zones with status
        """
        coro = self.async_update_zones()
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
            self._last_updated = time.time()
        return retval

    def update(self) -> bool:
        """Force update site/zones with current data.

        Returns:
            bool: True if update succeeded
        """
        retval = self._adt_service.update()
        if retval:
            self._last_updated = time.time()
        return retval
