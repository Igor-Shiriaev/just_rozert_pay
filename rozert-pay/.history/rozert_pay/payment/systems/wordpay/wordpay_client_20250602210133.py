import datetime
import hashlib
import os
import re
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
    username: str
    password: SecretStr
    secret2: SecretStr
    host: str
    operator: Optional[str]


class WordpayClient(base_classes.BasePaymentClient[WordpayCreds]):
    payment_system_name = const.PaymentSystemType.APPEX
    credentials_cls = WordpayCreds

    def deposit(self) -> entities.PaymentClientDepositResponse:
        assert self.trx.customer_card
        card_data = self.trx.customer_card.card_data_entity

        assert self.trx.customer
        lang = self.trx.customer.language

        assert card_data.card_cvv

        payload = {
            "amount": int(self.trx.amount),
            "amountcurr": self.trx.currency,
            "number": self.trx.uuid.hex,
            "description": f"Order {self.trx.uuid}",
            "trtype": "1",
            "account": self.creds.account,
            "lang": "ru" if lang == "ru" else "en",
            "email": self.trx.customer.email,
            "securecode": card_data.card_cvv.get_secret_value(),
            "ip_address": "127.0.0.1",
            "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
            "accept_language": lang,
        }

        expmonth = card_data.expiry_month
        expyear = card_data.expiry_year

        card_num = card_data.card_num.get_secret_value()
        payload.update(
            {
                "PAN": card_num,
                "expmonth": expmonth,
                "expyear": expyear,
                "cardholder": replace_non_ascii_chars(card_data.card_holder),
            }
        )
        additional = {
            "BIN": card_num[:6],
            "LAST4": card_num[-4:],
        }

        signature = self._sign_payload(
            payload=payload,
            secret1=self.creds.secret1,
            secret2=self.creds.secret2,
            fields_to_sign="amount, amountcurr, number, description, trtype, "
            "account, BIN, LAST4, expmonth, expyear, "
            "cardholder, paytoken, cf1, cf2, cf3".split(", "),
            additional=additional,
        )
        payload["signature"] = signature

        resp = self.session.post(
            f"{self.creds.host}/api/payment/execute",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=urlencode(payload),
        )
        parsed_data = resp.json()

        if parsed_data["status"] == "error":
            return entities.PaymentClientDepositResponse(
                status=const.TransactionStatus.FAILED,
                raw_response=parsed_data,
                id_in_payment_system=parsed_data.get("transID"),
                decline_code=parsed_data["errorcode"],
                decline_reason=parsed_data["errortext"],
            )

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
