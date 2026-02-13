import logging
import time
import typing as ty
from datetime import timedelta
from functools import cached_property
from uuid import uuid4

import pytz
from bm.datatypes import Money
from django.conf import settings
from django.utils import timezone
from pydantic import BaseModel, SecretStr
from rozert_pay.common import const
from rozert_pay.common.helpers import cache
from rozert_pay.payment import entities, models
from rozert_pay.payment.entities import RemoteTransactionStatus
from rozert_pay.payment.services import base_classes, errors

logger = logging.getLogger(__name__)


class CardpayCreds(BaseModel):
    terminal_code: int
    terminal_password: SecretStr
    callback_secret: SecretStr
    test_mode: bool = False


CARDPAY_STATUS_MAP = {
    "COMPLETED": const.TransactionStatus.SUCCESS,
    "DECLINED": const.TransactionStatus.FAILED,
    "IN_PROGRESS": const.TransactionStatus.PENDING,
    "NEW": const.TransactionStatus.PENDING,
    "AUTHORIZED": const.TransactionStatus.PENDING,
    "CHARGED_BACK": const.TransactionStatus.CHARGED_BACK,
    "CHARGEBACK_RESOLVED": const.TransactionStatus.CHARGED_BACK_REVERSAL,
    "REFUNDED": const.TransactionStatus.REFUNDED,
}


def _prepare_email(email: str) -> str:
    email = email.replace("+", "").replace("_", "")
    name, domain = email.split("@")
    domain = domain.replace("-", "")
    return f"{name}@{domain}"


