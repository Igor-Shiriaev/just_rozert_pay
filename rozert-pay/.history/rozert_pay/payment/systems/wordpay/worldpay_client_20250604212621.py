import datetime
import hashlib
import os
import xmltodict
import typing as ty
from decimal import Decimal
from typing import Optional
from urllib.parse import urlencode

from bm.datatypes import Money
from bm.utils import quantize_decimal
from pydantic import BaseModel, SecretStr
from rozert_pay.common import const
from rozert_pay.payment import entities
from rozert_pay.payment.models import PaymentTransaction
from rozert_pay.payment.services import base_classes, db_services, deposit_services
from rozert_pay.payment.systems.appex.appex_const import APPEX_FOREIGN_MD, APPEX_PARES
from rozert_pay.payment.systems.appex.const import (
    APPEX_ERROR_CODE_DEPOSIT_NOT_FOUND,
    APPEX_ERROR_CODE_WITHDRAW_NOT_FOUND,
)


class WorldpayCreds(BaseModel):
    base_url: str = "https://secure-test.worldpay.com"
    username: SecretStr
    password: SecretStr
    merchant_code: SecretStr


class WorldpayClient(base_classes.BasePaymentClient[WorldpayCreds]):
    payment_system_name = const.PaymentSystemType.WORDPAY
    credentials_cls = WorldpayCreds

    _deposit_status_by_foreign_status = {
        "AUTHORISED": entities.TransactionStatus.SUCCESS,
        "SENT_FOR_AUTHORISATION": entities.TransactionStatus.PENDING,
        "REFUSED": entities.TransactionStatus.FAILED,
        "ERROR": entities.TransactionStatus.FAILED,
        "CANCELLED": entities.TransactionStatus.FAILED,
        "EXPIRED": entities.TransactionStatus.FAILED,
    }
    _withdrawal_status_by_foreign_status = {
        "SENT_FOR_REFUND": entities.TransactionStatus.SUCCESS,
        "REFUSED": entities.TransactionStatus.FAILED,
        2: entities.TransactionStatus.FAILED,
        3: entities.TransactionStatus.FAILED,
    }

    def deposit(self) -> entities.PaymentClientDepositResponse:
        assert self.trx.user_data
        assert self.trx.customer_card
        card_data: entities.CardData = self.trx.customer_card.card_data_entity
        assert card_data.card_cvv

        assert self.trx.customer

        xml_payload: str = self._build_xml_payload(self._build_deposit_payload(card_data, self.trx.user_data))

        resp = self.session.post(
            url=f"{self.creds.base_url}/jsp/merchant/xml/paymentService.jsp",
            headers={"Content-Type": "text/xml"},
            data=xml_payload.encode("utf-8"),
            timeout=30,
        )
        resp.raise_for_status()
        parsed_data: dict[str, ty.Any] = xmltodict.parse(resp.text)

        status = parsed_data["paymentService"]["reply"]["orderStatus"]["payment"]["lastEvent"]

        return entities.PaymentClientDepositResponse(
            status=self._deposit_status_by_foreign_status[status],
            raw_response=parsed_data,
            # `id_in_payment_system` is equal to `trx.uuid.hex`
            id_in_payment_system=parsed_data["paymentService"]["reply"]["orderStatus"]["@orderCode"],
            decline_code=parsed_data["paymentService"]["reply"]["orderStatus"]["payment"].get("ISO8583ReturnCode"),
            decline_reason=None,
        )

    def _build_deposit_payload(self, card_data: entities.CardData, user_data: entities.UserData) -> str:
        return {
        "paymentService": {
            "@version": "1.4",
            "@merchantCode": self.creds.merchant_code.get_secret_value(),
            "submit": {
                "order": {
                    "@orderCode": self.trx.uuid.hex,
                    "@installationId": self.creds.installation_id,
                    "description": self.trx.description,
                    "amount": {
                        "@value": str(self.trx.amount),
                        "@currencyCode": self.trx.currency,
                        "@exponent": "2"
                    },
                    "paymentDetails": {
                        "CARD-SSL": {
                            "cardNumber": card_data.card_num.get_secret_value(),
                            "expiryDate": {
                                "date": {
                                    "@month": card_data.expiry_month,
                                    "@year": card_data.expiry_year
                                }
                            },
                            "cardHolderName": card_data.card_holder,
                            "cvc": card_data.cvc.get_secret_value(),
                            "cardAddress": {
                                "address": {
                                    "address1": user_data.address1,
                                    "address2": user_data.address2,
                                    "address3": user_data.address3,
                                    "postalCode": user_data.post_code,
                                    "city": user_data.city,
                                    "state": user_data.state,
                                    "countryCode": user_data.country
                                }
                            }
                        },
                        "session": {
                            "@shopperIPAddress": "123.123.123.123",
                            "@id": "0215ui8ib1"
                        }
                    },
                    "shopper": {
                        "shopperEmailAddress": user_data.email
                    },
                    },
                },
            }
        }
    }

    def _build_withdraw_payload(self, card_data: entities.CardData, user_data: entities.UserData) -> str:
        return {
            "paymentService": {
                "@version": "1.4",
                "@merchantCode": self.creds.merchant_code.get_secret_value(),
                "submit": {
                    "order": {
                        "@orderCode": self.trx.uuid.hex,
                        "description": f"Order {self.trx.uuid}",
                        "amount": {
                            "@currencyCode": self.trx.currency,
                            "@exponent": "2",
                            "@value": str(self.trx.amount),
                        },
                        "paymentDetails": {
                            "@action": "REFUND",
                            "ECMC-SSL": {
                                "cardNumber": card_data.card_num.get_secret_value(),
                                "cardHolderName": card_data.card_holder,
                            },
                        },
                    }
                },
            }
        }

    def _build_xml_payload(self, payload: dict[str, ty.Any]) -> str:
        xml_str = xmltodict.unparse(
            payload,
            pretty=True,
            full_document=True,
            encoding="UTF-8"
        )

        doctype = (
            '<!DOCTYPE paymentService PUBLIC '
            '"-//Worldpay//DTD Worldpay PaymentService v1//EN" '
            '"http://dtd.worldpay.com/paymentService_v1.dtd">'
        )
        parts = xml_str.split("\n", 1)
        return f"{parts[0]}\n{doctype}\n{parts[1]}"

    def _get_withdrawal_payment_method(self) -> str:
        if self.trx.currency == "RUB":
            return "ECMC-SSL"
        else:
            return "CARD-SSL"

    def withdraw(self) -> entities.PaymentClientWithdrawResponse:
        assert self.trx.user_data
        assert self.trx.customer_card
        card_data: entities.CardData = self.trx.customer_card.card_data_entity
        assert card_data.card_cvv

        assert self.trx.customer

        xml_payload: str = self._build_xml_payload(self._build_withdraw_payload(card_data, self.trx.user_data))

        resp = self.session.post(
            url=f"{self.creds.base_url}/jsp/merchant/xml/paymentService.jsp",
            headers={"Content-Type": "text/xml"},
            data=xml_payload.encode("utf-8"),
            timeout=30,
        )
        resp.raise_for_status()
        parsed_data: dict[str, ty.Any] = xmltodict.parse(resp.text)

        status = parsed_data["paymentService"]["reply"]["orderStatus"]["payment"]["lastEvent"]

        return entities.PaymentClientDepositResponse(
            status=self._deposit_status_by_foreign_status[status],
            raw_response=parsed_data,
            # `id_in_payment_system` is equal to `trx.uuid.hex`
            id_in_payment_system=parsed_data["paymentService"]["reply"]["orderStatus"]["@orderCode"],
            decline_code=parsed_data["paymentService"]["reply"]["orderStatus"]["payment"].get("ISO8583ReturnCode"),
            decline_reason=None,
        )

    def _get_transaction_status(self) -> entities.RemoteTransactionStatus:
        trx: PaymentTransaction = PaymentTransaction.objects.get(uuid=self.trx.uuid)

        if trx.type == const.TransactionType.DEPOSIT:
            data = self._check_pay_status(trx, self.creds)
        else:
            data = self._check_payout_status(trx, self.creds)

        if data.get("errorcode") in [
            APPEX_ERROR_CODE_WITHDRAW_NOT_FOUND,
            APPEX_ERROR_CODE_DEPOSIT_NOT_FOUND,
        ] and not data.get("transID"):
            return entities.RemoteTransactionStatus(
                operation_status=const.TransactionStatus.FAILED,
                raw_data=data,
                decline_code=const.TransactionDeclineCodes.TRANSACTION_NOT_FOUND,
            )

        if data.get("errorcode") in ["9010", "702"]:
            # See https://betmaster.slack.com/archives/C07JV737Y/p1692007321186879 thread
            operation_status = const.TransactionStatus.FAILED
        else:
            # If there is no number in response, it means some unexpected error.
            operation_status = {
                "error": const.TransactionStatus.FAILED,
                "OK": const.TransactionStatus.SUCCESS,
                "wait": const.TransactionStatus.PENDING,
            }[data["status"]]

        return entities.RemoteTransactionStatus(
            operation_status=operation_status,
            raw_data=data,
            id_in_payment_system=data.get("transID"),
            decline_code=data.get("errorcode"),
            decline_reason=data.get("errortext"),
            remote_amount=Money(
                Decimal(data["amount"]),
                data["amountcurr"],
            )
            if "amount" in data
            else None,
        )

    def _check_pay_status(
        self, trx: PaymentTransaction, creds: WorldpayCreds
    ) -> dict[str, ty.Any]:
        payload = {
            "opertype": "check",
            "number": trx.uuid.hex,
            "account": creds.account,
        }

        payload["signature"] = self._sign_payload(
            payload=payload,
            secret1=creds.secret1,
            secret2=creds.secret2,
            fields_to_sign=[
                "opertype",
                "account",
                "transID",
            ],
            # From docs, even if we don't pass transID we must put empty data
            # when generate signature.
            additional={
                "transID": "",
            },
        )

        response = self.session.post(
            url=f"{creds.host}/api/payment/operate",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=urlencode(payload),
        )
        return response.json()

    def _check_payout_status(
        self, trx: PaymentTransaction, creds: WorldpayCreds
    ) -> dict[str, ty.Any]:
        payload = {
            "account": creds.account,
            "number": trx.uuid.hex,
        }

        payload["signature"] = self._sign_payload(
            payload,
            secret1=creds.secret1,
            secret2=creds.secret2,
            fields_to_sign=[
                "account",
                "number",
                "transID",
            ],
            # From docs, even if we don't pass transID we must put empty data
            # when generate signature.
            additional={
                "transID": "",
            },
        )

        response = self.session.post(
            url=f"{creds.host}/api/payout/status",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=urlencode(payload),
        )
        return response.json()

    @classmethod
    def _sign_payload(
        cls,
        payload: dict[str, ty.Any],
        *,
        fields_to_sign: list[str],
        secret1: SecretStr,
        secret2: SecretStr,
        additional: Optional[dict[str, ty.Any]] = None,
        force_fields: Optional[list[str]] = None,
        mask_params_when_sign: bool = False,
    ) -> str:
        """mask_params_when_sign - if true, mask params (which must be card number) to 444444******4444."""
        if "PANmasked" in payload:
            payload.setdefault("cardholder", "")

        data = []
        keys = []
        additional = additional or {}
        for key in fields_to_sign:
            if key in additional:
                data.append(additional[key])
                keys.append(key)
                continue

            if key not in payload:
                continue

            value = str(payload[key])

            if mask_params_when_sign and key == "params":
                assert value.isnumeric(), f"bad: {key} {value}. must be card num"
                value = value[:6] + "*" * 6 + value[-4:]

            if value or key in (force_fields or []):
                data.append(value)
                keys.append(key)

        data += [secret1.get_secret_value(), secret2.get_secret_value()]
        str_data = ":".join(data)
        return hashlib.md5(str_data.encode("utf8")).hexdigest().upper()


class WorldpaySandboxClient(base_classes.BaseSandboxClientMixin[WorldpayCreds], WorldpayClient):
    pass
