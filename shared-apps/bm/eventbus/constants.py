from enum import auto

from bm.common.entities import StrEnum


class EventType(StrEnum):
    DEPOSIT_INITIATED = auto()
    DEPOSIT_SUCCEEDED = auto()
    DEPOSIT_FAILED = auto()
    DEPOSIT_ROLLBACKED = auto()
    WITHDRAWAL_SUCCEEDED = auto()
    WITHDRAWAL_INITIATED = auto()
    WITHDRAWAL_FAILED = auto()
    WITHDRAWAL_ROLLBACKED = auto()
    WITHDRAWAL_CANCELLED = auto()
    MISMATCHED_CARDHOLDER_NAME = auto()
    MISMATCHED_PAYER_NAME = auto()

    PAYMENT_TRANSACTION_CHANGED = auto()
    INSUFFICIENT_FUNDS_TO_PAYOUT = auto()
    PAYMENT_TRANSACTION_AMOUNT_CHANGED = auto()
    ADMIN_WITHDRAWAL_SUCCEEDED = auto()
    CHARGEBACK_RESOLVED = auto()
    CHARGEBACK_RECEIVED = auto()

    CASINO_ACTION_CREATED = auto()
    CASINO_GAME_CHANGED = auto()
    CASINO_GAME_DEACTIVATED = auto()
    CASINO_ACTION = auto()
    CASINO_SESSION_CLOSED = auto()
    CASINO_SESSION_STARTED = auto()

    SPORTS_BET_CHANGED = auto()
    BET_RESOLVED = auto()
    GGR_CHANGED = auto()

    VIRTUAL_SPORT_ACTION_CREATED = auto()
    VIRTUAL_SPORT_BET_PLACED = auto()
    VIRTUAL_SPORT_BET_WON = auto()
    VIRTUAL_SPORT_BET_LOST = auto()
    VIRTUAL_SPORT_BET_CANCELED = auto()

    USER_REWARDED = auto()
    REWARD_EXPIRED = auto()
    USER_REWARD_REQUESTED = auto()
    USER_REWARD_EXPIRE_REQUESTED = auto()
    PROMO_WALLET_EXPIRED = auto()
    PARTICIPANT_ACCEPTED = auto()
    PARTICIPANT_STARTED = auto()

    REWIND_JACKPOT_WON = auto()

    USER_CREATED = auto()
    USER_CHANGED = auto()
    USER_PERSONAL_DATA_CHANGED = auto()

    USER_SIGNED_IN = auto()
    USER_SIGNIN_FAILED = auto()
    USER_EXCEEDED_LOGIN_ATTEMPTS = auto()
    USER_SIGNED_OUT = auto()

    USER_REGISTRATION_STATUS_CHANGED = auto()
    USER_PASSWORD_CHANGED = auto()          # changed password while being logged in
    USER_PASSWORD_RESET_INITIATED = auto()  # reset flow initiation while being logged out
    USER_PASSWORD_RESET_SUCCEEDED = auto()  # reset flow successfully finished
    USER_PASSWORD_AGE_LIMIT_EXCEEDED = auto()  # user password age limit exceeded, user must be notified

    USER_DEACTIVATED = auto()
    USER_UNBLOCKED = auto()

    USER_CONTACT_CONFIRMED = auto()

    USER_VALIDATION_MATCHING_PERSONAL_DATA_USERS_FOUND = auto()
    USER_CONTACT_DUPLICATE_FOUND = auto()

    SPORTS_MARKET_CHANGED = auto()

    RG_DEPOSIT_LIMIT_SET = auto()
    RG_DEPOSIT_LIMIT_CHANGED = auto()
    RG_DEPOSIT_LIMIT_CANCELED = auto()
    RG_DEPOSIT_LIMIT_VIOLATED = auto()
    RG_DEPOSIT_LIMIT_VIOLATION_REMOVED = auto()

    RG_LOSS_LIMIT_SET = auto()
    RG_LOSS_LIMIT_CHANGE_REQUESTED = auto()
    RG_LOSS_LIMIT_CHANGE_REQUEST_CANCELLED = auto()
    RG_LOSS_LIMIT_CHANGED = auto()
    RG_LOSS_LIMIT_CANCEL_REQUESTED = auto()
    RG_LOSS_LIMIT_CANCELED = auto()
    RG_LOSS_LIMIT_VIOLATED = auto()

    RG_ACTIVITY_LIMIT_SET = auto()
    RG_ACTIVITY_LIMIT_CHANGED = auto()
    RG_ACTIVITY_LIMIT_CANCELED = auto()

    RG_TIMEOUT_SET = auto()
    RG_TIMEOUT_CHANGED = auto()
    RG_TIMEOUT_CANCELED = auto()

    RG_WAGER_LIMIT_SET = auto()
    RG_WAGER_LIMIT_CHANGED = auto()
    RG_WAGER_LIMIT_CANCELED = auto()
    RG_WAGER_LIMIT_VIOLATED = auto()

    RG_SYSTEM_DEPOSIT_LIMIT_SET = auto()
    RG_SYSTEM_DEPOSIT_LIMIT_CANCELED = auto()

    RG_SYSTEM_NET_DEPOSIT_LIMIT_SET = auto()
    RG_SYSTEM_NET_DEPOSIT_LIMIT_CANCELED = auto()

    RM_WITHDRAWAL_LIMIT_EXCEEDED = auto()

    RM_ALL_BETTING_PRODUCTS_RESTRICTED = auto()

    CHALLENGE_DELIVERY_REQUESTED = auto()

    RACING_BET_CREATED = auto()
    RACING_BET_ACCEPTED = auto()
    RACING_BET_REJECTED = auto()
    RACING_BET_FAILED = auto()
    RACING_BET_SETTLED = auto()

    FIRST_PHONE_APP_INSTALLATION = auto()

    BATCH_COMPRESSED_EVENT = auto()     # System event for batch data transfer, i.e. sync_for_optimove

    # TODO events: delete as obsolete event types. it's still here due to backward compatilibity.
    DEPOSIT_INIT = auto()
    DEPOSIT = auto()
    DEPOSIT_FAILURE = auto()
    DEPOSIT_LIMIT_SET = auto()
    WITHDRAWAL = auto()
    SPORT_ACTION = auto()
    USER_PASSWORD_RESET = auto()
    USER_SIGNIN_CREATED = auto()
    USER_SIGNIN_UPDATED = auto()
    USER_REGISTRATION_CHANGED = auto()

    MARKET_CHANGED = auto()
    BET_RESOLVED_ACTION = auto()
    USER_UPDATED = auto()
    CURRENCY_FIXED = auto()
    USER_SIGNIN_EVENT_CREATED = auto()
    USER_SIGNIN_EVENT_UPDATED = auto()

    USER_UNSUBSCRIBED = auto()

    RM_RISK_SCORE_CHANGED = auto()  # AML risk score changed
    RM_RG_RISK_SCORE_CHANGED = auto()
    RM_POLICY_SPORTS_GGR_CHANGED = auto()
    RM_POLICY_RACING_GGR_CHANGED = auto()
    RM_POLICY_REWIND_CHANGED = auto()
    RM_POLICY_DUPLICATES_CLUSTER_CHANGED = auto()
    RM_POLICY_DUPLICATE_WALLETS_CHANGED = auto()
    RM_TAGS_CHANGED = auto()
    RM_USER_APPEALED_CONTINUOUS_FLOW_RESTRICTION = auto()
    RM_CARD_USED_BY_ANOTHER_USER = auto()

    PROMO_POINTS_ADDED = auto()

    VERIFICATION_FLOW_REQUESTED = auto()

    SUMSUB_STATUS_CHANGED = auto()
    SUMSUB_FLOW_INITIATED = auto()
    SUMSUB_FLOW_DUE_DATE_ARRIVED = auto()
    SUMSUB_FLOW_INITIATOR_CHANGED = auto()
    SUMSUB_VERIFICATION_STARTED = auto()

    USER_VERIFICATION_INITIATED = auto()
    USER_VERIFICATION_STATUS_CHANGED = auto()
    USER_VERIFICATION_EXPIRED = auto()

    BIG_WIN_RECEIVED = auto()

    CURRENCY_RATES_UPDATED = auto()

    AB_FLAG_CHANGED = auto()
    AB_FLAG_ASSIGNED = auto()

    CASHBACK_GIVEN = auto()
    WEEKLY_CASHBACK_ACCEPTED = auto()
    FREESPINS_GIVEN = auto()
    TUESDAY_BONUSES_GIVEN = auto()
    PROMO_WELCOME_STARTED = auto()
    PROMO_WELCOME_COMPLETED = auto()
    PROMO_CANCELED_BY_USER = auto()
    USER_WELCOME_PROMOTION_REVOKED = auto()

    VERIFICATION_REQUESTED = auto()
    # User requested a limit increase by completing Source of Wealth verification.
    DEPOSIT_LIMIT_INCREASE_REQUESTED = auto()

    ROFUS_CHECK_COMPLETED = auto()

    GAMSTOP_EXCLUSION_STATUS_CHANGED = auto()

    GBG_VERIFICATION_FAILED = auto()

    HAMPI_CHECK_FAILED = auto()
    HAMPI_STATUS_CHANGED = auto()

    SIGNUP_DUPLICATION_HASHES_UPDATED = auto()

    USER_READ_COMPLIANCE_MESSAGE = auto()
    COMPLIANCE_MESSAGE_TRIGGERED = auto()
    DEPOSIT_COOLOFF_EXPIRED = auto()
    LOSS_COMPLAINT_SUBMITTED = auto()
    COMPLIANCE_MESSAGE_SLACK_ALERT_TRIGGERED = auto()


