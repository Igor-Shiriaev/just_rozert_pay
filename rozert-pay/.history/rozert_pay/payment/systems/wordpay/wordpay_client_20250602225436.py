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


class WordpayCreds(BaseModel):
    base_url: str = "https://secure-test.worldpay.com"
    username: SecretStr
    password: SecretStr
    merchant_code: SecretStr


class WordpayClient(base_classes.BasePaymentClient[WordpayCreds]):
    payment_system_name = const.PaymentSystemType.WORDPAY
    credentials_cls = WordpayCreds

    _deposit_status_by_foreign_status = {
        "AUTHORISED": entities.TransactionStatus.PENDING,
        "REFUSED": entities.TransactionStatus.FAILED,
        "ERROR": entities.TransactionStatus.FAILED,
    }
    _withdrawal_status_by_foreign_status = {
        0: entities.TransactionStatus.PENDING,
        1: entities.TransactionStatus.SUCCESS,
        2: entities.TransactionStatus.FAILED,
        3: entities.TransactionStatus.FAILED,
    }

    def deposit(self) -> entities.PaymentClientDepositResponse:
        assert self.trx.user_data
        assert self.trx.customer_card
        card_data: entities.CardData = self.trx.customer_card.card_data_entity
        assert card_data.card_cvv

        assert self.trx.customer

        xml_payload: str = self._build_deposit_xml_payload(card_data, self.trx.user_data)

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
            # `id_in_payment_system` is equal to `trx.uuid.hex` in response.
            id_in_payment_system=parsed_data.get("transID"),
            decline_code=parsed_data["errorcode"],
            decline_reason=parsed_data["errortext"],
        )
        if status == "error":

        if parsed_data["status"] == "wait":
            redirect_form_data = None
            if "PaReq" in parsed_data:
                redirect_form_data = entities.TransactionExtraFormData(
                    action_url=parsed_data["ACSURL"],
                    method="post",
                    fields={
                        "PaReq": parsed_data["PaReq"],
                        "MD": parsed_data["MD"],
                        "TermUrl": deposit_services.get_redirect_url(
                            const.PaymentSystemType.APPEX,
                            trx_id=self.trx.uuid,
                        ),
                    },
                )

                db_services.save_extra_field(
                    trx_id=self.trx.id,
                    field=APPEX_FOREIGN_MD,
                    value=parsed_data["MD"],
                )

            return entities.PaymentClientDepositResponse(
                status=const.TransactionStatus.PENDING,
                raw_response=parsed_data,
                id_in_payment_system=parsed_data["transID"],
                customer_redirect_form_data=redirect_form_data,
            )

        if parsed_data["status"] == "OK":
            return entities.PaymentClientDepositResponse(
                status=const.TransactionStatus.PENDING,
                raw_response=parsed_data,
                id_in_payment_system=parsed_data["transID"],
            )

        raise RuntimeError("unknown deposit status")  # pragma: no cover

    def _build_deposit_xml_payload(self, card_data: entities.CardData, user_data: entities.UserData) -> str:
        payment_dict = {
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
                            "CARD-SSL": {
                                "cardNumber": card_data.card_num.get_secret_value(),
                                "expiryDate": {
                                    "date": {
                                        "@month": card_data.expiry_month,
                                        "@year": card_data.expiry_year,
                                    }
                                },
                                "cardHolderName": card_data.card_holder,
                                "cardAddress": {
                                    "address": {
                                        "address1": user_data.address,
                                        "postalCode": user_data.post_code,
                                        "city": user_data.city,
                                        "state": user_data.state,
                                        "countryCode": user_data.country,
                                    }
                                },
                            },
                            "session": {
                                "@shopperIPAddress": "127.0.0.1",
                                "@id": "0215ui8ib1",
                            },
                        },
                        "shopper": {
                            "shopperEmailAddress": user_data.email,
                            "browser": {
                                "acceptHeader": "text/html",
                                "userAgentHeader": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
                            },
                        },
                        "dynamicMCC": "5045",
                        "dynamicInteractionType": {
                            "@type": "ECOMMERCE"
                        },
                        "dynamic3DS": {
                            "@overrideAdvice": "do3DS"
                        },
                    }
                },
            }
        }

        xml_str = xmltodict.unparse(
            payment_dict,
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

    def deposit_finalize(self) -> entities.PaymentClientDepositFinalizeResponse:
        assert self.trx.id_in_payment_system

        pares = self.trx.extra[APPEX_PARES]
        md = self.trx.extra[APPEX_FOREIGN_MD]

        payload = {
            "PaRes": pares,
            "MD": md,
            "transID": str(self.trx.id_in_payment_system),
            "datetime": str(datetime.datetime.now()),
        }

        payload["signature"] = self._sign_payload(
            payload,
            secret1=self.creds.secret1,
            secret2=self.creds.secret2,
            fields_to_sign=["PaRes", "MD", "transID", "datetime"],
        )

        resp = self.session.post(
            f"{self.creds.host}/api/payment/pares",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=urlencode(payload),
        )
        parsed_data: dict[str, ty.Any] = resp.json()

        id_in_payment_system = parsed_data.get("transID")
        if id_in_payment_system:
            assert id_in_payment_system == self.trx.id_in_payment_system
        else:  # pragma: no cover
            id_in_payment_system = self.trx.id_in_payment_system

        error_code = parsed_data.get("errorcode") or parsed_data.get("processing_code")
        error_text = parsed_data.get("errortext") or parsed_data.get("processing_text")

        return entities.PaymentClientDepositFinalizeResponse(
            status={  # type: ignore[arg-type]
                "error": const.TransactionStatus.FAILED,
                "OK": const.TransactionStatus.SUCCESS,
                "wait": const.TransactionStatus.PENDING,
            }[parsed_data["status"]],
            raw_response=parsed_data,
            decline_code=error_code,
            decline_reason=error_text,
        )

    def withdraw(self) -> entities.PaymentClientWithdrawResponse:
        amount = quantize_decimal(self.trx.amount, 2)

        assert self.trx.customer_card
        card_data = self.trx.customer_card.card_data_entity

        card_num: str = card_data.card_num.get_secret_value()
        mask_params_when_sign = False

        payload = {
            "account": self.creds.account,
            "operator": self.creds.operator,
            "params": card_num,
            "amount": str(amount),
            "amountcurr": self.trx.currency,
            "number": self.trx.uuid.hex,
            # one time unique value
            "nonce": os.urandom(8).hex(),
        }

        signature = self._sign_payload(
            payload,
            secret1=self.creds.secret1,
            secret2=self.creds.secret2,
            fields_to_sign=[
                "nonce",
                "account",
                "operator",
                "params",
                "amount",
                "amountcurr",
                "number",
            ],
            mask_params_when_sign=mask_params_when_sign,
        )
        payload["signature"] = signature

        resp = self.session.post(
            f"{self.creds.host}/api/payout/execute",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=urlencode(payload),
        )
        parsed_data = resp.json()

        if parsed_data["status"] == "error":
            return entities.PaymentClientWithdrawResponse(
                status=const.TransactionStatus.FAILED,
                raw_response=parsed_data,
                decline_code=parsed_data.get("errorcode"),
                decline_reason=parsed_data.get("errortext"),
                id_in_payment_system=parsed_data.get("transID"),
            )

        return entities.PaymentClientWithdrawResponse(
            status=const.TransactionStatus.PENDING,
            raw_response=parsed_data,
            id_in_payment_system=str(parsed_data["transID"]),
            decline_code=parsed_data.get("errorcode"),
            decline_reason=parsed_data.get("errortext"),
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
        self, trx: PaymentTransaction, creds: WordpayCreds
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
        self, trx: PaymentTransaction, creds: WordpayCreds
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


class WordpaySandboxClient(base_classes.BaseSandboxClientMixin[WordpayCreds], WordpayClient):
    pass
