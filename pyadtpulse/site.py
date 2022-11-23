import logging
LOG = logging.getLogger(__name__)

import re
import json
import time
#import dateparser
from bs4 import BeautifulSoup
from pyadtpulse.const import ( ADT_ZONES_URI, ADT_ARM_DISARM_URI, ADT_ORB_URI, ADT_SYSTEM_URI, ADT_SUMMARY_URI, ADT_DEVICE_URI )


ADT_ALARM_AWAY    = 'away'
ADT_ALARM_HOME    = 'stay'
ADT_ALARM_OFF     = 'off'
ADT_ALARM_UNKNOWN = 'unknown'

ADT_NAME_TO_DEFAULT_TAGS = {
    'Door':     [ 'sensor', 'doorWindow' ],
    'Window':   [ 'sensor', 'doorWindow' ],
    'Motion':   [ 'sensor', 'motion' ],
    'Glass':    [ 'sensor', 'glass' ] ,
    'Gas':      [ 'sensor', 'co' ],
    'Carbon':   [ 'sensor', 'co' ],
    'Smoke':    [ 'sensor', 'smoke' ],
    'Flood':    [ 'sensor', 'flood' ],
    'Floor':    [ 'sensor', 'flood' ],
    'Moisture': [ 'sensor', 'flood' ]
}


def remove_prefix(text, prefix):
    return text[text.startswith(prefix) and len(prefix):]