class _BaseCardpayClient(base_classes.BasePaymentClient[CardpayCreds]):
    credentials_cls = CardpayCreds  # type: ignore[assignment]

    payment_method: str

    @property
    def _customer(self) -> models.Customer:
        if not self.trx.customer:
            raise errors.SafeFlowInterruptionError("Customer is required")
        return self.trx.customer

    @property
    def _email(self) -> str:
        email = None

        if customer := self._customer:
            if customer.email_encrypted is not None:
                email = customer.email_encrypted.get_secret_value()

        if ud := self.trx.user_data:
            email = ud.email

        if not email:
            raise errors.SafeFlowInterruptionError("No email passed")

        return _prepare_email(email)

    def withdraw(self) -> entities.PaymentClientWithdrawResponse:
        payout_request = self._get_withdraw_request()

        response = self._make_request(
            url="/api/payouts",
            method="POST",
            data=payout_request,
        )
        if response.get("http_status_code") == 400:
            return entities.PaymentClientWithdrawResponse(
                status=const.TransactionStatus.FAILED,
                id_in_payment_system=None,
                raw_response=response,
                decline_code=response["name"],
                decline_reason=response["message"],
            )

        return entities.PaymentClientWithdrawResponse(
            status={  # type: ignore[arg-type]
                "COMPLETED": const.TransactionStatus.PENDING,
                "FAILED": const.TransactionStatus.FAILED,
                "DECLINED": const.TransactionStatus.FAILED,
            }[response["payout_data"]["status"]],
            raw_response=response,
            id_in_payment_system=response["payout_data"]["id"],
            decline_code=response["payout_data"].get("decline_code"),
            decline_reason=response["payout_data"].get("decline_reason"),
        )

    def _get_withdraw_request(self) -> dict[str, ty.Any]:
        return {
            "request": {
                "id": str(self.trx.uuid),
                "time": timezone.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            "merchant_order": {
                "id": str(self.trx.uuid),
            },
            "payment_method": self.payment_method,
            "payout_data": {
                "amount": str(self.trx.amount),
                "currency": self.trx.currency,
            },
            "customer": {
                "locale": self._customer.language,
                "email": self._email,
                "id": str(self._customer.uuid),
            },
        }

    def deposit(self) -> entities.PaymentClientDepositResponse:
        payment_request = {
            "request": {
                "id": str(self.trx.uuid),
                "time": timezone.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            "merchant_order": {
                "id": str(self.trx.uuid),
                "description": f"Order {self.trx.uuid}",
            },
            "payment_data": {
                "amount": str(self.trx.amount),
                "currency": self.trx.currency,
            },
            "return_urls": {
                "return_url": self.trx.redirect_url,
            },
            "payment_method": self.payment_method,
            "customer": {
                "locale": self._customer.language,
                "email": self._email,
                "id": str(self._customer.uuid),
            },
        }

        payment_request = self._enrich_payment_request(payment_request)

        response = self._make_request(
            url="/api/payments",
            method="POST",
            data=payment_request,
        )
        if response["http_status_code"] == 400:
            return entities.PaymentClientDepositResponse(
                status=const.TransactionStatus.FAILED,
                raw_response=response,
                decline_code=response["name"],
                decline_reason=response["message"],
            )

        if response.get("payment_data", {}).get("status") == "DECLINED":
            return entities.PaymentClientDepositResponse(
                status=const.TransactionStatus.FAILED,
                raw_response=response,
                decline_code=response["payment_data"].get("decline_code"),
                decline_reason=response["payment_data"].get("decline_reason"),
            )

        assert response["http_status_code"] == 200, response
        return entities.PaymentClientDepositResponse(
            status=const.TransactionStatus.PENDING,
            raw_response=response,
            id_in_payment_system=response.get("payment_data", {}).get("id"),
            customer_redirect_form_data=entities.TransactionExtraFormData(
                action_url=response["redirect_url"],
                method="get",
            )
            if "redirect_url" in response
            else None,
        )

    def _enrich_payment_request(self, req: dict[str, ty.Any]) -> dict[str, ty.Any]:
        return req

    def _get_pay_status(self) -> entities.RemoteTransactionStatus:
        assert self.trx.type == const.TransactionType.DEPOSIT

        dt = (self.trx.created_at - timedelta(hours=1)).astimezone(pytz.utc)
        start_dt = (
            dt.strftime("%Y-%m-%dT%H:%M:%S") + ".%03d" % (dt.microsecond / 1000) + "Z"
        )
        response = self._make_request(
            url=f"/api/payments/?request_id={uuid4()}&merchant_order_id={self.trx.uuid}&start_time={start_dt}",
            method="GET",
            data=None,
        )
        if not response["data"]:
            return entities.RemoteTransactionStatus(
                operation_status=entities.TransactionStatus.FAILED,
                raw_data=response,
                decline_code=const.TransactionDeclineCodes.NO_OPERATION_PERFORMED,
            )

        data = response["data"][0]

        remote_amount = None
        if "amount" in data["payment_data"]:
            remote_amount = Money(
                data["payment_data"]["amount"],
                data["payment_data"]["currency"],
            )

        return entities.RemoteTransactionStatus(
            operation_status=CARDPAY_STATUS_MAP[data["payment_data"]["status"]],
            decline_code=data["payment_data"].get("decline_code"),
            decline_reason=data["payment_data"].get("decline_reason"),
            raw_data=response,
            id_in_payment_system=data["payment_data"]["id"],
            remote_amount=remote_amount,
        )

    def _get_payout_status(self) -> entities.RemoteTransactionStatus:
        assert self.trx.type == const.TransactionType.WITHDRAWAL

        dt = (self.trx.created_at - timedelta(hours=1)).astimezone(pytz.utc)
        start_dt = (
            dt.strftime("%Y-%m-%dT%H:%M:%S") + ".%03d" % (dt.microsecond / 1000) + "Z"
        )
        response = self._make_request(
            url=f"/api/payouts/?request_id={uuid4()}&merchant_order_id={self.trx.uuid}&start_time={start_dt}",
            method="GET",
            data=None,
        )
        if not response["data"]:
            return entities.RemoteTransactionStatus(
                operation_status=const.TransactionStatus.FAILED,
                decline_code=const.TransactionDeclineCodes.NO_OPERATION_PERFORMED,
                raw_data=response,
            )

        data = response["data"][0]

        remote_amount = None
        if "amount" in data["payout_data"]:
            remote_amount = Money(
                data["payout_data"]["amount"],
                data["payout_data"]["currency"],
            )

        return entities.RemoteTransactionStatus(
            operation_status=CARDPAY_STATUS_MAP[data["payout_data"]["status"]],
            decline_code=data["payout_data"].get("decline_code"),
            decline_reason=data["payout_data"].get("decline_reason"),
            raw_data=response,
            id_in_payment_system=data["payout_data"]["id"],
            remote_amount=remote_amount,
        )

    def _get_transaction_status(self) -> RemoteTransactionStatus:
        if self.trx.type == const.TransactionType.WITHDRAWAL:
            return self._get_payout_status()
        elif self.trx.type == const.TransactionType.DEPOSIT:
            return self._get_pay_status()
        raise RuntimeError(f"Unknown transaction type: {self.trx.type}")

    @cached_property
    def host(self) -> str:
        return (
            "https://cardpay.com"
            if settings.IS_PRODUCTION
            else "https://sandbox.cardpay.com"
        )

    def _make_request(
        self,
        url: str,
        method: str,
        data: dict[str, ty.Any] | None,
    ) -> dict[str, ty.Any]:
        headers = self._get_common_headers()

        response = self.session.request(
            method=method,
            url=self.host + url,
            json=data,
            headers=headers,
        )
        return {
            **response.json(),
            "http_status_code": response.status_code,
        }

    def _get_common_headers(self) -> dict[str, str]:
        access_token_from_redis = self._get_access_token()
        return {
            "Authorization": f"Bearer {access_token_from_redis}",
            "Content-Type": "application/json",
        }

    def _get_access_token(self) -> str:
        redis_credentials_key = cache.CacheKey(
            f"credentials2:cardpay_api_v3:{self.creds.terminal_code}"
        )

        access_token_cached = cache.redis_cache_get(redis_credentials_key, str)
        if access_token_cached:
            return access_token_cached

        access_token_data = self._oauth_get_new_tokens()
        ttl = access_token_data["expires_in"]
        access_token = access_token_data["access_token"]
        cache.redis_cache_set(
            redis_credentials_key, access_token, ttl=timedelta(seconds=ttl - 30)
        )
        return access_token

    def _oauth_get_new_tokens(self) -> dict[str, ty.Any]:
        response = None

        for i in range(10):
            response = self.session.post(
                url=f"{self.host}/api/auth/token",
                headers={
                    "content-type": "application/x-www-form-urlencoded",
                    "cache-control": "no-cache",
                },
                data={
                    "grant_type": "password",
                    "terminal_code": self.creds.terminal_code,
                    "password": self.creds.terminal_password.get_secret_value(),
                },
            )
            if response.status_code == 520:
                logger.warning("got 520 error, retrying")
                time.sleep(i + 1)
                continue
            else:
                break

        assert response
        tokens = response.json()
        assert tokens["expires_in"] >= 60, tokens
        assert tokens["refresh_expires_in"] >= 60, tokens

        tokens["updated_at"] = int(timezone.now().timestamp())
        return tokens
