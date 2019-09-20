"""Base Python Class for pyadtpulse"""

import re
import time
import logging
import requests
from bs4 import BeautifulSoup

from pyadtpulse.const import ( API_HOST, API_PREFIX, ADT_LOGIN_URI, ADT_ZONES_URI )

LOG = logging.getLogger(__name__)

ADT_ALARM_AWAY = 'away'
ADT_ALARM_HOME = 'home'
ADT_ALARM_OFF  = 'off'

class PyADTPulse(object):
    """Base object for ADT Pulse."""

    def __init__(self, username=None, password=None, user_agent='pyadtpulse'):
        """Create a python interface to ADT Pulse service.
           :param username: ADT Pulse username
           :param password: ADT Pulse password
           :returns PyADTPulse base object
        """
        self.__session = requests.Session()
        self.__cookies = None
        self.__user_agent = user_agent
        self.__api_version = None

        # authenticate the user
        self.__username = username
        self.__password = password # TODO: ideally DON'T store this in memory...
        self.login()

        self.__sites = []
        self._site_id = None
        self._all_zones = None

    def __repr__(self):
        """Object representation."""
        return "<{0}: {1}>".format(self.__class__.__name__, self.__username)

    @property
    def version(self):
        if not self.__api_version:
            response = self.__session.get(API_HOST)
            m = re.search("/myhome/(.+)/access", response.url)
            if m:
                self.__api_version = m.group(1)
                LOG.debug("Discovered ADT Pulse version %s", self.__api_version)
            else:
                self.__api_version = '16.0.0-131'
                LOG.warn("Couldn't auto-detect ADT Pulse version, defaulting to %s", self.__api_version)

        return self.__api_version

    def _update_sites(self, summary_html):
        soup = BeautifulSoup(summary_html, 'html.parser')

        sites = []

        # typically, ADT Pulse accounts have only a single site (premise/location)
        singlePremise = soup.find('span', {'id': 'p_singlePremise'})
        if singlePremise:
            signout_info = soup.find('a', {'class': 'p_signoutlink'})
            LOG.warn("SURL=%s", signout_info.text)
            m = re.search("networkid=(.+)&", signout_info.text)
            if m:
                site_id = m.group(1)
                LOG.info(f"Found site id {site_id}")
                sites.append( ADTPulseSite(self, site_id, singlePremise.text) )
            else:
                LOG.warn("Couldn't find site id in %s!", signout_info)
        else:
            LOG.error("ADT Pulse accounts with multiple sites not yet supported!!!")

        self.__sites = sites
        LOG.debug(f"Discovered ADT Pulse sites: {self.__sites}")
# 
# ...and current network id from:
# <a id="p_signout1" class="p_signoutlink" href="/myhome/16.0.0-131/access/signout.jsp?networkid=150616za043597&partner=adt" onclick="return flagSignOutInProcess();">
#
# ... or perhaps better, just extract all from /system/settings.jsp



    def login(self):
        self.__authenticated = False

        """Login to the ADT Pulse account and generate access token"""
        response = self.query(
            ADT_LOGIN_URI, method='POST',
            extra_params={
                'usernameForm' : self.__username,
                'passwordForm' : self.__password,
                'sun'          : 'yes'
            },
            force_login=False)

        soup = BeautifulSoup(response.text, 'html.parser')
        error = soup.find('div', {'id': 'warnMsgContents'})
        if error:
            error_string = error.text
            LOG.error("ADT Pulse response: %s", error_string)
            self.__authenticated = False
            return

        self.__authenticated = True
        self.__authenticated_timestamp = time.time()
        LOG.info(f"Authenticated ADT Pulse account {self.__username}")

        self._update_sites(response.text)

    @property
    def is_connected(self):
        """Connection status of client with ADT Pulse cloud service."""
        #self.__authenticated_timestamp
        return self.__authenticated # FIXME: timeout automatically based on ADT default expiry?

    def query(self, uri, method='GET', extra_params=None, extra_headers=None,
              retry=3, force_login=True, version_prefix=True):
        """
        Returns a JSON object for an HTTP request.
        :param url: API URL
        :param method: GET, POST or PUT (default=POST)
        :param extra_params: Dictionary to be appended to request.body
        :param extra_headers: Dictionary to be apppended to request.headers
        :param retry: Retry attempts for the query (default=3)
        """
        response = None

        # automatically attempt to login, if not connected
        if force_login and not self.is_connected:
            self.login()

        url = f"{API_HOST}{API_PREFIX}{self.version}{uri}"

        loop = 0
        while loop <= retry:
            loop += 1
            LOG.debug(f"Attempting {method} {url} (try {loop}/{retry})")

            # FIXME: reauthenticate if received:
            # "You have not yet signed in or you have been signed out due to inactivity."

            # update default headers and body/json values
            params = {}
            if extra_params:
                params.update(extra_params)

            headers = { 'User-Agent': self.__user_agent }
            if extra_headers:
                headers.update(extra_headers)

            # define connection method
            if method == 'GET':
                response = self.__session.get(url, headers=headers, cookies=self.__cookies)
            elif method == 'POST':
                response = self.__session.post(url, headers=headers, cookies=self.__cookies, data=params)
            else:
                LOG.error("Invalid request method '%s'", method)
                return None

            if response and (response.status_code == 200):
                break # success!

        return response

    def update(self, update_zones=False):
        """Refresh any cached state."""
        self.login()

        if update_zones:
            # clear cache and force update
            self._all_zones = None
            force_update = self.sensors

    @property
    def sites(self):
        """Return all sites for this ADT Pulse account"""
        return self.__sites

    def logout(self):
        LOG.info(f"Logging {self.__username} out of ADT Pulse") 
        self.query(ADT_LOGOUT_URI)
        self.__authenticated = False


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
        LOG.debug(f"Setting alarm mode to '{type}'")
        response = self.query(ADT_ARM_DISARM_URI,
                              extra_params = {
                                 'href'     : 'rest/adt/ui/client/security/setArmState',
                                 'armstate' : self.__alarm_state,
                                 'arm'      : mode
                              })

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
        if self._zones:
            return self._zones

        response = self.query(ADT_ZONES_URI)
        LOG.debug("Response zones = %s", response.json)

   #     self._all_zones = response.json.get('items')
        # for zone in all_zones:

        # FIXME: modify json returned in each item?  E.g.
        # - delete deprecatedAction
        # - remove state and move the key variable as first class (e.g. statusTxt, activityTs, status = state.icon)

        return self._zones