class ADTPulseSite(object):
    def __init__(self, adt_service, site_id, name, summary_html_soup=None):
        """Represents an individual ADT Pulse site"""

        self._adt_service = adt_service
        self._id = site_id
        self._name = name
        self._zones = []
        self._status = ADT_ALARM_UNKNOWN
        self._sat = ''

        self._update_alarm_status(summary_html_soup)

    @property
    def id(self):
        return self._id

    @property
    def name(self):
        return self._name

    # FIXME: should this actually return if the alarm is going off!?  How do we
    # return state that shows the site is compromised??
    @property
    def status(self):
        """Returns the alarm status"""
        return self._status

    @property
    def is_away(self):
        return self._status == ADT_ALARM_AWAY

    @property
    def is_home(self):
        return self._status == ADT_ALARM_HOME

    @property
    def is_disarmed(self):
        return self._status == ADT_ALARM_OFF

    def _arm(self, mode):
        """Set the alarm arm mode to one of: off, home, away
        :param mode: alarm mode to set
        """
        LOG.debug(f"Setting ADT alarm '{self._name}' to '{mode}'")
        params = {
            'href'     : 'rest/adt/ui/client/security/setArmState',
            'armstate' : self._status, # existing state
            'arm'      : mode,          # new state
            'sat'      : self._sat
        }
        response = self._adt_service.query(ADT_ARM_DISARM_URI, method='POST',
                                           extra_headers= { 'Accept' : '*/*',
                                                            'Referer' : ADT_ARM_DISARM_URI.split('?')[0]},
                                           extra_params=params)
        if not response.ok:
            LOG.warning(f"Failed updating ADT Pulse alarm {self._name} to {mode} (http={response.status_code}")
        else:
            self._status = mode
            self.update()

    def arm_away(self):
        """Arm the alarm in Away mode"""
        self._arm(ADT_ALARM_AWAY)

    def arm_home(self):
        """Arm the alarm in Home mode"""
        self._arm(ADT_ALARM_HOME)

    def disarm(self):
        """Disarm the alarm"""
        self._arm(ADT_ALARM_OFF)

    @property
    def zones(self):
        """Return all zones registered with the ADT Pulse account (cached copy of last fetch)
           See Also fetch_zones()"""
        if self._zones:
            return self._zones

        return self.fetch_zones()

    @property
    def history(self):
        """Returns log of history for this zone (NOT IMPLEMENTED)"""
        return []

    def _update_alarm_status(self, summary_html_soup, update_zones=True):
        value = summary_html_soup.find('span', {'class': 'p_boldNormalTextLarge'})
        sat_location = 'security_button_0'
        if value:
            text = value.text
            if re.match('Disarmed', text):
                self._status = ADT_ALARM_OFF
            elif re.match('Armed Away', text):
                self._status = ADT_ALARM_AWAY
            elif re.match('Armed Stay', text):
                self._status = ADT_ALARM_HOME
            else:
                LOG.warning(f"Failed to get alarm status from '{text}'")
                self._status = ADT_ALARM_UNKNOWN

            LOG.debug("Alarm status = %s", self._status)

        sat_button = summary_html_soup.find('input', {
            'type': 'button',
            'id': sat_location
        })
        if sat_button and sat_button.has_attr('onclick'):
            on_click = sat_button['onclick']
            match = re.search(r'sat=([a-z0-9\-]+)', on_click)
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
        
        # if we should also update the zone details, force a fresh fetch of data from ADT Pulse
        if update_zones:
            self.fetch_zones()

    def fetch_zones(self):
        """Fetch a fresh copy of the zone data from ADT Pulse service"""

        # call ADT orb uri
        response = self._adt_service.query(ADT_ORB_URI,
                                           extra_headers= { 'Accept': '*/*',
                                                            'Referer': self._adt_service.make_url(ADT_SUMMARY_URI)}
                                                            )

        # summary.jsp contains more device id details
        response2 = self._adt_service.query(ADT_SYSTEM_URI,
                                            extra_headers= { 'Accept': '*/*',
                                                             'Referer': self._adt_service.make_url(ADT_ORB_URI)})
        
        soup = BeautifulSoup(response.text, 'html.parser')
        soup2 = BeautifulSoup(response2.text, 'html.parser')

        if not soup or not soup2:
            LOG.warning("Failed loading zone status from ADT Pulse service")
            LOG.debug(f"Failed ADT Pulse zone data response: %s", response.text)
            return

        zones = []
        regexDevice = "goToUrl\('device.jsp\?id=(\d*)'\);"
        for row in soup2.find_all("tr", {'class': 'p_listRow', 'onclick': True}):
            onClickValueText = row.get('onclick')
            result = re.findall(regexDevice, onClickValueText)

            # only proceed if regex succeeded, as some users have onClick links that include gateway.jsp
            if not result:
                LOG.debug(f"Failed regex match #{regexDevice} on #{onClickValueText} from ADT Pulse service, ignoringsy")
                continue

            device_id = result[0]
            deviceResponse = self._adt_service.query(ADT_DEVICE_URI+device_id,
                                                     extra_headers={ 'Referer': self._adt_service.make_url(ADT_DEVICE_URI)})

            if not deviceResponse:
                LOG.debug(f"Failed loading zone data from ADT Pulse service: %s", deviceResponse.text)
                return

            dName = dType = dZone = dStatus = dMan = ''
            deviceResponseSoup = BeautifulSoup(deviceResponse.text, 'html.parser')
            for devInfoRow in deviceResponseSoup.find_all("td", {'class', 'InputFieldDescriptionL'}):

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
                elif identityText == "MANUFACTURER/PROVIDER:":
                    dMan = value

            # NOTE: if empty string, this is the control panel
            if dZone != '':
                tags = None

                for search_term, default_tags in ADT_NAME_TO_DEFAULT_TAGS.items():
                    #convert to update first
                    if search_term.upper() in dType.upper():
                        tags = default_tags
                        break

                if not tags:
                    LOG.warning(f"Unknown sensor type for '{dType}', defaulting to doorWindow")
                    tags = [ 'sensor', 'doorWindow' ]

                zones.append({
                    "id":        f"sensor-{dZone}",
                    "zone":      dZone,
                    "name":      dName,
                    "status":    dStatus,
                    "state":     "",
                    "tags":      tags,
                    "timestamp": time.time() 
                })

        # FIXME: ensure the zones for the correct site are being loaded!!!

        # parse ADT's convulated html to get sensor status
        for row in soup.find_all("tr", {'class': 'p_listRow'}):
            name = row.find("a", {'class': 'p_deviceNameText'}).get_text()
            zone = int(remove_prefix(row.find("span", {'class': 'p_grayNormalText'}).get_text(), "Zone\xa0"))
            state = remove_prefix(row.find("canvas", {'class': 'p_ic_icon_device'}).get('icon'), 'devStat')

            # parse out last activity (required dealing with "Yesterday 1:52 PM")
            last_activity = time.time()

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
            for device in zones:
                if int(device['zone']) == zone:
                    device['state'] = state
                    break

        self._zones = zones
        return zones

    def fetch_zones_OLD(self):
        """Fetch a fresh copy of the zone data from ADT Pulse service"""
        response = self._adt_service.query(ADT_ZONES_URI)
        self._zones_json = response.json()
        LOG.debug("Result: %s", self._zones_json)
        
        if not self._zones_json:
            LOG.warning("Failed to load any zones from ADT Pulse service")
            LOG.debug(f"ADT Pulse service zone data response: {response}")
            return

        # FIXME: ensure the zones for the correct site are being loaded!!!

        # to simplify usage, flatten structure
        zones = self._zones_json.get('items')
        for zone in zones:
            del zone['deprecatedAction']
            del zone['devIndex']
            del zone['state']

            # insert simpler to access status field (e.g. Closed, Open)
            m = re.search(" - (.*)\n", zone['state']['statusTxt'])
            if m:
                zone['status'] = m.group(1)

            zone['tags'] = zone['tags'].split(',')
            zone['activityTs'] = int(zone['state']['activityTs'])

        self._zones = zones
        return self._zones

    def updates_may_exist(self):
        # FIXME: this should actually capture the latest version and compare if different!!!
        # ...this doesn't actually work if other components are also checking if updates exist
        return self._adt_service.updates_exist

    def update(self):
        """Force an update of the site and zones with current data from the service"""
        self._adt_service.update()
