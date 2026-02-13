import base64
import hashlib
import hmac
import json
import logging
import warnings
from decimal import Decimal
from hmac import compare_digest
from typing import Any, Literal, Optional, TypeVar, Union, cast
from uuid import UUID

import requests
from bm.utils import BMJsonEncoder
from pydantic import BaseModel, Field
from requests import PreparedRequest

from rozert_pay_shared.const import CARD_EXPIRATION_REGEXP

logger = logging.getLogger(__name__)


def sign_request(request_body: str, secret: str) -> str:
    secret_key = secret.encode()
    message = request_body
    signature = hmac.new(secret_key, message.encode(), hashlib.sha256).digest()
    signature = base64.b64encode(signature)
    return signature.decode()


class Instruction(BaseModel):
    type: Literal["instruction_file", "instruction_qr_code", "instruction_reference"]
    link: Union[str, None] = None
    qr_code: Union[str, None] = None
    reference: Union[str, None] = None


with warnings.catch_warnings():
    warnings.filterwarnings(
        "ignore",
        message=r"Support for class-based `config` is deprecated.*",
        category=DeprecationWarning,
    )

    class TransactionExtraFormData(BaseModel):
        class Config:
            arbitrary_types_allowed = True

        action_url: str
        method: Literal["get", "post"]
        fields: dict[str, Any] = cast(dict[str, Any], Field(default_factory=dict))  # type: ignore

        def to_dict(self) -> dict[str, Any]:
            try:
                return self.model_dump()  # type: ignore[attr-defined]
            except AttributeError:
                return self.dict()


class TransactionData(BaseModel):
    id: str
    status: Literal["pending", "success", "failed", "refunded", "charged_back"]
    wallet_id: UUID
    type: Literal["deposit", "withdrawal"]
    amount: Decimal
    currency: str
    instruction: Union[Instruction, None]
    decline_code: Optional[str]
    decline_reason: Optional[str]

    user_data: Optional[dict[str, Any]] = None
    user_form_data: Optional[TransactionExtraFormData] = None

    card_token: Optional[str] = None
    external_account_id: Optional[str] = None


CARD_EXPIRATION_REGEXP = r"^(0[1-9]|1[0-2])/(\d{2}|\d{4})$"


class CardData(BaseModel):
    card_num: str
    card_expiration: str = Field(pattern=CARD_EXPIRATION_REGEXP)
    card_holder: str
    card_cvv: Optional[str] = None


class CardToken(BaseModel):
    card_token: str


class DepositRequest(BaseModel):
    wallet_id: UUID
    amount: Decimal
    currency: str
    callback_url: Optional[str] = None
    user_data: Optional[dict[str, Any]] = None
    redirect_url: Optional[str] = None
    card: Optional[CardData] = None
    customer_id: Optional[str] = None

    # For cardpay applepay
    encrypted_data: Optional[str] = None

    # For 3ds cards, customer browser data
    browser_data: dict[str, bool | int | str] | None = None


class PhoneRequired(BaseModel):
    phone: str


class StpCodiRequest(DepositRequest):
    user_data: PhoneRequired  # type: ignore[assignment]
    deposit_type: Literal["app", "qr_code"] = "app"


class WithdrawRequest(BaseModel):
    wallet_id: UUID
    amount: Decimal
    currency: str
    system: str
    user_data: Optional[dict[str, Any]] = None
    customer_id: Optional[str] = None

    callback_url: Optional[str] = None
    withdraw_to_account: Optional[str] = None

    # Card params
    card: Union[CardData, CardToken, None] = None

    # For cardpay applepay
    encrypted_data: Optional[str] = None


class DepositAccountResponse(BaseModel):
    deposit_account: str
    customer_id: UUID


def transaction_data_from_response(response: dict[str, Any]) -> TransactionData:
    data = {
        **response,
        "user_form_data": response.get("form"),
    }
    return to_model(TransactionData, data)


T = TypeVar('T', bound=BaseModel)


def to_model(model_class: type[T], data: dict[str, Any]) -> T:
    if hasattr(model_class, "model_validate"):
        return cast(Any, model_class).model_validate(data)
    return model_class(**data)  # type: ignore[arg-type]


class RozertClient:
    @staticmethod
    def verify_callback_signature(
        *,
        body: str,
        signature: str,
        secret_key: str,
    ) -> bool:
        assert isinstance(body, str)
        assert isinstance(signature, str)
        assert isinstance(secret_key, str)

        expected_signature = base64.b64encode(
            hmac.new(secret_key.encode(), body.encode(), hashlib.sha256).digest()
        ).decode()
        return compare_digest(signature, expected_signature)

    def __init__(
        self,
        *,
        host: str,
        merchant_id: str,
        secret_key: str,
        sandbox: bool = False,
    ):
        self.host = host
        self.merchant_id = merchant_id
        self.secret_key = secret_key
        self.session = requests.Session()
        self.sandbox = sandbox

    def start_deposit(
        self, request: DepositRequest, url: str, user_data: Optional[dict[str, Any]] = None
    ) -> TransactionData:
        data = (
            cast(Any, request).model_dump() if hasattr(request, "model_dump") else request.dict()
        )

        if user_data:
            data["user_data"] = user_data

        resp = self._make_request(
            method="post",
            url=url,
            data=data,
        )
        assert isinstance(resp, dict)
        return transaction_data_from_response(resp)

    def start_withdraw(
        self,
        request: WithdrawRequest,
        url: str,
    ) -> TransactionData:
        # TODO: pass url: str as in start_deposit
        data = (
            cast(Any, request).model_dump() if hasattr(request, "model_dump") else request.dict()
        )

        resp = self._make_request(
            method="post",
            url=url,
            data=data,
        )
        assert isinstance(resp, dict)
        return transaction_data_from_response(resp)

    def stp_codi_deposit(self, request: StpCodiRequest) -> TransactionData:
        return self.start_deposit(
            request=request,
            url="",
            user_data=request.user_data.dict(),
        )

    def _make_request(
        self,
        method: Literal['get', 'post'],
        url: str,
        data: Union[dict[str, Any], list[Any], None],
    ) -> Union[dict[str, Any], list[Any]]:  # pragma: no cover
        data_str = data and json.dumps(data, cls=BMJsonEncoder)
        resp = self.session.request(
            method=method,
            url=f"{self.host}{url}",
            data=data_str,
            headers=self._get_headers(data_str or ''),
        )
        req: PreparedRequest = resp.request
        logger.info(
            'made request in client %s',
            self.__class__.__name__,
            extra={
                'request_url': repr(req.path_url),
                'request_full_url': req.url,
                'response_status': resp.status_code,
            },
        )
        resp.raise_for_status()
        return resp.json()

    def _get_headers(self, data: str) -> dict[str, str]:
        result = {
            "X-Merchant-Id": self.merchant_id,
            "X-Signature": sign_request(data, self.secret_key),
            "Content-Type": "application/json",
        }
        if self.sandbox:
            result["X-Sandbox-Mode"] = "true"
        return result

    def get_transaction(self, id: str) -> TransactionData:
        resp = self._make_request(
            method="get",
            url=f"/api/payment/v1/transaction/{id}/",
            data=None,
        )
        assert isinstance(resp, dict), resp
        return transaction_data_from_response(resp)

    def create_deposit_account(
        self, *, url: str, customer_id: str, wallet_id: str
    ) -> DepositAccountResponse:
        resp = self._make_request(
            method="post",
            url=url,
            data={
                "customer_id": customer_id,
                "wallet_id": wallet_id,
            },
        )
        assert isinstance(resp, dict)
        return to_model(DepositAccountResponse, resp)
