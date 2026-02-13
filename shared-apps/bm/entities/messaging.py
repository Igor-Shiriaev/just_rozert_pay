import datetime as dt
import typing
from datetime import (
    date,
    datetime,
)
from decimal import Decimal
from enum import auto
from functools import cached_property
from typing import Optional
from uuid import UUID

import pydantic
from bm.common.entities import StrEnum
from bm.constants import (
    UserLevel,
    ProductGroup,
)
from pydantic import BaseModel


class ChannelType(StrEnum):
    PULL = auto()  # Notifications in user client by HTTP API
    PULL_TECHNICAL = auto()  # Technical notifications in user client by HTTP API

    FCM = auto()  # Firebase Cloud Messaging - https://firebase.google.com/docs//cloud-messaging
    SMS = auto()
    EMAIL = auto()

    WHATSAPP = auto()


class GatewayType(StrEnum):
    PULL = auto()  # User pull notifications
    PULL_TECHNICAL = auto()  # Technical pull notifications
    FCM = auto()

    # Email gateways
    SENDGRID = auto()
    MAILGUN = auto()

    # SMS gateways
    SMSC = auto()
    TWILIO = auto()
    SMSAPI = auto()
    SMSGLOBAL = auto()
    MESSAGEBIRD = auto()
    SIGMASMS = auto()
    MITTO = auto()
    MITTO_OTP = auto()
    FAKE = auto()
    FORTYTWO = auto()
    FORTYTWO_OTP = auto()
    FORTYTWO_MX = auto()
    FORTYTWO_MX_OTP = auto()
    CONCEPTO_MOVIL = auto()
    CONCEPTO_MOVIL_OTP = auto()
    INFOBIP_MX = auto()
    INFOBIP_MX_OTP = auto()
    LAAFFIC = auto()

    # WhatsApp gateway
    WHATSAPP = auto()


class MessagePriority(StrEnum):
    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()


class EmergencyCancelCampaignRequest(BaseModel):
    campaign_id: int


class MessageDeliveryStatus(StrEnum):
    NOT_TOUCHED = auto()
    QUEUED = auto()
    TAKEN_FROM_QUEUE = auto()
    SENT_TO_PROVIDER = auto()
    DELIVERED = auto()
    OPENED = auto()
    FAILED = auto()
    DRY_RUN = auto()
    CONTROL_GROUP = auto()

    # Marketing campaign related statuses
    WAITING_EXECUTION = auto()


SUCCESS_FINAL_MESSAGE_DELIVERY_STATUSES = [
    MessageDeliveryStatus.SENT_TO_PROVIDER,
    MessageDeliveryStatus.DELIVERED,
    MessageDeliveryStatus.OPENED,
]



FINAL_MESSAGE_DELIVERY_STATUSES = [
    *SUCCESS_FINAL_MESSAGE_DELIVERY_STATUSES,
    MessageDeliveryStatus.FAILED,
]


class GetMessagesInfoRequest(BaseModel):
    external_identities: typing.List[str]

    @pydantic.validator('external_identities')
    def check_external_identities(cls, value):  # type: ignore
        assert len(value) <= 1000, f'too many items in array'
        assert value, f'must not be empty list'
        return value


class GetMessagesInfoResponse(BaseModel):
    id: str
    identity_foreign: str
    status: MessageDeliveryStatus
    gateway: typing.Optional[str]

    execution_started_at: typing.Optional[str] = None
    failure_reason: typing.Optional[str] = None
    gateway_message: typing.Optional[str] = None
    error_info: typing.Optional[str] = None

    class Config:
        orm_mode = True


class UserContactType(StrEnum):
    EMAIL = 'email'
    PHONE = 'phone'
    WHATSAPP = 'whatsapp'
    ACCOUNT_ID = 'account_id'


class UserContactData(BaseModel):
    type: typing.Literal['email', 'phone', 'account_id', 'estonian_id']
    contact: str


