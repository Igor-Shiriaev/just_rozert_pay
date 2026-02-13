import base64
import datetime
import hashlib
import json
import logging
import typing as ty
from decimal import Decimal
from typing import Literal

import pycountry
import pytz
import requests
import xmltodict
from bm.datatypes import Money
from currency.utils import from_minor_units, to_minor_units
from django.conf import settings
from pydantic import BaseModel
from rozert_pay.common import const
from rozert_pay.common.const import (
    PaymentSystemType,
    TransactionDeclineCodes,
    TransactionExtraFields,
    TransactionStatus,
)
from rozert_pay.payment import entities, types
from rozert_pay.payment.api_v1.serializers.card_serializers import (
    CardBrowserDataSerializer,
)
from rozert_pay.payment.models import PaymentTransaction
from rozert_pay.payment.services import base_classes, errors
from rozert_pay.payment.services.deposit_services import get_return_url
from rozert_pay.payment.services.incoming_callbacks import get_rozert_callback_url
from rozert_pay.payment.systems.ilixium.ilixium_const import ILIXIUM_PROVINCE_MAP
from rozert_pay.payment_audit import services as payment_audit_services
from rozert_pay.payment_audit.services.audit_items_synchronization import (
    AuditItem,
    AuditItemsSynchronizationClientMixin,
)
from rozert_pay_shared.rozert_client import TransactionExtraFormData

logger = logging.getLogger(__name__)


def currency_numeric(code: str) -> str:
    c = pycountry.currencies.get(alpha_3=code.upper())
    if not c:
        raise ValueError(f"Unknown currency {code}")
    return c.numeric


def _make_digest(
    xml_str: str,
    password: str,
) -> str:
    b64 = base64.b64encode(hashlib.sha512(xml_str.encode("utf-8")).digest())
    data = b64 + password.encode("utf-8")
    return base64.b64encode(hashlib.sha512(data).digest()).decode("ascii")


class IlixiumCreds(BaseModel):
    merchant_id: str
    account_id: str
    api_key: str
    api_url: str = "https://prprocessing.ilixium.com"

    withdrawal_api_key: str
    withdrawal_merchant_name: str


ILIXIUM_URL_PREFIX = "/platform/itix" if settings.IS_PRODUCTION else "/platform/ili"


class IlixiumUtils:
    @classmethod
    def to_merchant_ref(cls, trx: PaymentTransaction) -> str:
        return f"trx{trx.id}"

    @classmethod
    def get_transaction_id_from_merchant_ref(cls, ref: str) -> types.TransactionId:
        return types.TransactionId(int(ref[3:]))


