"""Base Python Class for pyadtpulse"""

import logging
import re
import time
from typing import Dict, List, Optional

from bs4 import BeautifulSoup
from requests import HTTPError, Response, Session

from pyadtpulse.const import (
    ADT_DEFAULT_HTTP_HEADERS,
    ADT_LOGIN_URI,
    ADT_LOGOUT_URI,
    ADT_SUMMARY_URI,
    ADT_SYNC_CHECK_URI,
    API_PREFIX,
    DEFAULT_API_HOST,
)
from pyadtpulse.site import ADTPulseSite
from pyadtpulse.util import handle_response

LOG = logging.getLogger(__name__)


class PyADTPulse(object):
    """Base object for ADT Pulse service."""

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        fingerprint: Optional[str] = None,
        user_agent=ADT_DEFAULT_HTTP_HEADERS["User-Agent"],
    ):
        """Create a python interface to the ADT Pulse service.
        :param username: ADT Pulse username
        :param password: ADT Pulse password
        """
        self._session = Session()
        self._session.headers.update(ADT_DEFAULT_HTTP_HEADERS)
        self._user_agent = user_agent
        self._api_version = None

        self._sync_timestamp = 0
        self._sync_token = "0-0-0"

        self._sites = []

        self._api_host = DEFAULT_API_HOST

        # authenticate the user
        self._authenticated = False

        # FIXME: should username and password really be optional?
        self._username = username
        self._password = password
        self._fingerprint = fingerprint

        self.login()

    def __repr__(self) -> str:
        """Object representation."""
        return "<{0}: {1}>".format(self.__class__.__name__, self._username)

    # ADTPulse API endpoint is configurable (besides default US ADT Pulse endpoint) to
    # support testing as well as alternative ADT Pulse endpoints such as
    # portal-ca.adtpulse.com
    def set_service_host(self, host: str) -> None:
        """Override the default ADT Pulse host (e.g. to point to
        'portal-ca.adtpulse.com')"""
        self._api_host = f"https://{host}"
        self._session.headers.update({"Host": host})

    def make_url(self, uri: str) -> str:
        return f"{self._api_host}{API_PREFIX}{self.version}{uri}"

    @property
    def username(self) -> Optional[str]:
        return self._username

    @property
    def version(self) -> str:
        if not self._api_version:
            response = self._session.get(self._api_host)
            m = re.search("/myhome/(.+)/access", response.url)
            if m:
                self._api_version = m.group(1)
                LOG.debug(
                    "Discovered ADT Pulse version %s at %s",
                    self._api_version,
                    self._api_host,
                )
            else:
                self._api_version = "16.0.0-131"
                LOG.warning(
                    "Couldn't auto-detect ADT Pulse version, defaulting to %s",
                    self._api_version,
                )

        return self._api_version

    def _update_sites(self, summary_html: str) -> None:
        soup = BeautifulSoup(summary_html, "html.parser")

        if not self._sites:
            self._initialize_sites(soup)
        else:
            # FIXME: this will have to be fixed once multiple ADT sites
            # are supported, since the summary_html only represents the
            # alarm status of the current site!!
            if len(self._sites) > 1:
                LOG.error(
                    (
                        "pyadtpulse DOES NOT support an ADT account ",
                        "with multiple sites yet!!!",
                    )
                )

            for site in self._sites:
                site._update_alarm_status(soup, update_zones=True)

    def _initialize_sites(self, soup: BeautifulSoup) -> None:
        sites = []

        # typically, ADT Pulse accounts have only a single site (premise/location)
        singlePremise = soup.find("span", {"id": "p_singlePremise"})
        if singlePremise:
            site_name = singlePremise.text
            signout_link = soup.find("a", {"class": "p_signoutlink"}).get("href")
            m = re.search("networkid=(.+)&", signout_link)
            if m:
                site_id = m.group(1)
                LOG.debug(f"Discovered site id {site_id}: {site_name}")
                sites.append(ADTPulseSite(self, site_id, site_name, soup))
            else:
                LOG.warning(
                    f"Couldn't find site id for '{site_name}' in '{signout_link}'"
                )
        else:
            LOG.error(
                (
                    "ADT Pulse accounts with 2FA enabled"
                    " (create new users without 2FA) or with MULTIPLE sites ",
                    " not supported!!!",
                )
            )

        self._sites = sites

    # ...and current network id from:
    # <a id="p_signout1" class="p_signoutlink"
    # href="/myhome/16.0.0-131/access/signout.jsp?networkid=150616za043597&partner=adt"
    # onclick="return flagSignOutInProcess();">
    #
    # ... or perhaps better, just extract all from /system/settings.jsp

    def login(self) -> None:
        self._authenticated = False
        LOG.debug(f"Authenticating to ADT Pulse cloud service as {self._username}")

        """Login to the ADT Pulse account and generate access token"""
        response = self.query(
            ADT_LOGIN_URI,
            method="POST",
            extra_params={
                "usernameForm": self._username,
                "passwordForm": self._password,
                "fingerprint": self._fingerprint,
                "sun": "yes",
            },
            force_login=False,
        )

        if not handle_response(
            response, logging.ERROR, "Could not log into ADT Pulse site"
        ):
            self._authenticated = False
            return

        if response is None:
            return

        soup = BeautifulSoup(response.text, "html.parser")
        error = soup.find("div", {"id": "warnMsgContents"})
        if error or not response.ok:
            LOG.error(
                f"ADT Pulse response ({response.status_code}): "
                "{error} {response.status_code}"
            )
            self._authenticated = False
            return

        self._authenticated = True
        self._authenticated_timestamp = time.time()

        # since we received fresh data on the status of the alarm, go ahead
        # and update the sites with the alarm status.
        self._update_sites(response.text)

    def logout(self) -> None:
        LOG.info(f"Logging {self._username} out of ADT Pulse")
        self.query(ADT_LOGOUT_URI)
        self._authenticated = False

    @property
    def updates_exist(self) -> bool:
        response = self.query(
            ADT_SYNC_CHECK_URI,
            extra_headers={"Accept": "*/*", "Referer": self.make_url(ADT_SUMMARY_URI)},
            extra_params={"ts": self._sync_timestamp},
        )

        if response is None:
            LOG.error("Error querying ADT sync")
            return False

        text = response.text
        self._sync_timestamp = time.time()

        pattern = r"\d+[-]\d+[-]\d+"
        if not re.match(pattern, text):
            LOG.warn(f"Unexpected sync check format ({pattern}), forcing re-auth")
            self._authenticated = False
            return True

        # TODO: do we need special handling for 1-0-0 and 2-0-0 tokens?
        if text != self._sync_token:
            LOG.debug(
                f"Sync token {text} != existing {self._sync_token}; updates may exist"
            )
            self._sync_token = text
            return True
        else:
            LOG.debug(
                f"Sync token {self._sync_token} matches, no remote updates to process"
            )
            return False

    @property
    def is_connected(self) -> bool:
        """Connection status of client with ADT Pulse cloud service."""
        # FIXME: timeout automatically based on ADT default expiry?
        # self._authenticated_timestamp
        return self._authenticated

    def query(
        self,
        uri: str,
        method: str = "GET",
        extra_params: Optional[Dict] = None,
        extra_headers: Optional[Dict] = None,
        retry: int = 3,
        force_login: Optional[bool] = True,
        version_prefix: Optional[bool] = True,
    ) -> Optional[Response]:
        """
        Returns a JSON object for an HTTP request.
        :param url: API URL
        :param method: GET, POST or PUT (default=GET)
        :param extra_params: Dictionary to be appended to request.body
        :param extra_headers: Dictionary to be apppended to request.headers
        :param retry: Retry attempts for the query (default=3)
        """
        response = None

        # automatically attempt to login, if not connected
        if force_login and not self.is_connected:
            self.login()

        url = self.make_url(uri)

        loop = 0
        while loop < retry:
            loop += 1
            LOG.debug(f"Attempting {method} {url} (try {loop}/{retry})")

            # FIXME: reauthenticate if received:
            # "You have not yet signed in or you
            #  have been signed out due to inactivity."

            # update default headers and body/json values
            params = {}
            if extra_params:
                params.update(extra_params)

            # define connection method
            try:
                if method == "GET":
                    response = self._session.get(url, headers=extra_headers)
                elif method == "POST":
                    response = self._session.post(
                        url, headers=extra_headers, data=params
                    )
                else:
                    LOG.error("Invalid request method '%s'", method)
                    return None
                response.raise_for_status()

                # success!
                return response

            except HTTPError as err:
                code = err.response.status_code
                if code in [429, 500, 502, 503, 504]:
                    continue
                else:
                    LOG.error(
                        "Unrecoverable HTTP error code {code} in request to ADT Pulse: "
                    )
                    break

        return None

    def update(self) -> None:
        """Refresh any cached state."""
        LOG.debug("Checking ADT Pulse cloud service for updates")
        response = self.query(ADT_SUMMARY_URI, method="GET")
        if response is None:
            LOG.info("Error returned from ADT Pulse service check")
            return

        if response.ok:
            self._update_sites(response.text)
        else:
            LOG.info(
                f"Error returned from ADT Pulse service check: {response.status_code}"
            )

    @property
    def sites(self) -> List[ADTPulseSite]:
        """Return all sites for this ADT Pulse account"""
        return self._sites