class UserMessagingExtraData(BaseModel):
    id: int
    uuid: UUID
    is_bonus_restriction_applied: bool
    is_spelpaus_restriction_applied: bool
    has_active_timeout_by_product: bool
    is_participant_of_restricted_cluster: bool = False  # TODO: remove this field after release.


class RewardCreateRequest(BaseModel):
    rewards_type: str
    rewards_expire_in_days: int
    rewards_config: dict
    user_id: int


class CashflowAndNGRData(BaseModel):
    user_id: int
    currency: str
    deposit_amount_sum: Decimal
    withdrawal_amount_sum: Decimal
    ngr_amount_sum: Decimal


class GetSmsGatewayForPhoneRequest(BaseModel):
    phone_number: str
    user_uuid: UUID


class GetSmsGatewayForPhoneResponse(BaseModel):
    custom_gateway: typing.Optional[GatewayType]
    gateway_by_rules: typing.Optional[GatewayType]


class DeleteSmsGatewayForPhoneRequest(BaseModel):
    phone_number: str


class PostSmsGatewayForPhoneRequest(BaseModel):
    phone_number: str
    custom_gateway: GatewayType


class GetCampaignsRequest(BaseModel):
    created_at_from: typing.Optional[datetime] = None
    exclude_bound_to_marketing_campaign: bool = False
    marketing_campaign_id: typing.Optional[int] = None
    include_tasks_count: bool = False


class MessagingCampaignResponseModel(BaseModel):
    id: int
    name: str
    status: str
    created_at: datetime
    started_at: typing.Optional[datetime] = None
    tasks_count: typing.Optional[int] = None
    email_tasks_count: typing.Optional[int] = None
    sms_tasks_count: typing.Optional[int] = None
    fcm_tasks_count: typing.Optional[int] = None


class DbAutomatedCampaignResponseModel(BaseModel):
    id: int
    name: str
    event: str
    token_selector: str
    active: bool
    start_datetime: datetime
    dry_run: bool




class GetMessagesForUserRequest(BaseModel):
    user_uuid: str
    channel_types: typing.Optional[typing.List[ChannelType]] = None


class MessageForUserModel(BaseModel):
    type: ChannelType
    subject: typing.Optional[str]
    created_at_timestamp: int
    body: str


class GetMessagesForUserResponse(BaseModel):
    items: typing.List[MessageForUserModel]


class SendgridIPPoolName(StrEnum):
    MAIN_POOL = 'main_pool'
    MT_POOL = 'mt_pool'
    BETMASTER_UK_POOL = 'betmaster_uk_pool'
    BETMASTER_IE_POOL = 'betmaster_ie_pool'
    BETMASTER_IOM_POOL = 'betmaster_iom_pool'
    CASINOIN_UK_POOL = 'casinoin_ie_pool'
    PARTNERS_MAIN_POOL = 'partners_main_pool'
    PARTNERS_MT_POOL = 'partners_mt_pool'


class SubscriptionChannel(StrEnum):
    EMAIL = 'email'
    SMS = 'sms'
    PHONE = 'phone'
    PUSH = 'push'


class SubscriptionProduct(StrEnum):
    SPORT = 'sport'
    CASINO = 'casino'
    BINGO = 'bingo'


class OptimoveTemplate(BaseModel):
    id: int
    handle: str


class OptimasterTriggeredCampaign(BaseModel):
    id: int
    title: str
    active: bool
    start_date: date


class OptimasterScheduledCampaign(BaseModel):
    id: int
    title: str
    active: bool
    start_date: date


class GetMarketingCampaignRelatedObjectsRequest(BaseModel):
    marketing_campaign_id: typing.Optional[int] = None
    created_at__gte: typing.Optional[int] = None


T = typing.TypeVar('T', bound=BaseModel)


class GetMarketingCampaignRelatedObjectsResponse(BaseModel, typing.Generic[T]):
    items: typing.List[T]


class SetMarketingCampaignIdToObjectsRequest(BaseModel):
    marketing_campaign_id: typing.Optional[int] = None
    objects_ids: typing.List[int]


