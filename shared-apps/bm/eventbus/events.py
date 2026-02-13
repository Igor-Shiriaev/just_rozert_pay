"""In this module SomethingChangedEvent means that something could have
been created as well as updated.
"""
import base64
import codecs
import json
import logging
import re
import uuid
from abc import ABC
from datetime import datetime
from decimal import Decimal
from enum import auto
from typing import Any, ClassVar, Dict, List, Optional, Type, TypeVar, Union, cast
from uuid import UUID, uuid4

from bm.casino.constants import CasinoProviderType
from bm.challenges.const import ChallengeAction, ChallengeType
from bm.common.entities import StrEnum
from bm.compliance_message.consts import ComplianceMessageGroup, ComplianceMessageStep
from bm.constants import (
    ActionCreator,
    ActionSource,
    CasinoActionStatus,
    CasinoActionType,
    ChargeMethod,
    ContactType,
    InstanceId,
    Period,
    ProductGroup,
    RacingProviderType,
    SportActionState,
    UserLevel,
    VirtualSportBetStatus,
    VirtualSportProviderType,
)
from bm.datatypes import Money
from bm.eventbus.constants import EventType, PersonalDataChangeType, SubscriptionChannel, SlackAlertStatus
from bm.gbg.consts import GBGVerificationType
from bm.promotion.constants import RewardType, TargetAudienceType
from bm.promotion.entities import STAGE_REWARD_PARAMS_BY_TYPE, RewardParams
from bm.sumsub.consts import LevelStatus, SumSubFlowName, SumSubFlowInitiator, VerificationRequestReason
from bm.utils import JSONEncoder, instance_as_data
from django.utils import timezone
from pydantic import BaseModel, Field, root_validator, validator

from bm.verification.consts import UserVerificationStatus, VerificationInitiator, VerificationType

from ..django_utils.field_value_path import FieldValuePath
from ..fallback_pydantic import FallbackCompatibleModel, FallbackField


logger = logging.getLogger(__name__)

T = TypeVar('T', bound=Type['EventPayload'])


class EventPriority(StrEnum):
    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()


class EventPublisher(StrEnum):
    """Service name that generates events."""

    CORE = auto()       # betmaster service, the most active publisher
    PROMOTION = auto()
    MESSAGING = auto()





class EventPayload(ABC, FallbackCompatibleModel, BaseModel):
    # list of strings with field paths that should be hidden in repr. For example:
    # ['user_id', 'user.email', 'user.phone'].
    _private_field_paths: ClassVar[List[str]] = []

    def get_repr_with_masked_private_data(self) -> Dict:
        data = self.dict()
        for field in self._private_field_paths:
            field_value_path = FieldValuePath.from_field_path(field)
            field_value = field_value_path.get_value(data)
            if field_value:
                field_value_path.set_value(data, '*' * len(field_value))
        return data



class UserEventPayload(EventPayload):
    user_id: UUID
    # NOTE: For now it always should be user base currency. later it will be refactored,
    # and, probably, moved down in event payloads hierarchy, since it's required only in
    # several event types, and in most cases it's not needed at all (plus event currency
    # could always be taken from amount.currency, see `is_allowed_event` in promotion/promotion/eventbus.py).
    # Plus this name is incorrect, correct one should be either 'user_currency_base' or
    # 'user_currency_current'.
    user_currency: str = ''
    is_loadtest: bool = False

    @property
    def operation_currency(self) -> str:
        # NOTE: for promo service it's important to know the operation currency to filter
        # and routing events. It must be filled in from any of the amount-related field to
        # represent in which currency the operation was performed.
        return self.user_currency


class UserEventPayloadWithObjectID(UserEventPayload):
    user_object_id: int


class NotificationUserEventPayload(UserEventPayload):
    """
    WARNING:
        NotificationEventPayload определяет классы которые используются
        в триггерных нотификациях. Не нужно его использовать как базовый просто потому что,
        если не планируется что на данное конкретное событие будет навешиваться некоторое сообщение.

    NOTE: external_identity
        Сквозной идентификатор - должен быть уникальным для разных нотификаций отправляемых пользователю.
        Нужен чтобы не допустить задублирования отправки одного события. Пример идентификаторов:
         * Для неуспешного вывода/успешного депозита - uuid транзакции.
         * Для события регистрации - uuid пользователя например.
    """
    external_identity: str
    user_contact_uuid: Optional[UUID] = None

    @root_validator(pre=True)  # type: ignore[call-overload]
    def validate_external_identity(cls, values: dict[str, Any]) -> dict[str, Any]:
        if 'external_identity' not in values:
            values['external_identity'] = ''
            logger.warning(
                'external_identity is not filled in, falled back to empty string',
                extra={'class_name': cls.__name__},  # type: ignore
            )
        return values


class NotificationUserEventPayloadWithUserID(NotificationUserEventPayload):
    # Do not use, user_object_id for notifications could be retrieved from with `get_user_context` func.
    user_object_id: Optional[int] = None


class Service(StrEnum):
    MESSAGING = auto()
    PROMOTION = auto()
    ANALYTICS = auto()


