import re
import json
import time
import logging
from bs4 import BeautifulSoup
from pyadtpulse.const import ( ADT_ZONES_URI, ADT_ARM_DISARM_URI )

LOG = logging.getLogger(__name__)

ADT_ALARM_AWAY    = 'away'
ADT_ALARM_HOME    = 'stay'
ADT_ALARM_OFF     = 'off'
ADT_ALARM_UNKNOWN = 'unknown'

class ADTPulseSite(object):
    def __init__(self, adt_service, site_id, name, summary_html_soup=None):
        """Represents an individual ADT Pulse site"""

        self._adt_service = adt_service
        self._id = site_id
        self._name = name
        self._zones = []
        self._status = ADT_ALARM_UNKNOWN

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
            'arm'      : mode          # new state
        }
        response = self._adt_service.query(ADT_ARM_DISARM_URI, method='POST',
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
        response = self._adt_service.query(ADT_ZONES_URI)
        self._zones_json = response.json()

        # FIXME: ensure the zones for the correct site are being loaded!!!

        # to simplify usage, flatten structure AND
        zones = response.json().get('items')
        for zone in zones:
            del zone['deprecatedAction']
            del zone['devIndex']

            # insert a simpler to access status field (e.g. Closed, Open)
            m = re.search(" - (.*)\n", zone['state']['statusTxt'])
            if m:
                zone['status'] = m.group(1)

            zone['tags'] = zone['tags'].split(',')

            zone['activityTs'] = int(zone['state']['activityTs'])
            del zone['state']

        self._zones = zones
        return self._zones

    def updates_may_exist(self):
        # FIXME: this should actually capture the latest version and compare if different!!!
        # ...this doesn't actually work if other components are also checking if updates exist
        return self._adt_service.updates_exist

    def update(self):
        """Force an update of the site and zones with current data from the service"""
        self._adt_service.update()