class WhatsAppSendMessageRequest(BaseModel):
    user_uuid: str
    target_uuid: str


class WhatsAppUpdateMessageStatusRequest(BaseModel):
    message_foreign_id: str
    current_status: str
    webhook_data: str


class WhatsAppRebindMessagesRequest(BaseModel):
    old_user_uuid: str
    new_user_uuid: str
    target_uuid: str


class PrivateMessagingApiContact(BaseModel):
    type: Optional[UserContactType]
    contact: str
    is_active: bool
    is_confirmed: bool
    uuid: Optional[UUID]

    @classmethod
    def from_contact(cls, contact: str) -> 'PrivateMessagingApiContact':
        return cls(
            contact=contact,
            is_active=True,
            is_confirmed=True,
            type=None,
            uuid=None,
        )


class PrivateMessagingApiUserResponse(BaseModel):
    id: int
    uuid: UUID
    market: str
    license: Optional[str]  # TODO: remove optional after release
    domain_group: str
    date_joined: dt.datetime
    country: Optional[str]
    brand: str
    is_active: bool
    is_subscribed: bool
    custom_sms_gateway: typing.Optional[str]
    currency_base: str
    currency: str
    nickname: str
    language: str
    level: UserLevel
    product_group: typing.Optional[ProductGroup]
    first_name: Optional[str]
    last_name: Optional[str]
    date_of_birth: Optional[dt.date]
    last_login: Optional[datetime]
    unsubscribe_url: Optional[str]
    name: Optional[str]
    account_id: Optional[str] = None

    # Calculated fields
    is_bonus_restriction_applied: bool
    is_bonus_allowed: bool = True
    is_spelpaus_restriction_applied: bool
    has_active_timeout_by_product: bool
    is_participant_of_restricted_cluster: bool
    contacts: list[PrivateMessagingApiContact]

    # Subscription
    subscription_channels: Optional[list[SubscriptionChannel]]
    subscription_products: Optional[list[SubscriptionProduct]]

    @cached_property
    def sorted_contacts(self) -> list[PrivateMessagingApiContact]:
        def _sort_func(contact: PrivateMessagingApiContact) -> tuple[bool, bool]:
            return (contact.is_confirmed, contact.is_active)

        return sorted(
            self.contacts, key=_sort_func, reverse=True
        )

    @cached_property
    def active_contact(self) -> PrivateMessagingApiContact:
        for c in self.sorted_contacts:
            if c.is_active:
                return c
        raise RuntimeError("No active contacts!")

    @cached_property
    def login_contact(self) -> str:
        for c in self.sorted_contacts:
            if c.is_active and c.is_confirmed:
                return c.contact
        raise RuntimeError("No active and confirmed contacts!")

    @cached_property
    def login_contact_type(self) -> str:
        assert self.active_contact.type
        return self.active_contact.type

    @cached_property
    def is_confirmed(self) -> bool:
        return self.active_contact.is_confirmed

    def get_contact_by_type(self, type_: UserContactType) -> Optional[PrivateMessagingApiContact]:
        for c in self.sorted_contacts:
            if c.type == type_:
                return c
        return None

    def get_contact_by_uuid(self, uuid: UUID) -> Optional[PrivateMessagingApiContact]:
        for c in self.contacts:
            if str(c.uuid) == str(uuid):
                return c
        return None

    class Config:
        keep_untouched = (cached_property,)


class PrivateMessagingApiUserRequest(BaseModel):
    uuids: Optional[list[str]] = None
    ids: Optional[list[int]] = None
    contact_uuids: Optional[list[str]] = None
    market__in: Optional[list[str]] = None
    date_joined__gte: Optional[dt.datetime] = None
    date_joined__lte: Optional[dt.datetime] = None
    has_deposits: Optional[bool] = None

    def clean(self) -> None:
        assert (
            self.uuids
            or self.ids
            or self.contact_uuids
            or self.market__in
            or self.date_joined__gte
            or self.date_joined__lte
            or self.has_deposits is not None
        ), "All filters are empty"