class IlixiumClient(
    base_classes.BasePaymentClient[IlixiumCreds],
    AuditItemsSynchronizationClientMixin[IlixiumCreds],
):
    payment_system_name = const.PaymentSystemType.ILIXIUM
    credentials_cls = IlixiumCreds

    def _post_init(self) -> None:
        super()._post_init()
        self.session.response_parsers = [xmltodict.parse]
        self.session.on_request_parser = xmltodict.parse

    @classmethod
    def send_request(
        cls,
        *,
        session: requests.Session,
        url: str,
        xml_dict: dict[str, ty.Any],
        creds: IlixiumCreds,
        type: Literal["deposit", "withdrawal"] = "deposit",
    ) -> dict[str, ty.Any] | Exception:
        try:
            if type == "deposit":
                body_raw = xmltodict.unparse(xml_dict, full_document=True, pretty=True)
                content_type = "text/xml; charset=utf-8"
                api_key = creds.api_key
            elif type == "withdrawal":
                body_raw = json.dumps(xml_dict)
                content_type = "application/json"
                api_key = creds.withdrawal_api_key
            else:
                raise RuntimeError

            digest = _make_digest(body_raw, api_key)

            headers = {
                "Content-Type": content_type,
                "X-MERCHANT-DIGEST": digest,
            }
            r = session.post(
                f"{creds.api_url}{url}", data=body_raw, headers=headers, timeout=30
            )

            r.raise_for_status()
            if type == "deposit":
                return xmltodict.parse(r.text)
            else:
                return r.json()
        except Exception as e:
            logger.exception("")
            return e

    @property
    def _transaction(self) -> dict[str, ty.Any]:
        return {
            "transactionType": "ECOMMERCE",
            "amount": int(to_minor_units(self.trx.amount, self.trx.currency)),
            "currency": currency_numeric(self.trx.currency),
            "merchantRef": IlixiumUtils.to_merchant_ref(self.trx),
        }

    @property
    def _merchant(self) -> dict[str, ty.Any]:
        return {
            "merchantId": self.creds.merchant_id,
            "accountId": self.creds.account_id,
        }

    def deposit(self) -> entities.PaymentClientDepositResponse:
        assert self.trx.customer_card

        card_data = self.trx.customer_card.card_data_entity
        assert card_data

        assert self.trx.customer

        assert card_data.card_cvv

        user_data = self.trx.user_data
        if not user_data:
            raise errors.SafeFlowInterruptionError("No user data")

        if not self.trx.customer:
            raise errors.SafeFlowInterruptionError("No customer")

        if not card_data.card_cvv:
            raise errors.SafeFlowInterruptionError("No card cvv")

        browser_data = CardBrowserDataSerializer.from_trx(self.trx)

        province = (
            ILIXIUM_PROVINCE_MAP.get(user_data.province.lower(), user_data.province)
            if user_data.province
            else ""
        )

        auth_request = {
            "authRequest": {
                "version": "2",
                "transaction": self._transaction,
                "deferredCapture": True,
                "paymentMethodType": "CARD",
                "merchant": self._merchant,
                "card": {
                    "cardNumber": card_data.card_num.get_secret_value(),
                    "securityCode": card_data.card_cvv.get_secret_value(),
                    "expiryDate": f"{card_data.expiry_month}{card_data.expiry_year}",
                },
                "customer": {
                    "customerId": self.trx.customer.uuid,
                    "email": self.trx.customer.email_encrypted.get_secret_value()
                    if self.trx.customer.email_encrypted is not None
                    else None,
                    "firstName": user_data.first_name,
                    "surname": user_data.last_name,
                    "address": {
                        "addressLine1": user_data.address.replace("\n", " ").replace(
                            "\r", " "
                        )
                        if user_data.address
                        else "",
                        "city": user_data.city,
                        "postcode": user_data.post_code,
                        "country": user_data.country,
                        "province": province,
                    },
                    "mobileNumber": user_data.phone,
                    "dateOfBirth": user_data.date_of_birth.strftime("%d%m%Y")
                    if user_data.date_of_birth
                    else "01012000",
                },
                "paymentInfo": {
                    "country": user_data.country,
                    "ipAddress": user_data.ip_address,
                },
                "emvco3ds": {
                    "browserDetails": {
                        "acceptHeader": browser_data.accept_header,
                        "javaScriptEnabled": browser_data.javascript_enabled,
                        "javaEnabled": browser_data.java_enabled,
                        "language": browser_data.language,
                        "screenHeight": browser_data.screen_height,
                        "screenWidth": browser_data.screen_width,
                        "timeDifference": browser_data.time_difference,
                        "userAgent": browser_data.user_agent,
                        "colorDepth": browser_data.color_depth,
                        "challengeWindowSize": browser_data.challenge_window_size,
                    },
                },
            }
        }
        resp = self.send_request(
            session=self.session,
            url=f"{ILIXIUM_URL_PREFIX}/direct/auth",
            xml_dict=auth_request,
            creds=self.creds,
        )
        if isinstance(resp, Exception):
            return entities.PaymentClientDepositResponse(
                status=const.TransactionStatus.FAILED,
                raw_response={
                    "error": str(resp),
                },
            )

        match resp["paymentResponse"]:
            case {
                "status": {
                    "code": "PENDING",
                },
                "paymentHistory": {
                    "paymentAttempt": {
                        "cardResponse": {
                            "threeDSecureAcsUrl": threeDSecureAcsUrl,
                            "threeDSecureMd": threeDSecureMd,
                            "threeDSecurePaReq": threeDSecurePaReq,
                        }
                    }
                },
            }:
                fd = TransactionExtraFormData(
                    action_url=threeDSecureAcsUrl,
                    method="post",
                    fields={
                        "MD": threeDSecureMd,
                        "PaReq": threeDSecurePaReq,
                        "TermUrl": get_return_url(
                            system=PaymentSystemType.ILIXIUM,
                            trx_id=self.trx.uuid,
                        ),
                    },
                )

                return entities.PaymentClientDepositResponse(
                    status=TransactionStatus.PENDING,
                    raw_response=resp,
                    customer_redirect_form_data=fd,
                )

            case {
                "status": {
                    "code": "REJECTED",
                    "message": message,
                }
            }:
                return entities.PaymentClientDepositResponse(
                    status=TransactionStatus.FAILED,
                    raw_response=resp,
                    decline_code=message,
                    decline_reason=message,
                )

            case _:
                raise RuntimeError("Unable to parse authorization response")

    def deposit_finalize(self) -> entities.PaymentClientDepositFinalizeResponse:
        match self.trx.extra.get(TransactionExtraFields.REDIRECT_RECEIVED_DATA):
            case {
                "MD": md,
                "PaRes": pares,
            }:
                pass
            case _:
                raise RuntimeError("No redirect data received!")

        payload = {
            "threeDSecureCompleteRequest": {
                "version": "2",
                "transaction": {
                    "merchantRef": self._transaction["merchantRef"],
                },
                "merchant": self._merchant,
                "threeDSecure": {
                    "md": md,
                    "paRes": pares,
                },
            }
        }

        resp = self.send_request(
            session=self.session,
            url=f"{ILIXIUM_URL_PREFIX}/direct/threedcomplete",
            xml_dict=payload,
            creds=self.creds,
        )
        if isinstance(resp, Exception):
            return entities.PaymentClientDepositFinalizeResponse(
                status=TransactionStatus.FAILED,
                raw_response={},
                decline_code=TransactionDeclineCodes.INTERNAL_ERROR,
                decline_reason=str(resp),
            )

        match resp["paymentResponse"]["paymentHistory"]["paymentAttempt"]:
            case {
                "code": "SUCCESS",
                "token": card_token,
            }:
                return entities.PaymentClientDepositFinalizeResponse(
                    status=TransactionStatus.SUCCESS,
                    raw_response=resp,
                    card_token=card_token,
                )

            case {
                "code": "DECLINED",
                "message": message,
            }:
                return entities.PaymentClientDepositFinalizeResponse(
                    status=TransactionStatus.FAILED,
                    raw_response=resp,
                    decline_code=message,
                    decline_reason=message,
                )
            case _:
                raise RuntimeError("Unknown response")

    def withdraw(self) -> entities.PaymentClientWithdrawResponse:
        # Build payload from real transaction and user data
        ud = self.trx.user_data

        if not ud:
            raise errors.SafeFlowInterruptionError("No user data")

        payment_date = datetime.date.today().strftime("%Y-%m-%d")
        payload: dict[str, ty.Any] = {
            "paymentMerchant": self.creds.withdrawal_merchant_name,
            "paymentTarget": "CANADA_EFT",
            "paymentCategory": "DISBURSEMENT",
            "paymentDate": payment_date,
            "paymentAmount": float(self.trx.amount),
            "paymentCurrency": self.trx.currency,
            "merchantReference": str(self.trx.uuid),
            "beneficiaryFirstName": ud.first_name or "",
            "beneficiaryLastName": ud.last_name or "",
            "beneficiaryPostcode": ud.post_code or "",
            "beneficiaryDob": ud.date_of_birth.strftime("%Y-%m-%d")
            if ud.date_of_birth
            else "",
            # Bank details
            "beneficiarySortCode": self.trx.extra["beneficiary_sort_code"],
            "beneficiaryBankCode": self.trx.extra["beneficiary_bank_code"],
            "beneficiaryAccountNumber": self.trx.extra["beneficiary_account_number"],
            # Address
            "beneficiaryAddr1": (ud.address or "")[:200],
            "callbackUrl": get_rozert_callback_url(
                system=self.trx.system,
                trx_uuid=self.trx.uuid,
            ),
        }

        resp = self.send_request(
            session=self.session,
            url="/platform/payment/pace/api/v1/payment/create",
            xml_dict=payload,
            type="withdrawal",
            creds=self.creds,
        )
        if isinstance(resp, Exception):
            raise resp

        try:
            status = ty.cast(str, resp.get("status"))
            pace_ref = ty.cast(str | None, resp.get("paceTransactionRef"))
        except Exception:
            raise RuntimeError("Unable to parse PACE withdraw response")

        if status in {"REJECTED", "FAILED"}:
            decline_code = None
            decline_reason = None
            try:
                if resp.get("errors"):
                    e0 = resp["errors"][0]
                    decline_code = e0.get("errorCode")
                    decline_reason = e0.get("errorDescription")
            except Exception:
                pass
            return entities.PaymentClientWithdrawResponse(
                status=TransactionStatus.FAILED,
                id_in_payment_system=pace_ref,
                raw_response=resp,
                decline_code=decline_code or TransactionDeclineCodes.INTERNAL_ERROR,
                decline_reason=decline_reason or "Rejected",
            )

        # Pending or any other non-final status
        return entities.PaymentClientWithdrawResponse(
            status=TransactionStatus.PENDING,
            id_in_payment_system=pace_ref,
            raw_response=resp,
        )

    def _get_transaction_status(self) -> entities.RemoteTransactionStatus:
        if self.trx.type == const.TransactionType.DEPOSIT:
            r = payment_audit_services.get_transaction_status(self.trx)
            if isinstance(r, errors.Error):
                raise r
            return r
        else:
            return self._get_withdrawal_status()

    def _get_withdrawal_status(self) -> entities.RemoteTransactionStatus:
        payload = {
            "paymentMerchant": self.creds.withdrawal_merchant_name,
            "merchantReference": str(self.trx.uuid),
        }

        resp = self.send_request(
            session=self.session,
            url="/platform/payment/pace/api/v1/payment/find",
            xml_dict=payload,
            creds=self.creds,
            type="withdrawal",
        )
        if isinstance(resp, Exception):
            raise resp

        # Parse status response
        try:
            pace_ref = ty.cast(str | None, resp.get("paceTransactionRef"))
            status = ty.cast(str, resp.get("status"))
        except Exception:
            raise RuntimeError("Unable to parse PACE find response")

        status_map = {
            "CONFIRMED": TransactionStatus.SUCCESS,
            "PENDING": TransactionStatus.PENDING,
            "REJECTED": TransactionStatus.FAILED,
            "FAILED": TransactionStatus.FAILED,
        }
        op_status = status_map.get(status, TransactionStatus.PENDING)

        decline_code = None
        decline_reason = None
        if op_status == TransactionStatus.FAILED and resp.get("errors"):
            try:
                e0 = resp["errors"][0]
                decline_code = e0.get("errorCode")
                decline_reason = e0.get("errorDescription")
            except Exception:
                pass

        remote_amount = None
        try:
            if resp.get("paymentAmount") and resp.get("paymentCurrency"):
                remote_amount = Money(
                    Decimal(str(resp["paymentAmount"])),
                    str(resp["paymentCurrency"]),
                )
        except Exception:
            remote_amount = None

        external_account_id = None
        try:
            external_account_id = resp.get("beneficiaryAccountNumber")
        except Exception:
            pass

        return entities.RemoteTransactionStatus(
            operation_status=op_status,
            raw_data=resp,  # type: ignore[arg-type]
            id_in_payment_system=pace_ref,
            decline_code=decline_code,
            decline_reason=decline_reason,
            remote_amount=remote_amount,
            external_account_id=external_account_id,
        )

    @classmethod
    def get_audit_items(
        cls,
        start: datetime.datetime,
        end: datetime.datetime,
        creds: IlixiumCreds,
    ) -> list[AuditItem]:
        data = cls.send_request(
            session=requests.Session(),
            url=f"{ILIXIUM_URL_PREFIX}/history/operations",
            xml_dict={
                "historyRequest": {
                    "merchant": {
                        "merchantId": creds.merchant_id,
                        "accountId": creds.account_id,
                    },
                    "periodStartDate": start.astimezone(pytz.utc).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    ),
                    "periodEndDate": end.astimezone(pytz.utc).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    ),
                    "reportFormat": "XML",
                }
            },
            creds=creds,
        )

        if isinstance(data, Exception):
            raise data

        result: list[AuditItem] = []

        for item in data["historyResponse"]["operation"]:
            match item:
                case {
                    "entryDate": operation_time,
                    "type": op_type,
                    "status": {
                        "code": status,
                        "message": message,
                    },
                    "transaction": {
                        "amount": amount_in_minor,
                        "currency": currency,
                        "gatewayRef": gatewayRef,
                        "merchantRef": merchantRef,
                    },
                } if op_type in {"AUTH", "CREDIT"}:
                    transaction_id = IlixiumUtils.get_transaction_id_from_merchant_ref(
                        merchantRef
                    )
                    item = AuditItem(
                        operation_time=operation_time,
                        transaction_id=transaction_id,
                        id_in_payment_system=gatewayRef,
                        operation_status={
                            "REJECTED": TransactionStatus.FAILED,
                            "SUCCESS": TransactionStatus.SUCCESS,
                        }.get(status, TransactionStatus.PENDING),
                        raw_data=item,
                        remote_amount=Money(
                            from_minor_units(Decimal(amount_in_minor), currency),
                            currency,
                        ),
                    )

                    if item.operation_status == TransactionStatus.FAILED:
                        item.decline_code = message
                        item.decline_reason = message

                    result.append(item)

                case _:
                    logger.warning(
                        "Unparsable item received",
                        extra={
                            "item": item,
                        },
                    )

        return result


class IlixiumSandboxClient(  # type: ignore[misc]
    base_classes.BaseSandboxClientMixin[IlixiumCreds], IlixiumClient
):
    pass
