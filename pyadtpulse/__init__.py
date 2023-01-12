"""Base Python Class for pyadtpulse."""

import logging
import re
import time
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup
from requests import HTTPError, Response, Session

from pyadtpulse.const import (
    ADT_DEFAULT_HTTP_HEADERS,
    ADT_DEFAULT_VERSION,
    ADT_LOGIN_URI,
    ADT_LOGOUT_URI,
    ADT_SUMMARY_URI,
    ADT_SYNC_CHECK_URI,
    API_PREFIX,
    DEFAULT_API_HOST,
)
from pyadtpulse.util import handle_response

# FIXME -- circular reference
# from pyadtpulse.site import ADTPulseSite


LOG = logging.getLogger(__name__)


class PyADTPulse:
    """Base object for ADT Pulse service."""

    def __init__(
        self,
        username: str,
        password: str,
        fingerprint: str,
        user_agent=ADT_DEFAULT_HTTP_HEADERS["User-Agent"],
    ):
        """Create a PyADTPulse object.

        Args:
            username (str): Username.
            password (str): Password.
            fingerprint (str): 2FA fingerprint.
            user_agent (str, optional): User Agent.
                         Defaults to ADT_DEFAULT_HTTP_HEADERS["User-Agent"].
        """
        if username is None or username == '':
            raise ValueError("Username is madatory")
        pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        if not re.match(pattern, username):
            raise ValueError("Username must be an email address")
        if password is None or password == '':
            raise ValueError("Password is mandatory")
        if fingerprint is None or fingerprint == '':
            raise ValueError("Fingerprint is required")
        self._session = Session()
        self._session.headers.update(ADT_DEFAULT_HTTP_HEADERS)
        self._user_agent = user_agent
        self._api_version: Optional[str] = None

        self._sync_timestamp = 0
        self._sync_token = "0-0-0"
        # fixme circular import, should be an ADTPulseSite
        self._sites: List[Any] = []

        self._api_host = DEFAULT_API_HOST

        # authenticate the user
        self._authenticated = False

        self._username = username
        self._password = password
        self._fingerprint = fingerprint

        self.login()

    def __repr__(self) -> str:
        """Object representation."""
        return "<{}: {}>".format(self.__class__.__name__, self._username)

    # ADTPulse API endpoint is configurable (besides default US ADT Pulse endpoint) to
    # support testing as well as alternative ADT Pulse endpoints such as
    # portal-ca.adtpulse.com
    def set_service_host(self, host: str) -> None:
        """Override the Pulse host (i.e. to use portal-ca.adpulse.com).

        Args:
            host (str): name of Pulse endpoint host
        """
        self._api_host = f"https://{host}"
        self._session.headers.update({"Host": host})

    def make_url(self, uri: str) -> str:
        """Create a URL to service host from a URI.

        Args:
            uri (str): the URI to convert

        Returns:
            str: the converted string
        """
        return f"{self._api_host}{API_PREFIX}{self.version}{uri}"

    @property
    def username(self) -> str:
        """Get username.

        Returns:
            str: the username
        """
        return self._username

    @property
    def version(self) -> str:
        """Get the ADT Pulse site version.

        Returns:
            str: a string containing the version
        """
        if not self._api_version:
            response = self._session.get(self._api_host)
            LOG.debug(f"Retrieved {response.url} trying to GET {self._api_host}")
            m = re.search("/myhome/(.+)/access", response.url)
            if m is not None:
                self._api_version = m.group(1)
                LOG.debug(
                    "Discovered ADT Pulse version"
                    f" {self._api_version} at {self._api_host}"
                )
                return self._api_version

            self._api_version = ADT_DEFAULT_VERSION
            LOG.warning(
                "Couldn't auto-detect ADT Pulse version, "
                f"defaulting to {self._api_version}"
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
        sites = self._sites
        # typically, ADT Pulse accounts have only a single site (premise/location)
        singlePremise = soup.find("span", {"id": "p_singlePremise"})
        if singlePremise:
            site_name = singlePremise.text

            # FIXME: this code works, but it doesn't pass the linter
            signout_link = str(
                soup.find("a", {"class": "p_signoutlink"}).get("href")  # type: ignore
            )
            if signout_link:
                m = re.search("networkid=(.+)&", signout_link)
                if m and m.group(1) and m.group(1):
                    from pyadtpulse.site import ADTPulseSite

                    site_id = m.group(1)
                    LOG.debug(f"Discovered site id {site_id}: {site_name}")
                    # FIXME ADTPulseSite circular reference
                    sites.append(ADTPulseSite(self, site_id, site_name, soup))
                    self._sites = sites
                    return
            else:
                LOG.warning(
                    f"Couldn't find site id for '{site_name}' in '{signout_link}'"
                )
        else:
            LOG.error(("ADT Pulse accounts with MULTIPLE sites not supported!!!"))

    # ...and current network id from:
    # <a id="p_signout1" class="p_signoutlink"
    # href="/myhome/16.0.0-131/access/signout.jsp?networkid=150616za043597&partner=adt"
    # onclick="return flagSignOutInProcess();">
    #
    # ... or perhaps better, just extract all from /system/settings.jsp

    def login(self) -> None:
        """Login to ADT Pulse and generate access token."""
        self._authenticated = False
        LOG.debug(f"Authenticating to ADT Pulse cloud service as {self._username}")

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

        if response is None:  # shut up linter
            return

        soup = BeautifulSoup(response.text, "html.parser")
        error = soup.find("div", {"id": "warnMsgContents"})
        if error:
            LOG.error(f"Invalid ADT Pulse response: ): {error}")
            self._authenticated = False
            return

        self._authenticated = True
        self._authenticated_timestamp = time.time()

        # since we received fresh data on the status of the alarm, go ahead
        # and update the sites with the alarm status.
        self._update_sites(response.text)

    def logout(self) -> None:
        """Log out of ADT Pulse."""
        LOG.info(f"Logging {self._username} out of ADT Pulse")
        self.query(ADT_LOGOUT_URI)
        self._authenticated = False

    @property
    def updates_exist(self) -> bool:
        """Check if updated data exists.

        Returns:
            bool: True if updated data exists
        """
        response = self.query(
            ADT_SYNC_CHECK_URI,
            extra_headers={"Accept": "*/*", "Referer": self.make_url(ADT_SUMMARY_URI)},
            extra_params={"ts": self._sync_timestamp},
        )

        if not handle_response(response, logging.ERROR, "Error querying ADT sync"):
            return False

        # shut up linter
        if response is None:
            return False

        text = response.text
        self._sync_timestamp = int(time.time())

        pattern = r"\d+[-]\d+[-]\d+"
        if not re.match(pattern, text):
            LOG.warn(f"Unexpected sync check format ({pattern}), forcing re-auth")
            LOG.debug(f"Received {text} from ADT Pulse site")
            self._authenticated = False
            return True

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
        """Check if connected to ADT Pulse.

        Returns:
            bool: True if connected
        """
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
        """Query ADT Pulse server.

        Args:
            uri (str): URI to query
            method (str, optional): GET, POST, or PUT. Defaults to "GET".
            extra_params (Optional[Dict], optional): extra parameters to pass.
                Defaults to None.
            extra_headers (Optional[Dict], optional): extra HTTP headers.
                Defaults to None.
            retry (int, optional): number of retries. Defaults to 3.
            force_login (Optional[bool], optional): force login. Defaults to True.
            version_prefix (Optional[bool], optional): _description_. Defaults to True.

        Returns:
            Optional[Response]: a Response object if successful, None on failure
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

        if not handle_response(
            response, logging.INFO, "Error returned from ADT Pulse service check"
        ):
            return

        # shut up linter
        if response is None:
            return

        self._update_sites(response.text)

# FIXME circular reference, should be ADTPulseSite

    @property
    def sites(self) -> List[Any]:
        """Return all sites for this ADT Pulse account."""
        return self._sites