class Event(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    event_type: EventType
    publisher: EventPublisher = EventPublisher.CORE
    priority: EventPriority = EventPriority.MEDIUM

    payload: EventPayload
    created_at: datetime = Field(default_factory=timezone.now)
    # TODO: remove it after the old promotions will not be use anymore. ch59944
    # This needs to avoid double turnover wager in the old and the new
    # promo services.
    ignore_by_promoservice: bool = False

    exclude_from_promotion_logic: bool = False

    offline_reward_short_identifier: Optional[str] = None

    # this made to fix previous implementation of serialization in messaging service (as repr)
    _bad_uuid_regexp: ClassVar = re.compile(r'UUID\(\'(?P<clean_uuid>[\w\d-]+)\'\)')
    _bad_datetime_regexp: ClassVar = re.compile(
        r'datetime\.datetime\((?P<year>\d+).*?(?P<month>\d+).*?(?P<day>\d+).*?'
        r'(?P<hour>\d+).*?(?P<minute>\d+).*?(?P<second>\d+).*?(?P<microsecond>\d+).*?'
        r'(?P<tzinfo>.*)\)'
    )
    _bad_money_regexp: ClassVar = re.compile(
        r'Money\(value=Decimal\(\'(?P<value>[\d.]+)\'\), ' r'currency=\'(?P<currency>\w+)\'\)'
    )

    @property
    def routing_key(self) -> str:
        """Key example: 'CORE.MEDIUM.DEPOSIT_INITIATED'.
        """
        return self.make_routing_key(
            publisher=self.publisher,
            priority=self.priority,
            event_type=self.event_type,
        )

    @classmethod
    def make_all_events_routing_key(cls) -> str:
        """More convinient method for '#' routing key than `make_routing_key`."""
        return cls.make_routing_key()

    @classmethod
    def make_routing_key(
        cls,
        publisher: Optional[EventPublisher] = None,
        priority: Optional[EventPriority] = None,
        event_type: Optional[EventType] = None,
    ) -> str:
        publisher_part = priority_part = event_type_part = None

        if publisher is not None:
            publisher_part = publisher.value
        if priority is not None:
            priority_part = priority.value
        if event_type is not None:
            event_type_part = event_type.value

        if publisher_part is None and priority_part is None and event_type_part is None:
            return '#'

        return f'{publisher_part or "*"}.{priority_part or "*"}.{event_type_part or "*"}'

    @property
    def pk(self) -> str:
        """For admin site support, see EventbusEventFakeModel"""
        if isinstance(self.payload, UserEventPayload):
            user_id = self.payload.user_id
        else:
            user_id = UUID('00000000-0000-0000-0000-000000000000')
        return f'{user_id}--{self.event_id}'

    @classmethod
    def parse_pk(cls, pk: str) -> tuple[UUID, UUID]:
        """For admin site support, see EventbusEventFakeModel"""
        user_id, event_id = pk.split('--')
        return UUID(user_id), UUID(event_id)

    @classmethod
    def from_raw_event(cls, raw_event: Dict) -> 'Event':
        if 'event_type' not in raw_event:
            raise ValueError('Event type is not specified')

        def fix_payload(container: Dict) -> Dict:
            for key, value in container.items():
                if isinstance(value, dict):
                    container[key] = fix_payload(value)
                elif isinstance(value, str):
                    date_match = cls._bad_datetime_regexp.match(value)
                    if date_match:
                        container[key] = datetime(
                            year=int(date_match.group('year')),
                            month=int(date_match.group('month')),
                            day=int(date_match.group('day')),
                            hour=int(date_match.group('hour')),
                            minute=int(date_match.group('minute')),
                            second=int(date_match.group('second')),
                            microsecond=int(date_match.group('microsecond')),
                        )
                    uuid_match = cls._bad_uuid_regexp.match(value)
                    if uuid_match:
                        container[key] = uuid_match.group('clean_uuid')
                    money_match = cls._bad_money_regexp.match(value)
                    if money_match:
                        container[key] = Money(
                            value=Decimal(money_match.group('value')),
                            currency=money_match.group('currency'),
                        )
            return container

        raw_event = fix_payload(raw_event)
        payload_model = EVENT_PAYLOAD_BY_EVENT_TYPE[raw_event['event_type']]
        raw_event['payload'] = payload_model.parse_obj(raw_event['payload'])
        return cls(**raw_event)


class BatchCompressedEvent(EventPayload):
    """
    Special technical event for passing huge chunks of data.
    Right now used only for analytics historical data transfers.
    """
    compressed_data: str

    @classmethod
    def from_event_list(cls, events: list[Event]) -> 'BatchCompressedEvent':
        out = json.dumps([instance_as_data(el) for el in events],
                         cls=JSONEncoder)
        compressed_bytes = codecs.encode(out.encode('utf8'), encoding='zlib')
        compressed_data = base64.b64encode(compressed_bytes).decode('utf8')
        return cls(
            compressed_data=compressed_data,
        )

    def decompress(self) -> list[Event]:
        from .serialization import make_event_from_data
        compressed_bytes = base64.b64decode(self.compressed_data.encode('utf8'))
        raw = codecs.decode(compressed_bytes, encoding='zlib')
        data = json.loads(raw)
        return [make_event_from_data(item) for item in data]


class UserEvent(Event):
    payload: UserEventPayload


class SportActionSelection(BaseModel):
    bet_uuid: UUID
    id: Optional[int] = None     # We don't have express blocks(selections) for single bets
    match_id: Optional[int]     # None in case of outright bet
    season_id: Optional[int]
    tournament_id: Optional[int] = None
    producer_id: Optional[int] = None
    sport_id: str
    sport_name: str
    start_datetime: Optional[datetime]  # None in case of outright bet
    market_id: str
    outcome_id: str
    team_home: str
    team_away: str
    specifiers: Optional[str]
    odds: Decimal
    provider: str

    @property
    def is_live(self) -> bool:
        return self.producer_id is not None and self.producer_id == 1


class SportActionExpressBlock(BaseModel):
    id: int
    state: SportActionState


class SportsBetChangedEventPayload(UserEventPayload):
    """Sports bet creation or update event payload."""

    bet_uuid: UUID
    is_demo: bool
    created_at: datetime
    charge_method: ChargeMethod
    state: SportActionState
    stake: Money
    real_money_amount: Money
    payout: Money  # calculated win amount
    total_odds: Decimal
    selections: List[SportActionSelection]
    is_first_resolve: bool = False
    is_first_bet_for_match: bool = True
    processed_at: Optional[datetime] = None
    signin_event_id: Optional[int] = None
    promo_identifier: Optional[str] = None
    express_blocks: List[SportActionExpressBlock] = cast(Any, Field)(default_factory=list)
    domain_group: Optional[str] = None
    promo_wallet_account: Optional[UUID] = None  # NOTE: it's used to track from which promo wallet the bet was made

    @property
    def operation_currency(self) -> str:
        return self.stake.currency

class CasinoGameChangedEventPayload(EventPayload):
    """Payload for CasinoGame creation/update event."""
    game_uuid: UUID
    name: str
    type: Optional[str]
    categories: list[str]
    casino_provider: str
    aggregator: str
    is_mobile_supported: bool
    is_enabled: bool
    is_mobile_only: bool
    restricted_country_codes: list[str] = Field(default_factory=list)
    # use default factory because this field was added later than others, in favour of restricted_country_codes
    launch_blacklisted_country_codes: list[str] = Field(default_factory=list)


class CasinoActionCreatedEventPayload(UserEventPayload):
    action_id: str | None = None  # NOTE: Optional because the field was added later, mongodb string _id.
    action_uuid: UUID
    player_uuid: Optional[UUID] = None  # NOTE: Optional because the field was added later
    round_id: Optional[str] = None
    is_demo: bool
    is_last_freespin: bool
    created_at: datetime
    charge_method: ChargeMethod
    action_type: CasinoActionType
    status: CasinoActionStatus
    amount: Money
    amount_foreign: Optional[Money] = None  # NOTE: Optional because the field was added later
    provider_transaction_id: Optional[str] = None
    real_money_amount: Money
    promo_wallet_account: Optional[UUID] = None  # NOTE: it's used to track from which promo wallet the bet was made
    promo_wallet_account_for_real_amount: Optional[UUID] = None  # NOTE: deprecated parameter, is not used anymore
    game_foreign_system_id: str                 # game id in foreign system
    game_uuid: Optional[UUID]                   # game uuid in betmaster
    game_type: str
    game_provider: str
    casino_provider: CasinoProviderType = None  # type: ignore
    wager_multiplier: Decimal = Decimal(1)
    promo_identifier: Optional[str] = None
    freespin_quantity: Optional[int] = None
    freespin_public_reward_id: Optional[str] = None
    domain_group: Optional[str] = None

    @property
    def operation_currency(self) -> str:
        return self.amount.currency


class CasinoSessionStartedPayload(UserEventPayload):
    session_id: int


class CasinoSessionClosedPayload(UserEventPayload):
    session_id: int


class BetResolvedEventPayload(UserEventPayload):
    """Common event for any bet (casino, sports, etc.)"""
    amount: Money
    real_money_amount: Money
    source: ActionSource
    promo_wallet_account_for_real_amount: Optional[UUID]


class CasinoGameDeactivatedEventPayload(EventPayload):
    # NOTE: This event is not sent at the moment.
    pass

class FillAmountEurFromAmountMixin(BaseModel):
    amount: Money
    amount_eur: Decimal = cast(Decimal, None)

    @root_validator     # type: ignore[call-overload]
    def fill_amount_eur(cls, values: dict[str, Any]) -> dict[str, Any]:
        from currency.const import EUR
        if values.get('amount_eur') is None:
            values['amount_eur'] = values['amount'].convert(EUR).value
        return values


class DepositSucceededEventPayload(NotificationUserEventPayload, FillAmountEurFromAmountMixin):
    is_first: bool
    payment_system: str
    transaction_uuid: UUID
    welcome_promo_code: Optional[str] = None
    deposit_promo_campaign_id: Optional[int] = None

    amount_foreign: Optional[Money] = None
    used_payment_channel: Optional[str] = None
    site_url: Optional[str] = None
    id_in_payment_system: Optional[str] = None
    wallet_uuid: Optional[UUID] = None
    external_wallet_identity: Optional[str] = None

    offline_reward_short_identifier: Optional[str] = None
    is_deposit_instruction: bool = False

    # See https://app.shortcut.com/betmaster/story/235102/new-analytics-params-for-meta-data-deposit-success-first-and-deposit-success-event
    registration_date: Optional[datetime] = None
    days_since_registration: Optional[int] = None

    @property
    def operation_currency(self) -> str:
        return self.amount.currency


class DepositRollbackedEventPayload(UserEventPayload, FillAmountEurFromAmountMixin):
    status_previous: str
    payment_system: str
    transaction_uuid: UUID
    welcome_promo_code: Optional[str] = None

    amount_foreign: Optional[Money] = None
    used_payment_channel: Optional[str] = None
    site_url: Optional[str] = None
    id_in_payment_system: Optional[str] = None
    wallet_uuid: Optional[UUID] = None
    external_wallet_identity: Optional[str] = None

    is_deposit_instruction: bool = False

    @property
    def operation_currency(self) -> str:
        return self.amount.currency


class DepositFailedEventPayload(NotificationUserEventPayloadWithUserID, FillAmountEurFromAmountMixin):
    payment_system: str
    transaction_uuid: UUID
    welcome_promo_code: Optional[str] = None

    amount_foreign: Optional[Money] = None
    used_payment_channel: Optional[str] = None
    site_url: Optional[str] = None
    id_in_payment_system: Optional[str] = None
    wallet_uuid: Optional[UUID] = None
    decline_code: Optional[str] = None
    decline_reason: Optional[str] = None
    external_wallet_identity: Optional[str] = None
    is_deposit_instruction: bool = False

    @property
    def operation_currency(self) -> str:
        return self.amount.currency


class DepositInitiadedEventPayload(NotificationUserEventPayload, FillAmountEurFromAmountMixin):
    payment_system: str
    is_first: bool = FallbackField(..., fallback_value=False)
    transaction_uuid: Optional[UUID] = None
    welcome_promo_code: Optional[str] = None

    amount_foreign: Optional[Money] = None
    used_payment_channel: Optional[str] = None
    site_url: Optional[str] = None
    id_in_payment_system: Optional[str] = None
    wallet_uuid: Optional[UUID] = None
    external_wallet_identity: Optional[str] = None
    is_deposit_instruction: bool = False
    transaction_created_at: datetime = Field(default_factory=timezone.now)  # for backward compability

    @property
    def operation_currency(self) -> str:
        return self.amount.currency


class ChargebackResolvedEventPayload(EventPayload):
    payment_system: str
    transaction_uuid: UUID
    transaction_id: int


class ChargebackReceivedEventPayload(UserEventPayload):
    payment_system: str
    transaction_uuid: UUID


class GGRChangedEventPayload(UserEventPayload):
    amount: Money
    ggr_type: ActionSource


class TransactionChangedEventPayload(NotificationUserEventPayload):
    transaction_uuid: UUID
    status: str
    amount: Decimal
    currency: str
    wallet_system: str
    user_uuid: UUID
    order_created_at: datetime
    type: str
    is_real_provider: bool
    signin_event_id: Optional[int]
    balance_after: Optional[Decimal] = None
    balance_on_hold_after: Optional[Decimal] = None
    promo_balance_after: Optional[Decimal] = None
    is_finalization: bool = False   # it's True only for new terminal statuses, e.g. success or failure.


class PaymentTransactionAmountChangedPayload(EventPayload):
    transaction_uuid: UUID
    transaction_id: int
    payment_system: str
    old_amount_face: Decimal
    old_currency: str
    new_amount_face: Decimal
    new_currency: str


class AdminWithdrawalSucceededEventPayload(UserEventPayload):
    amount: Money
    reason: str
    wallet_transaction_id: int


class WithdrawalSucceededEventPayload(NotificationUserEventPayload, FillAmountEurFromAmountMixin):
    amount: Money
    payment_system: str
    is_first: bool = False  # TODO events: delete default value
    transaction_uuid: Optional[UUID] = None

    amount_foreign: Optional[Money] = None
    used_payment_channel: Optional[str] = None
    site_url: Optional[str] = None
    id_in_payment_system: Optional[str] = None
    wallet_uuid: Optional[UUID] = None
    external_wallet_identity: Optional[str] = None

    @property
    def operation_currency(self) -> str:
        return self.amount.currency


class WithdrawalRollbackedEventPayload(UserEventPayload, FillAmountEurFromAmountMixin):
    status_previous: str
    amount: Money
    payment_system: str
    transaction_uuid: Optional[UUID] = None

    amount_foreign: Optional[Money] = None
    used_payment_channel: Optional[str] = None
    site_url: Optional[str] = None
    id_in_payment_system: Optional[str] = None
    wallet_uuid: Optional[UUID] = None
    external_wallet_identity: Optional[str] = None

    @property
    def operation_currency(self) -> str:
        return self.amount.currency


class WithdrawalInitiatedEventPayload(UserEventPayload):
    amount: Money
    payment_system: str
    is_first: bool
    transaction_uuid: UUID

    amount_foreign: Money
    wallet_uuid: UUID
    site_url: Optional[str] = None
    used_payment_channel: Optional[str] = None
    id_in_payment_system: Optional[str] = None
    external_wallet_identity: Optional[str] = None

    @property
    def operation_currency(self) -> str:
        return self.amount.currency


class WithdrawalCancelledEventPayload(UserEventPayload):
    transaction_uuid: UUID
    amount: Money


class WithdrawalFailedEventPayload(UserEventPayload):
    amount: Money
    payment_system: str
    transaction_uuid: UUID

    amount_foreign: Money
    wallet_uuid: UUID
    site_url: Optional[str] = None
    used_payment_channel: Optional[str] = None
    id_in_payment_system: Optional[str] = None
    decline_code: Optional[str] = None
    decline_reason: Optional[str] = None
    external_wallet_identity: Optional[str] = None

    @property
    def operation_currency(self) -> str:
        return self.amount.currency


class WithdrawalLimitExceededPayload(UserEventPayload):
    period: Period
    user_domain_group: str
    user_level: UserLevel


class AllBettingProductsRestrictedPayload(UserEventPayload):
    license: str
    domain_group: str
    level: UserLevel
    reason: str


class UserRewardedEventPayload(UserEventPayload):
    public_reward_id: UUID
    reward_type: RewardType
    expires_at: datetime
    params: RewardParams
    target_audience: TargetAudienceType
    campaign_internal_name: Optional[str] = None
    campaign_id: Optional[int] = None

    @validator('params', pre=True)
    def validate_params(
        cls,
        value: Union[Dict, RewardParams],
        values: Dict
    ) -> RewardParams:
        if isinstance(value, RewardParams):
            return value
        if 'reward_type' in values:
            return STAGE_REWARD_PARAMS_BY_TYPE[values['reward_type']](**value)  # type: ignore
        return value  # type: ignore


class UserCreatedEventPayload(UserEventPayload):
    user_id: UUID
    name: str
    currency: str
    language: str
    country: str
    brand: str
    date_joined: datetime
    is_subscribed: bool
    is_active: bool
    is_vip: bool
    level: Optional[UserLevel] = None
    platform: Optional[str] = None
    domain_group: str
    market: str
    is_currency_fixed: bool = True
    affiliate_id: Optional[str] = None
    utm_source: Optional[str] = None
    utm_content: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_affid: Optional[str] = None
    promotion_group_type: Optional[str] = None
    instance_id: InstanceId


class UserChangedEventPayload(UserEventPayload):
    """Payload for user update event."""
    user_uuid: Optional[UUID] = None  # TODO events: delete this field
    user_id: UUID = UUID('00000000-0000-0000-0000-000000000000')
    name: str
    currency: str
    language: str
    country: str
    brand: str
    date_joined: datetime
    is_subscribed: bool
    is_active: bool
    is_vip: bool
    level: Optional[UserLevel] = None
    platform: Optional[str] = None
    domain_group: str
    market: str
    is_currency_fixed: bool = True
    affiliate_id: Optional[str] = None
    utm_source: Optional[str] = None
    utm_content: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_affid: Optional[str] = None
    promotion_group_type: Optional[str] = None
    instance_id: Optional[InstanceId] = None  # TODO: remove default value after release.


class UserPersonalDataChangedEventPayload(UserEventPayloadWithObjectID):
    changed_types: list[PersonalDataChangeType]


class UserSigninEventCreatedEventPayload(UserEventPayload):
    id: int
    # TODO events: remove default value in user_id field (it's here for backward compatibility),
    # # delete 'user_uuid' in favor of 'user_id'.
    user_id: UUID = UUID('00000000-0000-0000-0000-000000000000')
    user_uuid: Optional[UUID] = None  # TODO events: delete this field
    created_at: datetime
    platform: Optional[str] = None
    os: Optional[str] = None
    ua: Optional[str] = None
    csrftoken: Optional[str] = None
    country: Optional[str] = None


class UserSigninEventUpdatedEventPayload(UserSigninEventCreatedEventPayload):
    is_success: bool
    is_closed: bool = False
    ip: Optional[str] = None


class EventbusRequestMetadata(BaseModel):
    platform: str
    source: str
    os: str
    ua: Optional[str]
    ip: Optional[str]
    signin_event_id: Optional[int]
    country: Optional[str] = None
    marketing: Optional[dict[str, Any]] = None
    ga_cid: Optional[str] = None
    fz_uniq: Optional[str] = None


class UserSignedInEventPayload(NotificationUserEventPayload):
    signin_event_id: int
    created_at: datetime
    csrftoken_hash: str
    request_meta: EventbusRequestMetadata
    user_license: Optional[str] = None  # for backward compatibility


class UserSignInFailedEventPayload(NotificationUserEventPayload):
    signin_event_id: int
    request_meta: EventbusRequestMetadata


class UserExceededLoginAttemptsEventPayload(NotificationUserEventPayload):
    request_meta: EventbusRequestMetadata


class UserSignedOutEventPayload(UserEventPayload):
    signin_event_id: int
    # Sometimes user is logged out without explicit log out action from users side.
    # In this case request_meta is not available
    request_meta: Optional[EventbusRequestMetadata]


class SportsMarketChangedEventPayload(EventPayload):
    market_id: str
    market_foreign_id: str
    name: str


class UserPasswordChangedEventPayload(NotificationUserEventPayload):
    signin_event_id: Optional[int]
    request_meta: EventbusRequestMetadata


class UserPasswordResetInitiatedEventPayload(NotificationUserEventPayload):
    _private_field_paths: ClassVar = ['code', ]

    reset_url: Optional[str] = None  # deprecated in favor of `code`
    code: Optional[str] = None
    request_meta: EventbusRequestMetadata


class UserPasswordResetSucceededEventPayload(NotificationUserEventPayload):
    request_meta: EventbusRequestMetadata


class UserPasswordAgeLimitExceededEventPayload(NotificationUserEventPayload):
    password_set_timestamp: int


class UserDeactivatedEventPayload(NotificationUserEventPayload):
    user_object_id: Optional[int] = None
    tag: Optional[str]
    same_login_user_ids: list[UUID]
    reason: Optional[str] = None
    user_domain_group: Optional[str] = None
    is_self_action: bool = False  # NOTE: means user does it himself


class UserUnblockedEventPayload(NotificationUserEventPayload):
    user_object_id: int
    block_period_days: int | None
    user_license: Optional[str] = None  # for backward compatibility

class UserContactConfirmedEventPayload(UserEventPayload):
    contact_uuid: UUID
    contact_type: ContactType
    is_login: bool  # whether this contact is used for login or additional contact
    # NOTE: it's true only if the first way of communication with a user (like email, phone, etc.)
    # has been confirmed. It's nullable for a backward compatibility, so None means "unknown".
    is_first_communication_channel: Optional[bool] = None


class UserContactDuplicateFoundEventPayload(UserEventPayload):
    contact_uuid: UUID
    contact_type: ContactType
    duplicate_contact_uuid: UUID
    duplicate_contact_type: ContactType


class UserMatchingPersonalDataFoundEventPayload(UserEventPayload):
    matching_by_personal_data_users_uuids: dict[str, list[uuid.UUID]]
    require_kyc: bool


class VirtualSportActionCreatedEventPayload(UserEventPayload):
    bet_id: UUID
    provider: VirtualSportProviderType
    status: VirtualSportBetStatus = VirtualSportBetStatus.OTHER
    status_raw: str
    amount: Money
    amount_foreign: Money
    created_at: datetime = Field(default_factory=timezone.now)
    raw_data: dict
    domain_group: Optional[str] = None

    @property
    def operation_currency(self) -> str:
        return self.amount.currency


class VirtualSportBetPlacedEventPayload(VirtualSportActionCreatedEventPayload):
    status: VirtualSportBetStatus = VirtualSportBetStatus.NEW


class VirtualSportBetWonEventPayload(VirtualSportActionCreatedEventPayload):
    status: VirtualSportBetStatus = VirtualSportBetStatus.WIN


class VirtualSportBetLostEventPayload(VirtualSportActionCreatedEventPayload):
    status: VirtualSportBetStatus = VirtualSportBetStatus.LOSE


class VirtualSportBetCanceledEventPayload(VirtualSportActionCreatedEventPayload):
    status: VirtualSportBetStatus = VirtualSportBetStatus.CANCELED


class RacingBetBase(UserEventPayload):
    bet_id: UUID
    created_at: datetime
    provider: RacingProviderType
    bet_type: str
    selections: list[dict]
    stake: Money
    stake_foreign: Money
    charge_method: ChargeMethod
    charges: dict[str, Decimal]
    odds: Optional[Decimal]

    domain_group: str
    signin_event_id: int

    promo_identifier: Optional[str] = None
    promo_wallet_account: Optional[UUID] = None  # NOTE: it's used to track from which promo wallet the bet was made

    @root_validator(pre=True)
    def add_external_identity(cls, values: dict[str, Any]) -> dict[str, Any]:
        if not values.get('external_identity'):
            values['external_identity'] = cls.construct_external_identity(**values)
        return values

    @staticmethod
    def construct_external_identity(**kwargs: Any) -> str:
        raise NotImplementedError()


class RacingBetCreatedEventPayload(RacingBetBase):
    @staticmethod
    def construct_external_identity(**kwargs: Any) -> str:
        return f'RacingBetCreated:{kwargs["bet_id"]}'


class RacingBetAcceptedEventPayload(RacingBetBase):
    is_first_bet_for_match: bool = True

    @staticmethod
    def construct_external_identity(**kwargs: Any) -> str:
        return f'RacingBetAccepted:{kwargs["bet_id"]}'


class RacingBetRejectedEventPayload(RacingBetBase):
    rm_code: str

    @staticmethod
    def construct_external_identity(**kwargs: Any) -> str:
        return f'RacingBetRejected:{kwargs["bet_id"]}'


class RacingBetFailedEventPayload(RacingBetBase):
    reason: str

    @staticmethod
    def construct_external_identity(**kwargs: Any) -> str:
        return f'RacingBetFailed:{kwargs["bet_id"]}'


class RacingBetSettledEventPayload(RacingBetBase):
    rolled_back_payout: Money  # empty if it's first bet settlement, previous settlement callback if it's second, third, etc. re-settlement.
    rolled_back_refund: Money
    rolled_back_push: Money

    payout: Money   # new applied payout
    refunded: Money
    pushed: Money

    is_first_resolve: bool = False
    is_first_bet_for_match: bool = True
    is_cancellation: bool = False

    @property
    def total_paid(self) -> Money:
        return self.payout + self.refunded + self.pushed

    @staticmethod
    def construct_external_identity(**kwargs: Any) -> str:
        # bet can be settled and re-settled multiple times, so use unique identity for messaging
        return str(uuid4())


class RewardExpiredEventPayload(UserEventPayload):
    """For now
    user_currency: str and is_loadtest: bool from UserEventPayload
    are not set explicitly since producer of this event does not have this
    info about user. So we rely on default values for these fields.
    It's ok since these two params are practically not used anywhere in project.
    Nevertheless, the moment UserEventPayload start asking for more user params
    this code will be refactored - this event won't be considered 'user event', so
    it will be consumed by from eventbus some service with an access to user's repo
    and will produce new event based on this one, but enriched with required user params.
    """

    public_reward_id: UUID
    # TODO events: remove default value in user_id field (it's here for backward compatibility).
    user_id: UUID = UUID('00000000-0000-0000-0000-000000000000')
    reason: str = ''
    reward_type: Optional[RewardType] = None


class PromoWalletExpiredEventPayload(UserEventPayload):
    """See comments in RewardExpiredEventPayload regarding UserEventPayload base class."""

    wallet_account: UUID
    # TODO events: remove default value in user_id field (it's here for backward compatibility).
    user_id: UUID = UUID('00000000-0000-0000-0000-000000000000')


class ParticipantChangedEventPayload(UserEventPayload):
    """See comments in RewardExpiredEventPayload regarding UserEventPayload base class."""

    user_id: UUID
    participant_id: int
    accepted: bool
    started: bool
    # NOTE: it used to use campaign_uuid which is wrong, we migrated to campaign_id,
    # it's optional for a backward compatibility.
    campaign_uuid: Optional[UUID] = None
    campaign_id: Optional[int] = None


class PromoWelcomeStartedEventPayload(UserEventPayload):
    user_id: UUID
    campaign_id: int


class PromoWelcomeCompletedEventPayload(UserEventPayload):
    user_id: UUID
    campaign_id: int
    initial_amount: Optional[Money] = None


class PromoCanceledByUserEventPayload(UserEventPayload):
    user_id: UUID
    campaign_id: int


class UserRegistrationStatusChangedEventPayload(NotificationUserEventPayload):
    _private_field_paths: ClassVar = ['code', ]

    class Status(StrEnum):
        # NOTE: Seems like STARTED is not used at all.
        STARTED = auto()                        # Registration process started (initiated)
        CONFIRMED = auto()                      # Registration confirmed
        PHONE_SIGNIN = auto()                   # Phone signin message requested
        WHATSAPP_SIGNIN = auto()                # WhatsApp signin message requested
        EMAIL_CONFIRMATION_REQUESTED = auto()
        MAGIC_LINK_SIGNIN = auto()              # Magic link signin message requested

    type: str
    status: Status
    confirm_url: Optional[str] = None  # Not used anymore, `code`` is used instead

    # NOTE: fields below was added afterward, so it's nullable for backward compatibility.
    user_domain_group: Optional[str] = None
    user_market: Optional[str] = None

    promotion_group_type: Optional[str] = None   # Promotion type
    code: Optional[str] = None

    offline_reward_short_identifier: Optional[str] = None

    host: Optional[str] = None
    platform: Optional[str] = None


# for backward compatibility
class DepositLimitSetEventPayload(UserEventPayload):
    amount: Decimal
    currency: str
    amount_sek: Decimal
    site_url: str


class RGEventPayload(UserEventPayload):
    user_object_id: Optional[int] = None
    object_id: Optional[int] = None
    made_by: ActionCreator = ActionCreator.USER

    external_identity: str = ''  # overriden in add_external_identity method

    @root_validator(pre=True)
    def add_external_identity(cls, values: dict[str, Any]) -> dict[str, Any]:
        if not values.get('external_identity'):
            values['external_identity'] = cls.construct_external_identity(**values)
        return values

    @staticmethod
    def construct_external_identity(**kwargs: Any) -> str:
        raise NotImplementedError()


class RGDepositLimitSetEventPayload(RGEventPayload):
    amount: Money
    amount_sek: Money
    # TODO remove optional after release
    period: Optional[str] = None
    site_url: Optional[str] = None

    @staticmethod
    def construct_external_identity(**kwargs: Any) -> str:
        return f'deposit-limit-set:{kwargs["object_id"]}:{str(uuid4())}'


class RGDepositLimitChangedEventPayload(RGEventPayload):
    amount: Money
    # TODO UK: delete default value after release
    # https://app.shortcut.com/betmaster/story/220590/new-uk-alerts-rm-rg-alerts-uk-step2-new-events
    amount_old: Decimal = Decimal(0)
    amount_sek: Money
    # TODO remove optional after release
    period: Optional[str] = None

    @staticmethod
    def construct_external_identity(**kwargs: Any) -> str:
        return f'deposit-limit-changed:{kwargs["object_id"]}:{str(uuid4())}'


class RGDepositLimitCanceledEventPayload(RGEventPayload):
    # TODO remove optional after release
    period: Optional[str] = None

    @staticmethod
    def construct_external_identity(**kwargs: Any) -> str:
        return f'deposit-limit-canceled:{kwargs["object_id"]}:{str(uuid4())}'


class RGDepositLimitViolatedEventPayload(RGEventPayload):
    excess_sum: Decimal
    excess_transaction_ids: list[int]
    # TODO remove optional after release
    period: Optional[str] = None

    @staticmethod
    def construct_external_identity(**kwargs: Any) -> str:
        return f'deposit-limit-violated:{kwargs["object_id"]}:{str(uuid4())}'


class RGDepositLimitViolationRemovedEventPayload(RGEventPayload):
    # TODO remove optional after release
    period: Optional[str] = None

    @staticmethod
    def construct_external_identity(**kwargs: Any) -> str:
        return f'deposit-limit-violation-removed:{kwargs["object_id"]}:{str(uuid4())}'


class RGLossLimitSetEventPayload(RGEventPayload):
    amount: Money
    ggr_at_start: Decimal
    period: str

    @staticmethod
    def construct_external_identity(**kwargs: Any) -> str:
        return f'loss-limit-set:{kwargs["object_id"]}'


class RGLossLimitChangeRequestCreatedEventPayload(RGEventPayload):
    amount: Money
    new_amount: Optional[Money]
    period: str
    made_by: ActionCreator = ActionCreator.USER

    @staticmethod
    def construct_external_identity(**kwargs: Any) -> str:
        return f'loss-limit-change-request-created:{kwargs["object_id"]}'


class RGLossLimitChangeRequestCancelledEventPayload(RGEventPayload):
    made_by: ActionCreator = ActionCreator.USER

    @staticmethod
    def construct_external_identity(**kwargs: Any) -> str:
        return f'loss-limit-change-request-cancelled:{kwargs["object_id"]}'


class RGLossLimitChangedEventPayload(RGEventPayload):
    amount: Money
    new_amount: Optional[Money]
    period: str

    @staticmethod
    def construct_external_identity(**kwargs: Any) -> str:
        return f'loss-limit-changed:{kwargs["object_id"]}'


class RGLossLimitCancelRequestedEventPayload(RGEventPayload):
    @staticmethod
    def construct_external_identity(**kwargs: Any) -> str:
        return f'loss-limit-cancel-requested:{kwargs["object_id"]}'


class RGLossLimitCanceledEventPayload(RGEventPayload):
    @staticmethod
    def construct_external_identity(**kwargs: Any) -> str:
        return f'loss-limit-canceled:{kwargs["object_id"]}'


class RGLossLimitViolatedEventPayload(RGEventPayload):
    @staticmethod
    def construct_external_identity(**kwargs: Any) -> str:
        return f'loss-limit-violated:{kwargs["object_id"]}'


class RGActivityLimitSetEventPayload(RGEventPayload):
    active_period_from: datetime
    active_period_to: datetime
    period: str
    seconds_limit: int

    @staticmethod
    def construct_external_identity(**kwargs: Any) -> str:
        return f'activity-limit-set:{kwargs["object_id"]}'


class RGActivityLimitChangedEventPayload(RGEventPayload):
    active_period_from: datetime
    active_period_to: datetime
    period: str
    seconds_limit: int

    @staticmethod
    def construct_external_identity(**kwargs: Any) -> str:
        return f'activity-limit-changed:{kwargs["object_id"]}'


class RGActivityLimitCanceledEventPayload(RGEventPayload):

    @staticmethod
    def construct_external_identity(**kwargs: Any) -> str:
        return f'activity-limit-canceled:{kwargs["object_id"]}'


class RGTimeoutSetEventPayload(RGEventPayload,
                               NotificationUserEventPayload):
    product: str
    period: str
    active_from: datetime
    active_to: datetime

    @staticmethod
    def construct_external_identity(**kwargs: Any) -> str:
        return f'timeout-set:{kwargs["object_id"]}'


class RGTimeoutChangedEventPayload(RGEventPayload):
    product: str
    period: str
    active_from: datetime
    active_to: datetime

    @staticmethod
    def construct_external_identity(**kwargs: Any) -> str:
        return f'timeout-changed:{kwargs["object_id"]}'


class RGTimeoutCanceledEventPayload(RGEventPayload):
    product: str

    @staticmethod
    def construct_external_identity(**kwargs: Any) -> str:
        return f'timeout-canceled:{kwargs["object_id"]}'


class RGWagerLimitBaseEventPayload(RGEventPayload, ABC):
    user_domain_group: str
    period: str
    active_from: datetime
    active_to: datetime
    streak_id: UUID


class RGWagerLimitSetEventPayload(RGWagerLimitBaseEventPayload):
    amount: Decimal
    currency: str

    @staticmethod
    def construct_external_identity(**kwargs: Any) -> str:
        return f'wager-limit-set:{kwargs["object_id"]}'


class RGWagerLimitChangedEventPayload(RGWagerLimitBaseEventPayload):
    amount: Decimal
    currency: str
    # TODO UK: delete default value after release
    # https://app.shortcut.com/betmaster/story/220590/new-uk-alerts-rm-rg-alerts-uk-step2-new-events
    amount_old: Decimal = Decimal(0)

    @staticmethod
    def construct_external_identity(**kwargs: Any) -> str:
        return f'wager-limit-changed:{kwargs["object_id"]}'


class RGWagerLimitCanceledEventPayload(RGWagerLimitBaseEventPayload):
    canceled_by_user: bool

    @staticmethod
    def construct_external_identity(**kwargs: Any) -> str:
        return f'wager-limit-canceled:{kwargs["object_id"]}'


class RGWagerLimitViolatedEventPayload(RGWagerLimitBaseEventPayload):

    @staticmethod
    def construct_external_identity(**kwargs: Any) -> str:
        return f'wager-limit-violated:{kwargs["object_id"]}'


class RGSystemDepositLimitSetEventPayload(RGEventPayload):
    amount: Money
    period: str

    @staticmethod
    def construct_external_identity(**kwargs: Any) -> str:
        return f'system-deposit-limit-set:{kwargs["object_id"]}'


class RGSystemDepositLimitCanceledEventPayload(RGEventPayload):

    @staticmethod
    def construct_external_identity(**kwargs: Any) -> str:
        return f'system-deposit-limit-canceled:{kwargs["object_id"]}'


class RGSystemNetDepositLimitSetEventPayload(RGEventPayload):
    amount: Money
    deposits_sum: Money
    withdraws_sum: Money
    period: str

    @staticmethod
    def construct_external_identity(**kwargs: Any) -> str:
        return f'system-net-deposit-limit-set:{kwargs["object_id"]}'


class RGSystemNetDepositLimitCanceledEventPayload(RGEventPayload):

    @staticmethod
    def construct_external_identity(**kwargs: Any) -> str:
        return f'system-net-deposit-limit-canceled:{kwargs["object_id"]}'


# TODO events: to be deleted along with CURRENCY_FIXED event
class CurrencyFixedPayload(UserEventPayload):
    pass


class UserUnsubscribedEventPayload(UserEventPayload):
    channel: SubscriptionChannel
    request_meta: Optional[EventbusRequestMetadata]


class ChallengeDeliveryRequestedEventPayload(NotificationUserEventPayload):
    _private_field_paths: ClassVar = ['question', ]

    challenge_uuid: UUID
    challenge_type: ChallengeType
    question: str
    expires_at: datetime
    action: ChallengeAction
    action_context: dict

    request_meta: EventbusRequestMetadata


class RMRiskScoreChangedPayload(UserEventPayload):
    old_risk_score_value: Optional[int]
    old_risk_score_details: Optional[dict]
    new_risk_score_value: int
    new_risk_score_details: dict
    transaction_risk_triggers: list[str]  # risk_management/const.py:RiskType enum values
    old_risk_score_level: Optional[str]
    new_risk_score_level: str
    user_object_id: Optional[int] = None
    user_domain_group: Optional[str] = None


class RMTagsChangedEventPayload(UserEventPayload):
    old_rm_tags: list[str]
    new_rm_tags: list[str]
    policy: str
    user_balance_available: Decimal
    user_balance_on_hold: Decimal
    company_profit_in_user_currency: Decimal
    deposits_sum_in_user_currency: Optional[Decimal] = None  # for backward compatibility
    user_domain_group: str
    user_object_id: int
    user_level: UserLevel


class PromoPointsAddedEventPayload(UserEventPayload):
    campaign_id: str
    campaign_handle: str
    campaign_start_datetime: datetime
    campaign_finish_datetime: datetime
    points_added: int
    related_event_id: str


class SumSubBasePayload(UserEventPayload, ABC):
    user_market: str
    user_domain_group: str
    user_license: str | None = None


class VerificationFlowRequestedPayload(SumSubBasePayload):
    request_reason: VerificationRequestReason


class SumsubStatusChangedPayload(SumSubBasePayload):
    user_full_name: str = 'deprecated'  # TODO events: remove this field after release.
    review_answer: Optional[LevelStatus]
    level_name: SumSubFlowName
    send_notification: bool = False
    verification_status: Optional[str] = None
    reject_labels: Optional[list[str]] = None
    action_uuid: Optional[UUID] = None


class GBGVerificationFailedPayload(UserEventPayload):
    market: str
    domain_group: str
    brand: str
    license: str
    verification_type: GBGVerificationType
    applied_restrictions: Optional[list[str]] = None


class SumSubFlowBasePayload(SumSubBasePayload, ABC):
    level_name: SumSubFlowName


class SumSubFlowInitiatorChangedPayload(SumSubFlowBasePayload):
    new_initiator: SumSubFlowInitiator
    old_initiator: SumSubFlowInitiator


class SumsubFlowInitiatedPayload(SumSubFlowBasePayload):
    due_date: Optional[datetime]


class BaseUserVerificationPayload(UserEventPayloadWithObjectID):
    user_domain_group: str
    user_license: str
    user_verification_id: int
    verification_transaction_public_id: UUID
    verification_type: VerificationType


class UserVerificationInitiatedPayload(BaseUserVerificationPayload):
    expires_at: datetime | None
    initiator: VerificationInitiator


class UserVerificationStatusChangedPayload(BaseUserVerificationPayload):
    new_status: UserVerificationStatus


class UserVerificationExpiredPayload(BaseUserVerificationPayload):
    expired_at: datetime
    current_status: UserVerificationStatus


class SumSubValidationDueDateArrivedPayload(SumSubFlowBasePayload):
    current_status: LevelStatus
    due_date: Optional[datetime]


class InsufficientFundsToPayoutEventPayload(UserEventPayload):
    user_object_id: int
    transaction_id: int
    transaction_uuid: UUID
    transaction_currency: str
    decline_reason: Optional[str] = None
    payment_system: str
    amount_face: Decimal
    user_domain_group: Optional[str] = None


class RMSportGGRPolicyChangedPayload(UserEventPayloadWithObjectID):
    old_winner_in_sport_ids: list[int]
    new_winner_in_sport_ids: list[int]
    current_ggr_by_sport_id: dict[int, Decimal]
    user_level: UserLevel = UserLevel.regular
    user_domain_group: Optional[str] = None


class RMRacingGGRPolicyChangedPayload(UserEventPayloadWithObjectID):
    old_winner_in_sport_ids: list[int]
    new_winner_in_sport_ids: list[int]
    current_ggr_by_sport_id: dict[int, Decimal]
    user_level: UserLevel = UserLevel.regular
    user_domain_group: Optional[str] = None


class RewindPolicyChangedPayload(UserEventPayloadWithObjectID):
    user_level: UserLevel = UserLevel.regular
    user_domain_group: Optional[str] = None
    current_turnover: Decimal
    current_abs_total_ggr: Decimal
    has_threshold_been_exceeded: bool
    user_custom_threshold: Optional[Decimal] = None
    is_admin_request: bool = False


class DuplicatesClusterPolicyChangedPayload(UserEventPayloadWithObjectID):
    user_level: UserLevel = UserLevel.regular
    user_domain_group: str
    is_admin_request: bool = False
    is_cluster_restricted: bool = False


class DuplicateWalletsPolicyChangedPayload(UserEventPayloadWithObjectID):
    user_level: UserLevel = UserLevel.regular
    user_domain_group: str
    is_admin_request: bool = False
    is_cluster_restricted: bool
    is_policy_applied: bool
    is_user_excluded_from_check: bool
    user_excluded_from_check_to: Optional[datetime]


class RMCardUsedByAnotherUserEventPayload(UserEventPayloadWithObjectID):
    same_card_wallet_ids: list[int]
    transaction_uuid: UUID


class UserAppealedContinuousFlowRestrictionPayload(UserEventPayload):
    compliance_message_id: int
    flow_name: str
    step_name: str


class BigWinEventPayload(UserEventPayload):
    amount: Decimal
    amount_eur: Optional[Decimal] = None
    currency: str
    product_type: ProductGroup
    related_object_id: Optional[str]
    user_level: UserLevel = UserLevel.regular


class MismatchedCardholderNameEventPayload(UserEventPayload):
    """
    The event is kicking off if the cardholder name is not matched with user personal data name
    """
    user_object_id: int
    payment_system: Optional[str] = None  # for reverse compability
    wallet_uuid: Optional[UUID] = None


class MismatchedPayerNameEventPayload(MismatchedCardholderNameEventPayload):
    payment_system: str
    actual_name: str
    received_name: str


class UserWelcomePromotionRevokedEventPayload(NotificationUserEventPayloadWithUserID):
    reason: str
    domain_group: str


class CurrencyRatesUpdatedEventPayload(EventPayload):
    rates: dict[str, str]


class ABFlagChangedPayload(EventPayload):
    id: int
    name: str
    features: dict
    flag_percentages: dict

    active_from: Optional[datetime] = None
    active_to: Optional[datetime] = None
    is_active: Optional[bool] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ABFlagAssignedPayload(EventPayload):
    flag_id: int
    selected_group: str
    session_key: Optional[str]
    user_id: Optional[UUID]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class BonusGivenEventPayload(NotificationUserEventPayloadWithUserID):
    domain_group: str
    brand: str
    product_group: Optional[ProductGroup]
    lang: str


class CashbackGivenEventPayload(BonusGivenEventPayload):
    level: UserLevel
    week_start_date: str
    cashback_disbursed_amount: Decimal
    cashback_currency: str


class WeeklyCashbackAccepted(UserEventPayload):
    campaign_id: int


class FreespinGivenEventPayload(BonusGivenEventPayload):
    market: str

    qualifying_casino_turnover: Decimal
    qualifying_sport_turnover: Decimal
    qualifying_turnover_currency: str | None
    week_start_date: str
    freespins_disbursed_amount: int
    freespin_currency: str


class TuesdayBonusesGivenEventPayload(BonusGivenEventPayload):
    market: str
    week_start_date: str
    is_issued_freespins: bool = False
    freespins_quantity: int = 0
    is_issued_bingo_tickets: bool = False
    bingo_tickets_quantity: int = 0
    is_issued_sport_freebet: bool = False
    sport_freebet_amount: Decimal = Decimal(0)
    sport_freebet_currency: str = ''


class VerificationRequestedPayload(NotificationUserEventPayloadWithUserID):
    user_market: str
    user_domain_group: str
    user_brand: str


class DepositLimitIncreaseRequestedPayload(NotificationUserEventPayloadWithUserID):
    pass


class ROFUSCheckCompletedPayload(UserEventPayloadWithObjectID):
    user_market: str
    user_domain_group: str
    user_brand: str
    is_restricted_temporarily: bool = False
    is_restricted_indefinitely: bool = False


class GAMSTOPExclusionStatusChangedPayload(UserEventPayloadWithObjectID):
    market: str
    domain_group: str
    brand: str
    license: str
    previous_status: Optional[str]
    new_status: str
    applied_restrictions: Optional[list[str]] = None


class HAMPICheckFailedPayload(UserEventPayloadWithObjectID):
    market: str
    domain_group: str
    brand: str
    license: str
    applied_restrictions: Optional[list[str]] = None


class HAMPICheckStatusChangedPayload(UserEventPayloadWithObjectID):
    market: str
    domain_group: str
    brand: str
    license: str
    previous_restricted_products: Optional[list[str]]
    new_restricted_products: list[str]
    applied_restrictions: Optional[list[str]] = None


class FirstPhoneAppInstallationEventPayload(UserEventPayload):
    market: Optional[str]
    domain_group: str


class RewindJackpotWonEventPayload(NotificationUserEventPayload, FillAmountEurFromAmountMixin):
    jackpot_uuid: UUID
    jackpot_name: str
    rank: int


class SignupDuplicationHashesUpdated(UserEventPayloadWithObjectID):
    updated_hashes: list[str]


class UserReadComplianceMessagePayload(UserEventPayloadWithObjectID):
    compliance_message_id: int
    read_at: datetime
    flow: ComplianceMessageGroup
    step: ComplianceMessageStep
    user_domain_group: str


class ComplianceMessageTriggeredPayload(NotificationUserEventPayload):
    flow: ComplianceMessageGroup
    step: ComplianceMessageStep
    user_domain_group: str
    message_public_id: UUID
    user_license: str | None = None  # delete None after release of https://app.shortcut.com/betmaster/story/260564/backend-uk-trigger-3-pop-up-messages-for-high-loss


class DepositCooloffExpiredPayload(UserEventPayloadWithObjectID):
    period_hours: int
    flow: ComplianceMessageGroup
    step: ComplianceMessageStep
    user_domain_group: str


class LossComplaintPayload(UserEventPayloadWithObjectID):
    sow_verification_statuses: set[LevelStatus]


class SlackAlertTriggeredPayload(UserEventPayload):
    channel: str
    alert_name: str
    status: SlackAlertStatus
    event_time: datetime = Field(default_factory=timezone.now)
    error_message: str = ''

EVENT_PAYLOAD_BY_EVENT_TYPE: Dict[EventType, Type[EventPayload]] = {
    EventType.DEPOSIT_INITIATED: DepositInitiadedEventPayload,
    EventType.DEPOSIT_SUCCEEDED: DepositSucceededEventPayload,
    EventType.DEPOSIT_FAILED: DepositFailedEventPayload,
    EventType.DEPOSIT_ROLLBACKED: DepositRollbackedEventPayload,
    EventType.WITHDRAWAL_INITIATED: WithdrawalInitiatedEventPayload,
    EventType.WITHDRAWAL_SUCCEEDED: WithdrawalSucceededEventPayload,
    EventType.WITHDRAWAL_FAILED: WithdrawalFailedEventPayload,
    EventType.WITHDRAWAL_ROLLBACKED: WithdrawalRollbackedEventPayload,
    EventType.WITHDRAWAL_CANCELLED: WithdrawalCancelledEventPayload,
    EventType.PAYMENT_TRANSACTION_CHANGED: TransactionChangedEventPayload,
    EventType.INSUFFICIENT_FUNDS_TO_PAYOUT: InsufficientFundsToPayoutEventPayload,
    EventType.PAYMENT_TRANSACTION_AMOUNT_CHANGED: PaymentTransactionAmountChangedPayload,
    EventType.ADMIN_WITHDRAWAL_SUCCEEDED: AdminWithdrawalSucceededEventPayload,
    EventType.CHARGEBACK_RESOLVED: ChargebackResolvedEventPayload,
    EventType.CHARGEBACK_RECEIVED: ChargebackReceivedEventPayload,

    EventType.CASINO_ACTION_CREATED: CasinoActionCreatedEventPayload,
    EventType.SPORTS_BET_CHANGED: SportsBetChangedEventPayload,
    EventType.BET_RESOLVED: BetResolvedEventPayload,

    EventType.VIRTUAL_SPORT_ACTION_CREATED: VirtualSportActionCreatedEventPayload,
    EventType.VIRTUAL_SPORT_BET_PLACED: VirtualSportBetPlacedEventPayload,
    EventType.VIRTUAL_SPORT_BET_WON: VirtualSportBetWonEventPayload,
    EventType.VIRTUAL_SPORT_BET_LOST: VirtualSportBetLostEventPayload,
    EventType.VIRTUAL_SPORT_BET_CANCELED: VirtualSportBetCanceledEventPayload,

    EventType.CASINO_GAME_DEACTIVATED: CasinoGameDeactivatedEventPayload,
    EventType.CASINO_GAME_CHANGED: CasinoGameChangedEventPayload,

    EventType.USER_REWARD_EXPIRE_REQUESTED: RewardExpiredEventPayload,
    EventType.USER_REWARD_REQUESTED: UserRewardedEventPayload,
    EventType.USER_REWARDED: UserRewardedEventPayload,
    EventType.REWARD_EXPIRED: RewardExpiredEventPayload,
    EventType.PROMO_WALLET_EXPIRED: PromoWalletExpiredEventPayload,
    EventType.PARTICIPANT_ACCEPTED: ParticipantChangedEventPayload,
    EventType.PARTICIPANT_STARTED: ParticipantChangedEventPayload,

    EventType.USER_CREATED: UserCreatedEventPayload,
    EventType.USER_CHANGED: UserChangedEventPayload,
    EventType.USER_PERSONAL_DATA_CHANGED: UserPersonalDataChangedEventPayload,
    EventType.USER_REGISTRATION_STATUS_CHANGED: UserRegistrationStatusChangedEventPayload,

    EventType.USER_SIGNED_IN: UserSignedInEventPayload,
    EventType.USER_SIGNED_OUT: UserSignedOutEventPayload,
    EventType.USER_SIGNIN_FAILED: UserSignInFailedEventPayload,
    EventType.USER_EXCEEDED_LOGIN_ATTEMPTS: UserExceededLoginAttemptsEventPayload,
    EventType.USER_PASSWORD_CHANGED: UserPasswordChangedEventPayload,
    EventType.USER_PASSWORD_RESET_INITIATED: UserPasswordResetInitiatedEventPayload,
    EventType.USER_PASSWORD_RESET_SUCCEEDED: UserPasswordResetSucceededEventPayload,
    EventType.USER_PASSWORD_AGE_LIMIT_EXCEEDED: UserPasswordAgeLimitExceededEventPayload,
    EventType.USER_DEACTIVATED: UserDeactivatedEventPayload,
    EventType.USER_CONTACT_CONFIRMED: UserContactConfirmedEventPayload,

    EventType.SPORTS_MARKET_CHANGED: SportsMarketChangedEventPayload,

    EventType.RG_DEPOSIT_LIMIT_SET: RGDepositLimitSetEventPayload,
    EventType.RG_DEPOSIT_LIMIT_CHANGED: RGDepositLimitChangedEventPayload,
    EventType.RG_DEPOSIT_LIMIT_CANCELED: RGDepositLimitCanceledEventPayload,
    EventType.RG_DEPOSIT_LIMIT_VIOLATED: RGDepositLimitViolatedEventPayload,
    EventType.RG_DEPOSIT_LIMIT_VIOLATION_REMOVED: RGDepositLimitViolationRemovedEventPayload,

    EventType.RG_LOSS_LIMIT_SET: RGLossLimitSetEventPayload,
    EventType.RG_LOSS_LIMIT_CHANGE_REQUESTED: RGLossLimitChangeRequestCreatedEventPayload,
    EventType.RG_LOSS_LIMIT_CHANGE_REQUEST_CANCELLED: RGLossLimitChangeRequestCancelledEventPayload,
    EventType.RG_LOSS_LIMIT_CHANGED: RGLossLimitChangedEventPayload,
    EventType.RG_LOSS_LIMIT_CANCEL_REQUESTED: RGLossLimitCancelRequestedEventPayload,
    EventType.RG_LOSS_LIMIT_CANCELED: RGLossLimitCanceledEventPayload,

    EventType.RG_ACTIVITY_LIMIT_SET: RGActivityLimitSetEventPayload,
    EventType.RG_ACTIVITY_LIMIT_CHANGED: RGActivityLimitChangedEventPayload,
    EventType.RG_ACTIVITY_LIMIT_CANCELED: RGActivityLimitCanceledEventPayload,

    EventType.RG_WAGER_LIMIT_SET: RGWagerLimitSetEventPayload,
    EventType.RG_WAGER_LIMIT_CHANGED: RGWagerLimitChangedEventPayload,
    EventType.RG_WAGER_LIMIT_CANCELED: RGWagerLimitCanceledEventPayload,
    EventType.RG_WAGER_LIMIT_VIOLATED: RGWagerLimitViolatedEventPayload,

    EventType.RG_SYSTEM_DEPOSIT_LIMIT_SET: RGSystemDepositLimitSetEventPayload,
    EventType.RG_SYSTEM_DEPOSIT_LIMIT_CANCELED: RGSystemDepositLimitCanceledEventPayload,

    EventType.RG_SYSTEM_NET_DEPOSIT_LIMIT_SET: RGSystemNetDepositLimitSetEventPayload,
    EventType.RG_SYSTEM_NET_DEPOSIT_LIMIT_CANCELED: RGSystemNetDepositLimitCanceledEventPayload,

    EventType.RG_TIMEOUT_SET: RGTimeoutSetEventPayload,
    EventType.RG_TIMEOUT_CHANGED: RGTimeoutChangedEventPayload,
    EventType.RG_TIMEOUT_CANCELED: RGTimeoutCanceledEventPayload,

    EventType.CHALLENGE_DELIVERY_REQUESTED: ChallengeDeliveryRequestedEventPayload,

    EventType.PROMO_POINTS_ADDED: PromoPointsAddedEventPayload,

    EventType.CURRENCY_RATES_UPDATED: CurrencyRatesUpdatedEventPayload,

    EventType.MISMATCHED_CARDHOLDER_NAME: MismatchedCardholderNameEventPayload,
    EventType.MISMATCHED_PAYER_NAME: MismatchedPayerNameEventPayload,

    # TODO events: delete as it's obsolete event types. it's still here due to backward compatilibity.
    EventType.DEPOSIT_INIT: DepositInitiadedEventPayload,
    EventType.DEPOSIT: DepositSucceededEventPayload,
    EventType.DEPOSIT_FAILURE: DepositFailedEventPayload,
    EventType.DEPOSIT_LIMIT_SET: DepositLimitSetEventPayload,
    EventType.WITHDRAWAL: WithdrawalSucceededEventPayload,
    EventType.CASINO_ACTION: CasinoActionCreatedEventPayload,
    EventType.SPORT_ACTION: SportsBetChangedEventPayload,
    EventType.USER_PASSWORD_RESET: UserPasswordResetInitiatedEventPayload,
    EventType.USER_SIGNIN_CREATED: UserSigninEventCreatedEventPayload,
    EventType.USER_SIGNIN_UPDATED: UserSigninEventUpdatedEventPayload,
    EventType.USER_REGISTRATION_CHANGED: UserRegistrationStatusChangedEventPayload,
    EventType.MARKET_CHANGED: SportsMarketChangedEventPayload,
    EventType.BET_RESOLVED_ACTION: BetResolvedEventPayload,
    EventType.USER_UPDATED: UserChangedEventPayload,
    EventType.CURRENCY_FIXED: CurrencyFixedPayload,
    EventType.USER_SIGNIN_EVENT_CREATED: UserSigninEventCreatedEventPayload,
    EventType.USER_SIGNIN_EVENT_UPDATED: UserSigninEventUpdatedEventPayload,
    EventType.GGR_CHANGED: GGRChangedEventPayload,
    EventType.USER_UNSUBSCRIBED: UserUnsubscribedEventPayload,

    EventType.RM_RISK_SCORE_CHANGED: RMRiskScoreChangedPayload,
    EventType.RM_RG_RISK_SCORE_CHANGED: RMRiskScoreChangedPayload,
    EventType.RM_POLICY_SPORTS_GGR_CHANGED: RMSportGGRPolicyChangedPayload,
    EventType.RM_POLICY_RACING_GGR_CHANGED: RMRacingGGRPolicyChangedPayload,
    EventType.RM_POLICY_REWIND_CHANGED: RewindPolicyChangedPayload,
    EventType.RM_TAGS_CHANGED: RMTagsChangedEventPayload,
    EventType.RM_WITHDRAWAL_LIMIT_EXCEEDED: WithdrawalLimitExceededPayload,
    EventType.RM_POLICY_DUPLICATES_CLUSTER_CHANGED: DuplicatesClusterPolicyChangedPayload,
    EventType.RM_POLICY_DUPLICATE_WALLETS_CHANGED: DuplicateWalletsPolicyChangedPayload,
    EventType.RM_USER_APPEALED_CONTINUOUS_FLOW_RESTRICTION: UserAppealedContinuousFlowRestrictionPayload,
    EventType.RM_ALL_BETTING_PRODUCTS_RESTRICTED: AllBettingProductsRestrictedPayload,
    EventType.RM_CARD_USED_BY_ANOTHER_USER: RMCardUsedByAnotherUserEventPayload,

    EventType.VERIFICATION_FLOW_REQUESTED: VerificationFlowRequestedPayload,

    EventType.SUMSUB_STATUS_CHANGED: SumsubStatusChangedPayload,
    EventType.SUMSUB_FLOW_INITIATED: SumsubFlowInitiatedPayload,
    EventType.SUMSUB_FLOW_DUE_DATE_ARRIVED: SumSubValidationDueDateArrivedPayload,

    EventType.BIG_WIN_RECEIVED: BigWinEventPayload,

    EventType.BATCH_COMPRESSED_EVENT: BatchCompressedEvent,

    EventType.AB_FLAG_CHANGED: ABFlagChangedPayload,
    EventType.AB_FLAG_ASSIGNED: ABFlagAssignedPayload,

    EventType.CASHBACK_GIVEN: CashbackGivenEventPayload,
    EventType.WEEKLY_CASHBACK_ACCEPTED: WeeklyCashbackAccepted,

    EventType.FREESPINS_GIVEN: FreespinGivenEventPayload,
    EventType.TUESDAY_BONUSES_GIVEN: TuesdayBonusesGivenEventPayload,

    EventType.USER_WELCOME_PROMOTION_REVOKED: UserWelcomePromotionRevokedEventPayload,
    EventType.PROMO_WELCOME_STARTED: PromoWelcomeStartedEventPayload,
    EventType.PROMO_WELCOME_COMPLETED: PromoWelcomeCompletedEventPayload,
    EventType.PROMO_CANCELED_BY_USER: PromoCanceledByUserEventPayload,

    EventType.USER_CONTACT_DUPLICATE_FOUND: UserContactDuplicateFoundEventPayload,
    EventType.USER_VALIDATION_MATCHING_PERSONAL_DATA_USERS_FOUND: UserMatchingPersonalDataFoundEventPayload,

    EventType.VERIFICATION_REQUESTED: VerificationRequestedPayload,
    EventType.DEPOSIT_LIMIT_INCREASE_REQUESTED: DepositLimitIncreaseRequestedPayload,

    EventType.ROFUS_CHECK_COMPLETED: ROFUSCheckCompletedPayload,

    EventType.RACING_BET_CREATED: RacingBetCreatedEventPayload,
    EventType.RACING_BET_ACCEPTED: RacingBetAcceptedEventPayload,
    EventType.RACING_BET_REJECTED: RacingBetRejectedEventPayload,
    EventType.RACING_BET_FAILED: RacingBetFailedEventPayload,
    EventType.RACING_BET_SETTLED: RacingBetSettledEventPayload,
    EventType.FIRST_PHONE_APP_INSTALLATION: FirstPhoneAppInstallationEventPayload,

    EventType.REWIND_JACKPOT_WON: RewindJackpotWonEventPayload,

    EventType.GAMSTOP_EXCLUSION_STATUS_CHANGED: GAMSTOPExclusionStatusChangedPayload,
    EventType.GBG_VERIFICATION_FAILED: GBGVerificationFailedPayload,
    EventType.HAMPI_CHECK_FAILED: HAMPICheckFailedPayload,
    EventType.HAMPI_STATUS_CHANGED: HAMPICheckStatusChangedPayload,

    EventType.CASINO_SESSION_STARTED: CasinoSessionStartedPayload,
    EventType.CASINO_SESSION_CLOSED: CasinoSessionClosedPayload,

    EventType.SIGNUP_DUPLICATION_HASHES_UPDATED: SignupDuplicationHashesUpdated,
    EventType.USER_UNBLOCKED: UserUnblockedEventPayload,

    EventType.USER_READ_COMPLIANCE_MESSAGE: UserReadComplianceMessagePayload,
    EventType.COMPLIANCE_MESSAGE_TRIGGERED: ComplianceMessageTriggeredPayload,
    EventType.DEPOSIT_COOLOFF_EXPIRED: DepositCooloffExpiredPayload,
    EventType.SUMSUB_FLOW_INITIATOR_CHANGED: SumSubFlowInitiatorChangedPayload,
    EventType.SUMSUB_VERIFICATION_STARTED: SumSubFlowBasePayload,
    EventType.LOSS_COMPLAINT_SUBMITTED: LossComplaintPayload,

    EventType.USER_VERIFICATION_INITIATED: UserVerificationInitiatedPayload,
    EventType.USER_VERIFICATION_STATUS_CHANGED: UserVerificationStatusChangedPayload,
    EventType.USER_VERIFICATION_EXPIRED: UserVerificationExpiredPayload,
    EventType.COMPLIANCE_MESSAGE_SLACK_ALERT_TRIGGERED: SlackAlertTriggeredPayload,
}


class EventGroup(StrEnum):
    GAMING = auto()
    PAYMENT = auto()
    MONEY_ACTIONS = auto()
    USER_PROFILE = auto()
    PROMOTION = auto()
    SYSTEM = auto()
    VIRTUAL_SPORT = auto()
    RESPONSIBLE_GAMBLING = auto()
    RISK_MANAGEMENT = auto()
    RACING = auto()


EVENT_TYPES_BY_GROUP: dict[EventGroup, list[EventType]] = {
    EventGroup.MONEY_ACTIONS: [
        EventType.DEPOSIT_SUCCEEDED,
        EventType.DEPOSIT_FAILED,
        EventType.DEPOSIT_ROLLBACKED,
        EventType.WITHDRAWAL_SUCCEEDED,
        EventType.WITHDRAWAL_ROLLBACKED,
        EventType.CASINO_ACTION_CREATED,
        EventType.SPORTS_BET_CHANGED,
        EventType.BET_RESOLVED,
        EventType.USER_REWARDED,
        EventType.ADMIN_WITHDRAWAL_SUCCEEDED,
    ],
    EventGroup.GAMING: [
        EventType.SPORTS_BET_CHANGED,
        EventType.CASINO_ACTION_CREATED,
        EventType.BET_RESOLVED,
        EventType.VIRTUAL_SPORT_ACTION_CREATED,
        EventType.VIRTUAL_SPORT_BET_PLACED,
        EventType.VIRTUAL_SPORT_BET_WON,
        EventType.VIRTUAL_SPORT_BET_LOST,
        EventType.VIRTUAL_SPORT_BET_CANCELED,
        EventType.RACING_BET_CREATED,
        EventType.RACING_BET_ACCEPTED,
        EventType.RACING_BET_REJECTED,
        EventType.RACING_BET_FAILED,
        EventType.RACING_BET_SETTLED,
    ],
    EventGroup.PAYMENT: [
        EventType.DEPOSIT_INITIATED,
        EventType.DEPOSIT_SUCCEEDED,
        EventType.DEPOSIT_FAILED,
        EventType.WITHDRAWAL_SUCCEEDED,
        EventType.MISMATCHED_CARDHOLDER_NAME,
        EventType.MISMATCHED_PAYER_NAME,
    ],
    EventGroup.PROMOTION: [
        EventType.USER_REWARD_EXPIRE_REQUESTED,
        EventType.USER_REWARD_REQUESTED,
        EventType.USER_REWARDED,
        EventType.REWARD_EXPIRED,
        EventType.PROMO_WALLET_EXPIRED,
        EventType.PARTICIPANT_ACCEPTED,
        EventType.PARTICIPANT_STARTED,
        EventType.REWIND_JACKPOT_WON,
        EventType.PROMO_WELCOME_STARTED,
        EventType.PROMO_WELCOME_COMPLETED,
        EventType.PROMO_CANCELED_BY_USER,
    ],
    EventGroup.USER_PROFILE: [
        EventType.USER_REGISTRATION_STATUS_CHANGED,
        EventType.USER_SIGNED_IN,
        EventType.USER_SIGNED_OUT,
        EventType.USER_SIGNIN_FAILED,
        EventType.USER_EXCEEDED_LOGIN_ATTEMPTS,
        EventType.USER_PASSWORD_CHANGED,
        EventType.USER_PASSWORD_RESET_INITIATED,
        EventType.USER_PASSWORD_RESET_SUCCEEDED,
        EventType.USER_DEACTIVATED,
        EventType.DEPOSIT_LIMIT_SET,
        EventType.CHALLENGE_DELIVERY_REQUESTED,
        EventType.SUMSUB_STATUS_CHANGED,
        EventType.SUMSUB_FLOW_INITIATED,
        EventType.SUMSUB_FLOW_DUE_DATE_ARRIVED,
        EventType.USER_CONTACT_CONFIRMED,
    ],
    EventGroup.SYSTEM: [
        # TODO events: think about separate event like "user registeted". now this event
        # spams a lot. (language update, nickname set, password update, login confirmation, etc.).
        # When separate events are created they could be placed to EventGroup.USER_PROFILE.
        EventType.USER_CHANGED,
        EventType.PAYMENT_TRANSACTION_CHANGED,
        EventType.MARKET_CHANGED,
        EventType.CASINO_GAME_CHANGED,
    ],
    EventGroup.VIRTUAL_SPORT: [
        EventType.VIRTUAL_SPORT_ACTION_CREATED,
        EventType.VIRTUAL_SPORT_BET_PLACED,
        EventType.VIRTUAL_SPORT_BET_WON,
        EventType.VIRTUAL_SPORT_BET_LOST,
        EventType.VIRTUAL_SPORT_BET_CANCELED,
    ],
    EventGroup.RESPONSIBLE_GAMBLING: [
        EventType.RG_LOSS_LIMIT_SET,
        EventType.RG_LOSS_LIMIT_CHANGE_REQUESTED,
        EventType.RG_LOSS_LIMIT_CHANGE_REQUEST_CANCELLED,
        EventType.RG_LOSS_LIMIT_CHANGED,
        EventType.RG_LOSS_LIMIT_CANCEL_REQUESTED,
        EventType.RG_LOSS_LIMIT_CANCELED,
        EventType.RG_LOSS_LIMIT_VIOLATED,
        EventType.RG_DEPOSIT_LIMIT_SET,
        EventType.RG_DEPOSIT_LIMIT_CHANGED,
        EventType.RG_DEPOSIT_LIMIT_CANCELED,
        EventType.RG_DEPOSIT_LIMIT_VIOLATED,
        EventType.RG_DEPOSIT_LIMIT_VIOLATION_REMOVED,
        EventType.RG_ACTIVITY_LIMIT_SET,
        EventType.RG_ACTIVITY_LIMIT_CHANGED,
        EventType.RG_ACTIVITY_LIMIT_CANCELED,
        EventType.RG_TIMEOUT_SET,
        EventType.RG_TIMEOUT_CHANGED,
        EventType.RG_TIMEOUT_CANCELED,
        EventType.RG_WAGER_LIMIT_SET,
        EventType.RG_WAGER_LIMIT_CHANGED,
        EventType.RG_WAGER_LIMIT_CANCELED,
        EventType.RG_WAGER_LIMIT_VIOLATED,
        EventType.RG_SYSTEM_DEPOSIT_LIMIT_SET,
        EventType.RG_SYSTEM_DEPOSIT_LIMIT_CANCELED,
        EventType.RG_SYSTEM_NET_DEPOSIT_LIMIT_SET,
        EventType.RG_SYSTEM_NET_DEPOSIT_LIMIT_CANCELED,
    ],
    EventGroup.RISK_MANAGEMENT: [
        EventType.RM_RISK_SCORE_CHANGED,
        EventType.RM_RG_RISK_SCORE_CHANGED,
        EventType.RM_WITHDRAWAL_LIMIT_EXCEEDED,
    ],
    EventGroup.RACING: [
        EventType.RACING_BET_CREATED,
        EventType.RACING_BET_ACCEPTED,
        EventType.RACING_BET_REJECTED,
        EventType.RACING_BET_FAILED,
        EventType.RACING_BET_SETTLED,
    ],

}
