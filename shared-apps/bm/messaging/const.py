from bm.entities.messaging import GatewayType

API_PRIVATE_GET_MESSAGES_INFO_URL = '/api/messaging-api/private/get-messages-info/'
API_PRIVATE_GET_OPTIMOVE_BOUND_CAMPAIGNS_IDS = '/api/messaging-api/private/get-bound-promo-campaign-ids'
API_PRIVATE_SMS_GATEWAY_FOR_PHONE = '/api/messaging-api/private/sms-gateway-for-phone'
API_PRIVATE_GET_MESSAGING_CAMPAIGNS = '/api/messaging-api/private/messaging-campaigns'
API_PRIVATE_SET_MARKETING_CAMPAIGN_ID_TO_CAMPAIGNS = '/api/messaging-api/private/messaging-campaigns/set-marketing-campaign-id-to-campaigns'
API_PRIVATE_GET_DB_AUTOMATED_CAMPAIGNS = '/api/messaging-api/private/db-automated-campaigns'
API_PRIVATE_SET_MARKETING_CAMPAIGN_ID_TO_DB_AUTOMATED_CAMPAIGNS = '/api/messaging-api/private/db-automated-campaigns/set-marketing-campaign-id-to-campaigns'
API_PRIVATE_GET_MESSAGES_FOR_USER = '/api/messaging-api/private/messages-for-user'
API_PRIVATE_GET_OPTIMOVE_EMAIL_TEMPLATES = '/api/messaging-api/private/get-optimove-email-templates'
API_PRIVATE_GET_OPTIMOVE_SMS_TEMPLATES = '/api/messaging-api/private/get-optimove-sms-templates'
API_PRIVATE_GET_OPTIMOVE_PUSH_TEMPLATES = '/api/messaging-api/private/get-optimove-push-templates'
API_PRIVATE_SET_MARKETING_CAMPAIGN_ID_TO_OPTIMOVE_EMAIL_TEMPLATES = '/api/messaging-api/private/set-marketing-campaign-id-to-optimove-email-templates'
API_PRIVATE_SET_MARKETING_CAMPAIGN_ID_TO_OPTIMOVE_SMS_TEMPLATES = '/api/messaging-api/private/set-marketing-campaign-id-to-optimove-sms-templates'
API_PRIVATE_SET_MARKETING_CAMPAIGN_ID_TO_OPTIMOVE_PUSH_TEMPLATES = '/api/messaging-api/private/set-marketing-campaign-id-to-optimove-push-templates'
API_PRIVATE_GET_OPTIMASTER_TRIGGERED_CAMPAIGNS = '/api/messaging-api/private/get-optimaster-triggered-campaigns'
API_PRIVATE_SET_MARKETING_CAMPAIGN_ID_TO_OPTIMASTER_TRIGGERED_CAMPAIGNS = '/api/messaging-api/private/set-marketing-campaign-id-to-optimaster-triggered-campaigns'
API_PRIVATE_GET_OPTIMASTER_SCHEDULED_CAMPAIGNS = '/api/messaging-api/private/get-optimaster-scheduled-campaigns'
API_PRIVATE_SET_MARKETING_CAMPAIGN_ID_TO_OPTIMASTER_SCHEDULED_CAMPAIGNS = '/api/messaging-api/private/set-marketing-campaign-id-to-optimaster-scheduled-campaigns'
API_PRIVATE_WHATSAPP_START_REGISTRATION_FLOW = '/api/messaging-api/private/whatsapp-start-registration-flow'
API_PRIVATE_WHATSAPP_SEND_REGISTRATION_FOLLOW_UP = '/api/messaging-api/private/whatsapp-send-registration-follow-up'
API_PRIVATE_WHATSAPP_UPDATE_MESSAGE_STATUS = '/api/messaging-api/private/whatsapp-update-message-status'
API_PRIVATE_WHATSAPP_REBIND_MESSAGES_TO_REGISTERED_USER = '/api/messaging-api/private/whatsapp-rebind-messages-to-registered-user'


GATEWAY_SMSC = 'smsc'
GATEWAY_TWILIO = 'twilio'
GATEWAY_MAILGUN = 'mailgun'
GATEWAY_SENDGRID = 'sendgrid'
GATEWAY_SMSAPI = 'smsapi'
GATEWAY_SMSGLOBAL = 'smsglobal'
GATEWAY_MESSAGEBIRD = 'messagebird'
GATEWAY_SIGMASMS = 'sigmasms'
GATEWAY_MITTO = 'mitto'
GATEWAY_MITTO_OTP = 'mitto_otp'
GATEWAY_FORTYTWO = 'fortytwo'
GATEWAY_FORTYTWO_OTP = 'fortytwo_otp'
GATEWAY_CONCEPTO_MOVIL = 'concepto_movil'
GATEWAY_FAKE = 'fake'

MESSAGE_GATEWAYS = [
    GATEWAY_SMSC,
    GATEWAY_MAILGUN,
    GATEWAY_SMSAPI,
    GATEWAY_SMSGLOBAL,
    GATEWAY_MESSAGEBIRD,
    GATEWAY_SIGMASMS,
    GATEWAY_TWILIO,
    GATEWAY_MITTO,
    GATEWAY_MITTO_OTP,
    GATEWAY_FORTYTWO,
    GATEWAY_FORTYTWO_OTP,
    GATEWAY_CONCEPTO_MOVIL,
    GATEWAY_FAKE,
    GatewayType.CONCEPTO_MOVIL_OTP,
    GatewayType.INFOBIP_MX,
    GatewayType.INFOBIP_MX_OTP,
]

CHANNEL_SMS = 'sms'
CHANNEL_EMAIL = 'email'
