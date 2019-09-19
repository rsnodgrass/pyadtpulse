"""Base Python Class for pyadtpulse"""

import time
import logging
import requests
from bs4 import BeautifulSoup

from pyadtpulse.const import ( API_HOST, API_PREFIX, ADT_LOGIN_URI, ADT_ZONES_URI )

LOG = logging.getLogger(__name__)

class PyADTPulse(object):
    """Base object for ADT Pulse."""

    def __init__(self, username=None, password=None, user_agent='pyadtpulse'):
        """Create a python interface to ADT Pulse service.
           :param username: ADT Pulse username
           :param password: ADT Pulse password
           :returns PyADTPulse base object
        """
        self.__session = requests.Session()
        self.__user_agent = user_agent
        self.__user_agent = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/77.0.3865.75 Safari/537.36'

        self.__version = None

        self.__headers = None
        self.__params = None
        self.__cookies = None

        # authenticate the user
        self.__username = username
        self.__password = password # TODO: ideally do NOT store this in memory...
        self.login()

        self._all_zones = None

    def __repr__(self):
        """Object representation."""
        return "<{0}: {1}>".format(self.__class__.__name__, self.__username)

    @property
    def version(self):
        if not self.__version:
            # FIXME...
            # split out version from ['Location'] = /myhome/16.0.0-131/access/signin.jsp
            # self.__version = resp.headers['Location'].rsplit('/', 2)[0]
            self.__version = '16.0.0-131'

        return self.__version

    def login(self):
        self.__authenticated = False

        """Login to the ADT Pulse account and generate access token"""
        self.reset_headers()

        response = self.query(
            ADT_LOGIN_URI, method='POST',
            extra_params={
                'usernameForm' : self.__username,
                'passwordForm' : self.__password,
                'sun'          : 'yes'
            },
            force_login=False)

        html = BeautifulSoup(response.text, 'html.parser') # text or content?
        error = html.find('div', {'id': 'warnMsgContents'})
        if error:
            error_string = error.text
            LOG.debug("Error logging into ADT Pulse %s", error_string)
            self.__authenticated = False
            return

        self.__authenticated = True
        self.__authenticated_timestamp = time.time()
        LOG.info(f"Authenticated ADT Pulse account {self.__username}")

    @property
    def is_connected(self):
        """Connection status of client with ADT Pulse cloud service."""
        return self.__authenticated

    def reset_headers(self):
        """Reset the default headers and params."""
        self.__headers = {
            'Host':          'portal.adtpulse.com',
            'Accept':        'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'User-Agent':    self.__user_agent
        }
        self.__params = {}

    def query(self, uri, method='GET', extra_params=None, extra_headers=None,
              retry=3, force_login=True, version_prefix=True):
        """
        Returns a JSON object for an HTTP request.
        :param url: API URL
        :param method: Specify the method GET, POST or PUT (default=POST)
        :param extra_params: Dictionary to be appended on request.body
        :param extra_headers: Dictionary to be apppended on request.headers
        :param retry: Retry attempts for the query (default=3)
        """
        response = None
        self.reset_headers() # ensure the headers and params are reset to the bare minimum

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

            # override request.body or request.headers dictionary
            params = self.__params
            if extra_params:
                params.update(extra_params)
            if 'password' not in params:
                LOG.debug("Params: %s", params)

            headers = self.__headers
            if extra_headers:
                headers.update(extra_headers)
            LOG.debug("Headers: %s", headers)

#            if self.__cookies:
            LOG.debug("Cookies: %s", self.__cookies)

            # define connection method
            response = None
            if method == 'GET':
                response = self.__session.get(url, headers=headers, cookies=self.__cookies)
            elif method == 'PUT':
                response = self.__session.put(url, headers=headers, cookies=self.__cookies, json=params)
            elif method == 'POST':
                response = self.__session.post(url, headers=headers, cookies=self.__cookies, json=params)
            else:
                LOG.error("Invalid request method '%s'", method)
                return None

            LOG.debug("Response = %s", response.content)

            if response and (response.status_code == 200):
                break # success!

        return response

    @property
    def zones(self):
        """Return all zones registered with the ADT Pulse account."""
        if self._all_zones:
            return self._all_zones

        response = self.query(ADT_ZONES_URI)
        LOG.debug("Response zones = %s", response.json)

        self._all_zones = response.json.get('items')
        # for zone in all_zones:

        # FIXME: modify json returned in each item?  E.g.
        # - delete deprecatedAction
        # - remove state and move the key variable as first class (e.g. statusTxt, activityTs, status = state.icon)

        return self._all_zones

    def alarm_status(self):
        response = self.query(ADT_SUMMARY_URI)

        # FIXME parse out state
        html = BeautifulSoup(response.content, 'html.parser')
        alarm_status = html.find('span', 'p_boldNormalTextLarge')
#        if not alarm_status:
#            raise LoginException("Cannot find alarm state information")

        for string in alarm_status.strings:
            status, _ = string.split('.', 1)
 
        return status

    @property
    def armed(self, mode=None):
        """Returns true if the alarm is armed
        :param mode: optional arm mode to determine if the alarm is set to
        """
        return False  # FIXME

    def arm(self, mode='away'):
        """Set the alarm arm mode to one of: off, home, away
        :param mode: alarm mode to set (default=away)
        """
        LOG.debug(f"Setting alarm mode to '{type}'")
        response = self.query(ADT_ARM_DISARM_URI,
                              extra_params = {
                                 'href'     : 'rest/adt/ui/client/security/setArmState',
                                 'armstate' : self.__alarm_state,
                                 'arm'      : mode
                              })

    def disarm(self):
        """Disarm the alarm"""
        self.arm(mode='off')

    def update(self, update_zones=False):
        """Refresh any cached state."""
        self.login()

        if update_zones:
            # clear cache and force update
            self._all_zones = None
            force_update = self.sensors

    def logout(self):
        LOG.info(f"Logging {self.__username} out of ADT Pulse") 
        self.query(ADT_LOGOUT_URI)
        self.__authenticated = False
