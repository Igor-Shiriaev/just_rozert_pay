BULK_CREATE_MESSAGES_REQUEST = {
    'bulk': [{
        'user_uuid': 'bf103ef6-ae04-44a2-ab11-9af1a78087a4',
        'identity_foreign': 'messaging_legacy_task:508',
        'channel': 'SMS',
        'subject': 'You have freespins',
        'body': 'Please use them',
        'dry_run': False,
        'bm_campaign_id': '522',
        'gateway': 'SMSC',
        'target': '+79999999999',
        'sender_name': 'Betmaster <mail@notify.betmaster.com>',
    }, {
        'user_uuid': 'bf103ef6-ae04-44a2-ab11-9af1a78087a4',
        'identity_foreign': 'messaging_legacy_task:509',
        'channel': 'EMAIL',
        'subject': 'You have freespins',
        'body': 'Please use them',
        'dry_run': False,
        'bm_campaign_id': '522',
        'gateway': 'MAILGUN',
        'target': 'test@test.ru',
        'sender_name': 'Betmaster <mail@notify.betmaster.com>',
    }]
}

GET_MESSAGES_INFO_REQUEST = {'external_identities': [
  'messaging_legacy_task:1',
  'messaging_legacy_task:2',
  'messaging_legacy_task:3',
  'messaging_legacy_task:4']
}

GET_MESSAGES_INFO_RESPONSE = [
    {
        'identity_foreign': 'messaging_legacy_task:1',
        'status': 'DELIVERED',
        'id': '1',
        'gateway': 'MAILGUN',
    },
    {
        'identity_foreign': 'messaging_legacy_task:2',
        'status': 'SENT_TO_PROVIDER',
        'id': '2',
        'gateway': 'MAILGUN',
    },
    {
        'identity_foreign': 'messaging_legacy_task:3',
        'status': 'FAILED',
        'error_info': 'Test error info',
        'id': '3',
        'gateway': 'MAILGUN',
    },
    {
        'identity_foreign': 'messaging_legacy_task:4',
        'status': 'NOT_TOUCHED',
        'id': '4',
        'gateway': 'MAILGUN',
    },
]

GET_MESSAGES_INFO_RESPONSE_DRY_RUN = [
    {
        'identity_foreign': 'messaging_legacy_task:1',
        'status': 'DRY_RUN',
        'id': '1',
        'error_info': 'not real error',
    },
]

EMERGENCY_CANCEL_CAMPAIGN_REQUEST = {'campaign_id': 123}
