import typing as ty

from pydantic import ConfigDict
from rozert_pay.common import const
from rozert_pay.payment import models
from rozert_pay.payment.services import base_classes, errors
from rozert_pay.payment.systems.cardpay_systems.base_client import (
    CardpayCreds,
    _BaseCardpayClient,
)
from waffle import switch_is_active


class CardpayApplepayCreds(CardpayCreds):
    model_config = ConfigDict(extra="allow")

    applepay_key: str
    applepay_certificate: str


class CardpayApplepayClient(_BaseCardpayClient):
    payment_method = "APPLEPAY"
    credentials_cls = CardpayApplepayCreds  # type: ignore[assignment]

    def _get_last_successful_deposit_payment_id(self) -> str:
        payment_id = (
            models.PaymentTransaction.objects.filter(
                wallet=self.trx.wallet,
                customer=self._customer,
                system_type=const.PaymentSystemType.CARDPAY_APPLEPAY,
                type=const.TransactionType.DEPOSIT,
                status=const.TransactionStatus.SUCCESS,
                id_in_payment_system__isnull=False,
            )
            .order_by("-created_at")
            .values_list("id_in_payment_system", flat=True)
            .first()
        )
        if not payment_id:
            raise errors.SafeFlowInterruptionError(
                "No successful cardpay_applepay deposit found for customer"
            )
        return str(payment_id)

    def _get_withdraw_request(self) -> dict[str, ty.Any]:
        request = super()._get_withdraw_request()
        request["payout_data"]["encrypted_data"] = self.trx.extra["encrypted_data"]
        request["payment_data"] = {"id": self._get_last_successful_deposit_payment_id()}
        bankcard_switch = switch_is_active(const.CARDPAY_APPLEPAY_BANKCARD_SWITCH)
        if bankcard_switch:
            request["payment_method"] = "BANKCARD"
            user_data = self.trx.user_data
            if not user_data:
                raise errors.SafeFlowInterruptionError("No user data")
            request["card_account"] = {"recipient_info": user_data.full_name}
        return request

    def _enrich_payment_request(self, req: dict[str, ty.Any]) -> dict[str, ty.Any]:
        req["payment_data"]["encrypted_data"] = self.trx.extra["encrypted_data"]
        return req


class SandboxCardpayApplepayClient(
    base_classes.BaseSandboxClientMixin[CardpayCreds], CardpayApplepayClient
):
    pass
