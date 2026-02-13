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
        format: Literal["xml", "json"] = "xml",
    ) -> dict[str, ty.Any] | Exception:
        try:
            if format == "xml":
                body_raw = xmltodict.unparse(xml_dict, full_document=True, pretty=True)
                content_type = "text/xml; charset=utf-8"
            elif format == "json":
                body_raw = json.dumps(xml_dict)
                content_type = "application/json"
            else:
                raise RuntimeError

            digest = _make_digest(body_raw, creds.api_key)

            headers = {
                "Content-Type": content_type,
                "X-MERCHANT-DIGEST": digest,
            }
            r = session.post(
                f"{creds.api_url}{url}", data=body_raw, headers=headers, timeout=30
            )

            r.raise_for_status()
            if format == "xml":
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
                    "email": self.trx.customer.email,
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
                        "province": user_data.province,
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
            url="/platform/itix/direct/auth",
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
            url="/platform/ili/direct/threedcomplete",
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
        raise NotImplementedError

    def _get_transaction_status(self) -> entities.RemoteTransactionStatus:
        r = payment_audit_services.get_transaction_status(self.trx)
        if isinstance(r, errors.Error):
            raise r
        return r

    @classmethod
    def get_audit_items(
        cls,
        start: datetime.datetime,
        end: datetime.datetime,
        creds: IlixiumCreds,
    ) -> list[AuditItem]:
        data = cls.send_request(
            session=requests.Session(),
            url="/platform/ili/history/operations",
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
                    "type": "AUTH",
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
                }:
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
