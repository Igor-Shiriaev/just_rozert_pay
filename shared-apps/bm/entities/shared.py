import datetime
import datetime as datetime_module
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, List, NewType, Optional
from unittest.mock import Mock
from uuid import UUID

from django.shortcuts import render
from django.template import TemplateDoesNotExist
from pydantic import BaseModel, Field, root_validator, validator

from bm.casino.constants import CasinoProviderType
from bm.utils import datetime_to_millis

DjangoTemplatePath = NewType('DjangoTemplatePath', str)


class BaseConfigurationItem(BaseModel):
    key: Optional[str] = None

    def clean(self) -> None:
        "Override this method for custom configuration validation."
        pass


if TYPE_CHECKING:
    _TemplateCheckConfigurationMixin_base = BaseModel
else:
    _TemplateCheckConfigurationMixin_base = object


class TemplateCheckConfigurationMixin(_TemplateCheckConfigurationMixin_base):
    """This mixin checks presence of templates for DjangoTemplatePath type.

    MUST be used before BaseConfigurationItem in MRO.
    """

    def clean(self) -> None:
        self._validate_all_template_paths()
        super().clean()  # type: ignore

    def _validate_all_template_paths(self) -> None:
        fields = self.__fields__

        for attr, value in self.dict().items():
            if attr not in fields:
                continue

            tp = self.__annotations__.get(attr, fields[attr].type_)
            if tp is DjangoTemplatePath:
                try:
                    render(Mock(), value)
                except TemplateDoesNotExist:
                    assert False, f'template {value} does not exist!'


class EnvCasinoConfiguration(BaseConfigurationItem):
    licenses: Optional[list[str]] = None
    is_actions_archivation_enabled: bool = False
    is_actions_clickhouse_archivation_enabled: bool = False
    providers: List[str]


class EnvFeatureAvailability(BaseModel):
    coinmarketcap_rates_update: bool


class EnvMessagingConfiguration(BaseConfigurationItem):
    blacklisted_countries: list[str]


class SharedEnvConfiguration(BaseConfigurationItem):
    casino: EnvCasinoConfiguration
    messaging: EnvMessagingConfiguration
    features_availability: EnvFeatureAvailability
    admin_session_duration_minutes: int
    notify_user_on_balances_change_on_casino_action: bool


ALL_PLACEHOLDER = '<ALL>'


class AllTransformationMixin(BaseModel):
    @validator('*', pre=True)
    def all_options_to_list(cls, value: Any, field: Any) -> Any:
        if 'all_options' in field.field_info.extra:
            return field.field_info.extra['all_options'] if value == ALL_PLACEHOLDER else value
        return value


class EmailFromSetting(BaseModel):
    email: str
    name: str

    @property
    def verbose_from_email(self) -> str:
        return f'{self.name} <{self.email}>'


class BrandConfiguration(TemplateCheckConfigurationMixin, BaseConfigurationItem):
    email_from_settings: dict[str, EmailFromSetting]
    sms_transactional_sender_name: str


class GetCurrencyExchangeRatesResponse(BaseModel):
    datetime_calculated: datetime_module.datetime
    exchange_rates: dict[str, Decimal]


class WalletTransactionArchived(BaseModel):
    id: int
    wallet_id: int
    datetime: datetime_module.datetime
    opening_balance_available: Decimal
    opening_balance_on_hold: Decimal
    balance_available: Decimal
    balance_on_hold: Decimal
    system_namespace: str
    system: str
    system_transaction_id: Optional[str]
    details: Optional[str]

    # See entities_admin.py module for details (used for )
    @property
    def pk(self) -> str:
        # We have wallet id and datetime as part of primary key in clickhouse, so this is
        # optimal way to encode unique id of archived wallet transaction and select it from
        # clickhouse. Additional self.id is used to make it truly unique in case we have two
        # or more records with the same wallet_id and datetime.
        return f'{self.wallet_id}--{datetime_to_millis(self.datetime)}--{self.id}'

    @staticmethod
    def parse_pk(pk: str) -> tuple[int, str, int]:
        wallet_id_str, datetime_ts, wt_id_str = pk.split('--')
        return int(wallet_id_str), datetime_ts, int(wt_id_str)

    # NOTE: mimic WalletTransaction2 model string representation
    def __str__(self) -> str:
        return 'WalletTransactionArchived #{} (available: {}, hold: {})'.format(
            self.id,
            self.balance_available - self.opening_balance_available,
            self.balance_on_hold - self.opening_balance_on_hold,
        )


class CasinoActionArchived(BaseModel):
    id: str
    user_id: int
    uuid: UUID
    transaction_foreign_id: str
    rollback_transaction_id: Optional[str] = None
    round_id: Optional[str] = None
    session_id: int
    player_uuid: Optional[UUID] = None
    game_foreign_id: Optional[str] = None
    game_type: Optional[str] = None

    action_type: str
    status: str
    currency: str
    currency_foreign: str
    casino_provider: CasinoProviderType

    amount: Decimal
    amount_foreign: Decimal
    promo_amount: Decimal

    freespin_quantity: Optional[int] = None
    freespin_used_quantity: Optional[int] = None
    freespin_public_reward_id: Optional[UUID] = None
    freespin_promo_identifier: Optional[str] = None
    is_last_freespin: bool = False
    freespin_amount: Optional[Decimal] = None

    charges: Dict[int, str] = Field(default_factory=dict)

    created_at: datetime.datetime
    updated_at: Optional[datetime.datetime] = None

    @root_validator(pre=True)
    def prepare_charges(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        charges_wallet_ids = values.get('charges.wallet_id', [])
        charges_amounts = values.get('charges.amount', [])
        charges = dict(zip(charges_wallet_ids, charges_amounts))
        values['charges'] = charges
        return values

    @property
    def pk(self) -> str:
        """
        Clickhouse repo has primary key (user_id, created_at)
        """
        return f'{self.user_id}--{datetime_to_millis(self.created_at)}--{self.id}'

    @staticmethod
    def parse_pk(pk: str) -> tuple[int, str, str]:
        user_id, created_at_ts, action_id = pk.split('--')
        return int(user_id), created_at_ts, action_id

    @property
    def transaction_id(self) -> str:
        return self.transaction_foreign_id
