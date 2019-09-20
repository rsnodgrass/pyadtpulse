import re
import json
import time
import logging
from bs4 import BeautifulSoup
from pyadtpulse.const import ( ADT_ZONES_URI, ADT_ARM_DISARM_URI )

LOG = logging.getLogger(__name__)

ADT_ALARM_AWAY = 'away'
ADT_ALARM_HOME = 'home'
ADT_ALARM_OFF  = 'off'

class ADTPulseSite(object):
    def __init__(self, adt_service, site_id, name, summary_html):
        """Represents an individual ADT Pulse site"""

        self._adt_service = adt_service
        self._id = site_id
        self._name = name

        self._update(summary_html)

        self._zones = []

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
    def armed(self):
        """Returns true if the alarm is armed"""
        return self._status != 'disarmed'

    def _arm(self, mode):
        """Set the alarm arm mode to one of: off, home, away
        :param mode: alarm mode to set
        """
        LOG.debug(f"Setting alarm to '{mode}'")
        response = self._adt_service.query(ADT_ARM_DISARM_URI, method='POST',
                                           extra_params = {
                                              'href'     : 'rest/adt/ui/client/security/setArmState',
                                              'armstate' : self._status, # existing state
                                              'arm'      : mode          # new state
                                           })
        self._status = mode

    def arm_away(self):
        self._arm(ADT_ALARM_AWAY)

    def arm_home(self):
        self._arm(ADT_ALARM_HOME)

    def disarm(self):
        """Disarm the alarm"""
        self._arm(ADT_ALARM_OFF)

    def _update(self, summary_html):
        soup = BeautifulSoup(summary_html, 'html.parser')

        status_orb = soup.find('canvas', {'id': 'ic_orb'})
        if status_orb:
            self._status = status_orb['orb']
            LOG.debug("Alarm status = %s", self._status)
        else:
            LOG.error("Failed to find alarm status!")

    @property
    def zones(self):
        """Return all zones registered with the ADT Pulse account."""
        # FIXME: check if the timestamp is stale --> fetch the latest copy

        if not self._adt_service.updates_exist:
            return

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

        return zones


    @property
    def history(self):
        """Returns log of history for this zone (NOT IMPLEMENTED)"""
        return []