OBSOLETE_EVENT_TYPES = [
    EventType.DEPOSIT_INIT,
    EventType.DEPOSIT,
    EventType.DEPOSIT_FAILURE,
    EventType.DEPOSIT_LIMIT_SET,
    EventType.WITHDRAWAL,
    EventType.CASINO_ACTION,
    EventType.SPORT_ACTION,
    EventType.USER_PASSWORD_RESET,
    EventType.USER_SIGNIN_CREATED,
    EventType.USER_SIGNIN_UPDATED,
    EventType.USER_REGISTRATION_CHANGED,
    EventType.MARKET_CHANGED,
    EventType.BET_RESOLVED_ACTION,
    EventType.USER_UPDATED,
    EventType.CURRENCY_FIXED,
    EventType.USER_SIGNIN_EVENT_CREATED,
    EventType.USER_SIGNIN_EVENT_UPDATED,
    EventType.GGR_CHANGED,
    EventType.BATCH_COMPRESSED_EVENT,
]

CLICKHOUSE_EXCLUDED_EVENT_TYPES = [
    EventType.BATCH_COMPRESSED_EVENT,
]


class SubscriptionChannel(StrEnum):
    EMAIL = 'email'
    SMS = 'sms'


class PersonalDataChangeType(StrEnum):
    first_name = 'first_name'
    last_name = 'last_name'
    birth_date = 'birth_date'

class SlackAlertStatus(StrEnum):
    SENT = 'sent'
    FAILED = 'failed'
