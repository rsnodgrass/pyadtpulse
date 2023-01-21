"""Base Python Class for pyadtpulse."""

import logging
import re
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from bs4 import BeautifulSoup
from requests import HTTPError, Response, Session, RequestException
from requests.adapters import HTTPAdapter
from urllib3 import Retry

from pyadtpulse.const import (
    ADT_DEFAULT_HTTP_HEADERS,
    ADT_DEFAULT_VERSION,
    ADT_DEVICE_URI,
    ADT_LOGIN_URI,
    ADT_LOGOUT_URI,
    ADT_SYSTEM_URI,
    ADT_SYNC_CHECK_URI,
    API_PREFIX,
    DEFAULT_API_HOST,
    ADT_TIMEOUT_URI,
    ADT_TIMEOUT_INTERVAL,
    ADT_HTTP_REFERER_URIS,
    ADT_ORB_URI,
)
from pyadtpulse.util import handle_response, make_soup

# FIXME -- circular reference
# from pyadtpulse.site import ADTPulseSite

if TYPE_CHECKING:
    from pyadtpulse.site import ADTPulseSite

LOG = logging.getLogger(__name__)

RECOVERABLE_ERRORS = [429, 500, 502, 503, 504]


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
        self._init_login_info(username, password, fingerprint)
        self._init_session()
        self._user_agent = user_agent
        self._api_version: Optional[str] = None

        self._last_timeout_reset = time.time()
        self._sync_timestamp = 0.0
        # fixme circular import, should be an ADTPulseSite
        if TYPE_CHECKING:
            self._sites: List[ADTPulseSite]
        else:
            self._sites: List[Any] = []

        self._api_host = DEFAULT_API_HOST

        # authenticate the user
        self._authenticated = False
        self.login()

    def _init_login_info(self, username: str, password: str, fingerprint: str) -> None:
        if username is None or username == "":
            raise ValueError("Username is madatory")
        pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
        if not re.match(pattern, username):
            raise ValueError("Username must be an email address")
        self._username = username
        if password is None or password == "":
            raise ValueError("Password is mandatory")
        self._password = password
        if fingerprint is None or fingerprint == "":
            raise ValueError("Fingerprint is required")
        self._fingerprint = fingerprint

    def _init_session(self) -> None:
        retry_strategy = Retry(
            total=3,
            status_forcelist=RECOVERABLE_ERRORS,
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
            backoff_factor=0.1,
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self._session = Session()
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)
        self._session.headers.update(ADT_DEFAULT_HTTP_HEADERS)

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

    def _update_sites(self, soup: BeautifulSoup) -> None:

        if len(self._sites) == 0:
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

    def _reset_timeout(self) -> None:
        if not self._authenticated:
            return
        LOG.debug("Resetting timeout")
        response = self.query(ADT_TIMEOUT_URI, "POST")
        if handle_response(
            response, logging.INFO, "Failed resetting ADT Pulse cloud timeout"
        ):
            self._last_timeout_reset = time.time()

    def login(self) -> None:
        """Login to ADT Pulse and generate access token."""
        self._authenticated = False
        LOG.debug(f"Authenticating to ADT Pulse cloud service as {self._username}")

        response = self.query(
            ADT_LOGIN_URI,
            method="POST",
            extra_params={
                "partner": "adt",
                "usernameForm": self._username,
                "passwordForm": self._password,
                "fingerprint": self._fingerprint,
                "sun": "yes",
            },
            force_login=False,
            timeout=10,
        )

        soup = make_soup(response, logging.ERROR, "Could not log into ADT Pulse site")
        if soup is None:
            self._authenticated = False
            return

        error = soup.find("div", {"id": "warnMsgContents"})
        if error:
            LOG.error(f"Invalid ADT Pulse response: ): {error}")
            self._authenticated = False
            return

        self._authenticated = True
        self._last_timeout_reset = time.time()

        # since we received fresh data on the status of the alarm, go ahead
        # and update the sites with the alarm status.

        self._update_sites(soup)
        self._sync_timestamp = time.time()

    def logout(self) -> None:
        """Log out of ADT Pulse."""
        LOG.info(f"Logging {self._username} out of ADT Pulse")
        self.query(ADT_LOGOUT_URI, timeout=10)
        self._last_timeout_reset = time.time()
        self._authenticated = False

    @property
    def updates_exist(self) -> bool:
        """Check if updated data exists.

        Returns:
            bool: True if updated data exists
        """
        retval = False
        while True:
            LOG.debug(f"Last timeout reset: {time.time() - self._last_timeout_reset}")
            if (time.time() - self._last_timeout_reset) > ADT_TIMEOUT_INTERVAL:
                self._reset_timeout()
            response = self.query(
                ADT_SYNC_CHECK_URI,
                extra_params={"ts": int(self._sync_timestamp * 1000)},
            )

            if not handle_response(response, logging.ERROR, "Error querying ADT sync"):
                return False

            # shut up linter
            if response is None:
                return False

            text = response.text

            pattern = r"\d+[-]\d+[-]\d+"
            if not re.match(pattern, text):
                LOG.warn(f"Unexpected sync check format ({pattern}), forcing re-auth")
                LOG.debug(f"Received {text} from ADT Pulse site")
                self._authenticated = False
                return False

            # we can have 0-0-0 followed by 1-0-0 followed by 2-0-0, etc
            # wait until these settle
            if text.endswith("-0-0"):
                LOG.debug(f"Sync token {text} indicates updates may exist, requerying")
                self._sync_timestamp = time.time()
                retval = True
                continue
            LOG.debug(f"Sync token {text} indicates no remote updates to process")
            self._sync_timestamp = time.time()
            return retval

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
        force_login: Optional[bool] = True,
        version_prefix: Optional[bool] = True,
        timeout=1,
    ) -> Optional[Response]:
        """Query ADT Pulse server.

        Args:
            uri (str): URI to query
            method (str, optional): GET, POST, or PUT. Defaults to "GET".
            extra_params (Optional[Dict], optional): extra parameters to pass.
                Defaults to None.
            extra_headers (Optional[Dict], optional): extra HTTP headers.
                Defaults to None.
            force_login (Optional[bool], optional): force login. Defaults to True.
            version_prefix (Optional[bool], optional): _description_. Defaults to True.
            timeout int: number of seconds to wait for request.  Defaults to .2

        Returns:
            Optional[Response]: a Response object if successful, None on failure
        """
        response = None

        # automatically attempt to login, if not connected
        if force_login and not self.is_connected:
            self.login()

        url = self.make_url(uri)
        if uri in ADT_HTTP_REFERER_URIS:
            new_headers = {"Accept": ADT_DEFAULT_HTTP_HEADERS["Accept"]}
        else:
            new_headers = {"Accept": "*/*"}

        LOG.debug(f"Updating HTTP headers: {new_headers}")
        self._session.headers.update(new_headers)

        LOG.debug(f"Attempting {method} {url}")

        # FIXME: reauthenticate if received:
        # "You have not yet signed in or you
        #  have been signed out due to inactivity."

        # define connection method
        try:
            if method == "GET":
                response = self._session.get(
                    url, headers=extra_headers, params=extra_params, timeout=timeout
                )
            elif method == "POST":
                response = self._session.post(
                    url, headers=extra_headers, data=extra_params, timeout=timeout
                )
            else:
                LOG.error(f"Invalid request method {method}")
                return None
            response.raise_for_status()

        except HTTPError as err:
            code = err.response.status_code
            LOG.exception(f"Received HTTP error code {code} in request to ADT Pulse")
            return None
        except RequestException:
            LOG.exception("An exception occurred in request to ADT Pulse")
            return None

        # success!
        # FIXME? login uses redirects so final url is wrong
        if uri in ADT_HTTP_REFERER_URIS:
            if uri == ADT_DEVICE_URI:
                referer = self.make_url(ADT_SYSTEM_URI)
            else:
                referer = response.url
                LOG.debug(f"Setting Referer to: {referer}")
            self._session.headers.update({"Referer": referer})

        return response

    # FIXME? might have to move this to site for multiple sites
    def _query_orb(self, level: int, error_message: str) -> Optional[BeautifulSoup]:
        response = self.query(ADT_ORB_URI)

        return make_soup(response, level, error_message)

    def update(self) -> bool:
        """Update ADT Pulse data.

        Returns:
            bool: True on success
        """
        """Refresh any cached state."""
        LOG.debug("Checking ADT Pulse cloud service for updates")
        if (time.time() - self._last_timeout_reset) > ADT_TIMEOUT_INTERVAL:
            self._reset_timeout()

        # FIXME will have to query other URIs for camera/zwave/etc
        soup = self._query_orb(
            logging.INFO, "Error returned from ADT Pulse service check"
        )
        if soup is not None:
            self._update_sites(soup)
            return True

        return False

    # FIXME circular reference, should be ADTPulseSite

    @property
    def sites(self) -> List[Any]:
        """Return all sites for this ADT Pulse account."""
        return self._sites
