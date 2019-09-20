"""Base Python Class for pyadtpulse"""

import re
import time
import logging
import requests
from bs4 import BeautifulSoup

from pyadtpulse.const import ( API_HOST, API_PREFIX, ADT_LOGIN_URI, ADT_LOGOUT_URI, ADT_SYNC_CHECK_URI )
from pyadtpulse.site import ADTPulseSite

LOG = logging.getLogger(__name__)

class PyADTPulse(object):
    """Base object for ADT Pulse service."""

    def __init__(self, username=None, password=None, user_agent='pyadtpulse'):
        """Create a python interface to the ADT Pulse service.
           :param username: ADT Pulse username
           :param password: ADT Pulse password
        """
        self._session = requests.Session()
        self._cookies = None
        self._user_agent = user_agent
        self._api_version = None

        self._sync_timestamp = 0
        self._sync_token = '0-0-0'

        self._sites = []

        # authenticate the user
        self._username = username
        self._password = password # TODO: ideally DON'T store this in memory...
        self.login()

    def __repr__(self):
        """Object representation."""
        return "<{0}: {1}>".format(self._class__.__name__, self._username)

    @property
    def username(self):
        return self._username

    @property
    def version(self):
        if not self._api_version:
            response = self._session.get(API_HOST)
            m = re.search("/myhome/(.+)/access", response.url)
            if m:
                self._api_version = m.group(1)
                LOG.debug("Discovered ADT Pulse version %s", self._api_version)
            else:
                self._api_version = '16.0.0-131'
                LOG.warn("Couldn't auto-detect ADT Pulse version, defaulting to %s", self._api_version)

        return self._api_version

    def _update_sites(self, summary_html):
        soup = BeautifulSoup(summary_html, 'html.parser')

        sites = []

        # typically, ADT Pulse accounts have only a single site (premise/location)
        singlePremise = soup.find('span', {'id': 'p_singlePremise'})
        if singlePremise:
            signout_info = soup.find('a', {'class': 'p_signoutlink'})
            LOG.warn("SURL=%s", signout_info.text)
            signout_info = '<a class="p_signoutlink" href="/myhome/16.0.0-131/access/signout.jsp?networkid=150616za043597&amp;partner=adt" id="p_signout1" onclick="return flagSignOutInProcess();">'
            m = re.search("networkid=(.+)&", signout_info)
            if m:
                site_id = m.group(1)
                LOG.debug(f"Discovered site id {site_id}: {singlePremise.text}")
                sites.append( ADTPulseSite(self, site_id, singlePremise.text, summary_html) )
            else:
                LOG.warn("Couldn't find site id in %s!", signout_info)
        else:
            LOG.error("ADT Pulse accounts with MULTIPLE sites not yet supported!!!")

        self._sites = sites

# ...and current network id from:
# <a id="p_signout1" class="p_signoutlink" href="/myhome/16.0.0-131/access/signout.jsp?networkid=150616za043597&partner=adt" onclick="return flagSignOutInProcess();">
#
# ... or perhaps better, just extract all from /system/settings.jsp

    def login(self):
        self._authenticated = False

        """Login to the ADT Pulse account and generate access token"""
        response = self.query(
            ADT_LOGIN_URI, method='POST',
            extra_params={
                'usernameForm' : self._username,
                'passwordForm' : self._password,
                'sun'          : 'yes'
            },
            force_login=False)

        soup = BeautifulSoup(response.text, 'html.parser')
        error = soup.find('div', {'id': 'warnMsgContents'})
        if error:
            error_string = error.text
            LOG.error("ADT Pulse response: %s", error_string)
            self._authenticated = False
            return

        self._authenticated = True
        self._authenticated_timestamp = time.time()
        LOG.info(f"Authenticated ADT Pulse account {self._username}")

        self._update_sites(response.text)

    def logout(self):
        LOG.info(f"Logging {self._username} out of ADT Pulse") 
        self.query(ADT_LOGOUT_URI)
        self._authenticated = False

    @property
    def updates_exist(self):
        response = self.query(ADT_SYNC_CHECK_URI, extra_params={'ts': self._sync_timestamp})
        self._sync_timestamp = time.time()

        if response.content != self._sync_token:
            LOG.debug(f"Sync token {response.content} != existing {self._sync_token}")
            self._sync_token = response.content
            return True

        return False

    @property
    def is_connected(self):
        """Connection status of client with ADT Pulse cloud service."""
        #self._authenticated_timestamp
        return self._authenticated # FIXME: timeout automatically based on ADT default expiry?

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

            headers = { 'User-Agent': self._user_agent }
            if extra_headers:
                headers.update(extra_headers)

            # define connection method
            if method == 'GET':
                response = self._session.get(url, headers=headers, cookies=self._cookies)
            elif method == 'POST':
                response = self._session.post(url, headers=headers, cookies=self._cookies, data=params)
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
        return self._sites
