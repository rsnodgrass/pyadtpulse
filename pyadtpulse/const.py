"""Constants for pyadtpulse."""

__version__ = "1.2.0"

DEFAULT_API_HOST = "https://portal.adtpulse.com"
API_HOST_CA = "https://portal-ca.adtpulse.com"  # Canada

API_PREFIX = "/myhome/"

ADT_LOGIN_URI = "/access/signin.jsp"
ADT_LOGOUT_URI = "/access/signout.jsp"
ADT_MFA_FAIL_URI = "/mfa/mfaSignIn.jsp?workflow=challenge"

ADT_SUMMARY_URI = "/summary/summary.jsp"
ADT_ZONES_URI = "/ajax/homeViewDevAjax.jsp"
ADT_ORB_URI = "/ajax/orb.jsp"
ADT_SYSTEM_URI = "/system/system.jsp"
ADT_DEVICE_URI = "/system/device.jsp"
ADT_STATES_URI = "/ajax/currentStates.jsp"
ADT_GATEWAY_URI = "/system/gateway.jsp"
ADT_SYNC_CHECK_URI = "/Ajax/SyncCheckServ"
ADT_TIMEOUT_URI = "/KeepAlive"
# Intervals are all in minutes
ADT_DEFAULT_KEEPALIVE_INTERVAL: int = 5
ADT_DEFAULT_RELOGIN_INTERVAL: int = 120
ADT_MAX_KEEPALIVE_INTERVAL: int = 15
ADT_MIN_RELOGIN_INTERVAL: int = 20
ADT_GATEWAY_STRING = "gateway"

# ADT sets their keepalive to 1 second, so poll a little more often
# than that
ADT_DEFAULT_POLL_INTERVAL = 2.0
ADT_GATEWAY_MAX_OFFLINE_POLL_INTERVAL = 600.0
ADT_MAX_BACKOFF: float = 15.0 * 60.0
ADT_DEFAULT_HTTP_USER_AGENT = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/100.0.4896.127 Safari/537.36 Edg/100.0.1185.44"
    )
}

ADT_DEFAULT_HTTP_ACCEPT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
}
ADT_DEFAULT_SEC_FETCH_HEADERS = {
    "Sec-Fetch-User": "?1",
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "navigate",
    "Upgrade-Insecure-Requests": "1",
}
ADT_OTHER_HTTP_ACCEPT_HEADERS = {
    "Accept": "*/*",
}
ADT_ARM_URI = "/quickcontrol/serv/RunRRACommand"
ADT_ARM_DISARM_URI = "/quickcontrol/armDisarm.jsp"

ADT_SYSTEM_SETTINGS = "/system/settings.jsp"

ADT_HTTP_BACKGROUND_URIS = (ADT_ORB_URI, ADT_SYNC_CHECK_URI)
STATE_OK = "OK"
STATE_OPEN = "Open"
STATE_MOTION = "Motion"
STATE_TAMPER = "Tamper"
STATE_ALARM = "Alarm"
STATE_UNKNOWN = "Unknown"
STATE_ONLINE = "Online"

ADT_SENSOR_DOOR = "doorWindow"
ADT_SENSOR_WINDOW = "glass"
ADT_SENSOR_MOTION = "motion"
ADT_SENSOR_SMOKE = "smoke"
ADT_SENSOR_CO = "co"
ADT_SENSOR_ALARM = "alarm"

ADT_DEFAULT_LOGIN_TIMEOUT = 30
