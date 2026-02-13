import datetime
from typing import Any, Literal, Optional

import pydantic
from bm.datatypes import Money
from pydantic import BaseModel, Field, SecretStr
from rozert_pay.common import const
from rozert_pay.common.const import TransactionStatus
from rozert_pay_shared.rozert_client import TransactionExtraFormData


class RemoteTransactionStatus(pydantic.BaseModel):
    operation_status: TransactionStatus
    raw_data: dict  # type: ignore[type-arg]
    id_in_payment_system: Optional[str] = None
    decline_code: Optional[str] = None
    decline_reason: Optional[str] = None
    redirect_form_data: Optional[TransactionExtraFormData] = None
    client_extra: Optional[dict] = None  # type: ignore[type-arg]
    remote_amount: Optional[Money] = None
    refund_amount: Optional[Money] = None

    transaction_id: Optional[int] = None

    # If payment system returns account identifier in response,
    # it should be presented here.
    external_account_id: Optional[str] = None

    @classmethod
    def initial(
        cls,
        *,
        raw_data: dict[str, Any],
        id_in_payment_system: Optional[str] = None,
        transaction_id: Optional[int] = None,
    ) -> "RemoteTransactionStatus":
        return cls(
            operation_status=TransactionStatus.PENDING,
            raw_data=raw_data,
            id_in_payment_system=id_in_payment_system,
            transaction_id=transaction_id,
        )


class UserData(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    post_code: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    state: Optional[str] = None
    address: Optional[str] = None
    language: Optional[str] = None
    date_of_birth: Optional[datetime.date] = None
    ip_address: Optional[str] = None
    province: Optional[str] = None

    @property
    def full_name(self) -> str:
        assert self.first_name is not None
        assert self.last_name is not None
        return f"{self.first_name} {self.last_name}"


class PaymentClientWithdrawResponse(BaseModel):
    # status must be FAILED only if 100% sure that money are not sent to the user.
    # Otherwise it must be PENDING.
    status: Literal[TransactionStatus.PENDING, TransactionStatus.FAILED]
    id_in_payment_system: str | None
    raw_response: dict[str, Any]

    decline_code: Optional[str] = None
    decline_reason: Optional[str] = None

    def clean(self) -> None:
        if self.status == TransactionStatus.FAILED:
            assert (
                self.decline_code is not None
            ), "decline_code must be set if status is FAILED"


class PaymentClientDepositResponse(BaseModel):
    status: Literal[TransactionStatus.PENDING, TransactionStatus.FAILED, TransactionStatus.SUCCESS]
    raw_response: dict[str, Any]

    id_in_payment_system: str | None = None
    decline_code: str | None = None
    decline_reason: str | None = None

    # Use this field to redirect customer to intermediate pages/send some forms
    customer_redirect_form_data: TransactionExtraFormData | None = None

    def clean(self) -> None:
        if self.status == TransactionStatus.FAILED:
            assert (
                self.decline_code is not None
            ), "decline_code must be set if status is FAILED"


class PaymentClientDepositFinalizeResponse(BaseModel):
    # Status can be FAILED / SUCCESS. We don't return PENDING status here.
    # Deposit approval must be checked with payment system via callbacks / status checks.
    status: Literal[
        TransactionStatus.FAILED, TransactionStatus.SUCCESS, TransactionStatus.PENDING
    ]
    raw_response: dict[str, Any]

    decline_code: Optional[str] = None
    decline_reason: Optional[str] = None

    # TODO: handle card token
    card_token: Optional[str] = None


class Webhook(BaseModel):
    id: str
    url: str
    raw_data: dict[str, Any] = pydantic.Field(repr=False)


class CardData(BaseModel):
    card_num: SecretStr
    card_expiration: str = Field(pattern=const.CARD_EXPIRATION_REGEXP)
    card_holder: str
    card_cvv: SecretStr | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "card_num": self.card_num.get_secret_value(),
            "card_cvv": self.card_cvv.get_secret_value() if self.card_cvv else None,
            "card_expiration": self.card_expiration,
            "card_holder": self.card_holder,
        }

    @property
    def expiry_month(self) -> str:
        return self.card_expiration.split("/")[0]

    @property
    def expiry_year(self) -> str:
        return self.card_expiration.split("/")[1]
