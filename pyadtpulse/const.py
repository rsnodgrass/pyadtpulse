DEFAULT_API_HOST = 'https://portal.adtpulse.com'
API_HOST_CA      = 'https://portal-ca.adtpulse.com' # Canada

API_PREFIX = '/myhome/'

ADT_LOGIN_URI      = '/access/signin.jsp?partner=adt'
ADT_LOGOUT_URI     = '/access/signout.jsp'

ADT_SUMMARY_URI    = '/summary/summary.jsp'
ADT_ZONES_URI      = '/ajax/homeViewDevAjax.jsp'
ADT_ORB_URI        = '/ajax/orb.jsp'
ADT_SYSTEM_URI     = '/system/system.jsp'
ADT_DEVICE_URI     = '/system/device.jsp?id='
ADT_STATES_URI     = '/ajax/currentStates.jsp'
ADT_SYNC_CHECK_URI = '/Ajax/SyncCheckServ'

ADT_DEFAULT_HTTP_HEADERS = { 'User-Agent' : 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36 Edg/100.0.1185.44',
                             'Accept' : 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',}
                             
ADT_ARM_URI        = '/quickcontrol/serv/RunRRACommand'
ADT_ARM_DISARM_URI = '/quickcontrol/armDisarm.jsp?href=rest/adt/ui/client/security/setArmState'

ADT_STATUS_CHANGE_URI = '/quickcontrol/serv/ChangeVariableServ'

ADT_SET_PREMISE_URI = '/site/site?action=changepremise&siteId=[NETWORKID]'

ADT_SYSTEM_SETTINGS = '/system/settings.jsp'

STATE_OK = 'OK'
STATE_OPEN = 'Open'
STATE_MOTION = 'Motion'
STATE_TAMPER = 'Tamper'
STATE_ALARM = 'Alarm'
STATE_UNKNOWN = 'Unknown'

ADT_SENSOR_DOOR = 'doorWindow'
ADT_SENSOR_WINDOW = 'glass'
ADT_SENSOR_MOTION = 'motion'
ADT_SENSOR_SMOKE = 'smoke'
ADT_SENSOR_CO = 'co'
ADT_SENSOR_ALARM = 'alarm'
