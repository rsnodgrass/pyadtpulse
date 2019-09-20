API_HOST   = 'https://portal.adtpulse.com'
API_PREFIX = '/myhome/'

ADT_LOGIN_URI      = '/access/signin.jsp?partner=adt'
#ADT_LOGIN_URI      = '/access/signin.jsp?e=n'
ADT_LOGOUT_URI     = '/access/signout.jsp'

ADT_SUMMARY_URI    = '/summary/summary.jsp'
ADT_ZONES_URI      = '/ajax/homeViewDevAjax.jsp' # json
ADT_STATES_URI     = '/ajax/currentStates.jsp'
ADT_SYNC_URI       = '/Ajax/SyncCheckServ'       # example: 31224-0-0

ADT_ARM_URI        = '/quickcontrol/serv/RunRRACommand'
ADT_ARM_DISARM_URI = '/quickcontrol/armDisarm.jsp?href=rest/adt/ui/client/security/setArmState'

ADT_STATUS_CHANGE_URI = '/quickcontrol/serv/ChangeVariableServ'

ADT_SET_PREMISE_URI = '/site/site?action=changepremise&siteId=[NETWORKID]'

ADT_SYSTEM_SETTINGS = '/system/settings.jsp'

ADT_CLOSED    = 'Closed'
ADT_OPEN      = 'Open'
ADT_NO_MOTION = 'No Motion'
ADT_MOTION    = 'Motion'

# "doorWindow": "door",
#    "motion": "motion",
#    "smoke": "smoke"
