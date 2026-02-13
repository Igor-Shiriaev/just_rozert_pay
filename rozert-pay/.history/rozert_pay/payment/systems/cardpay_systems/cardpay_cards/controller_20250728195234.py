import json
from decimal import Decimal
from hashlib import sha512

from bm.datatypes import Money
from bm.utils import round_decimal
from rest_framework.response import Response
from rozert_pay.common import const
from rozert_pay.payment import types
from rozert_pay.payment.entities import RemoteTransactionStatus
from rozert_pay.payment.models import IncomingCallback, PaymentTransaction
from rozert_pay.payment.services import (
    deposit_services,
    transaction_processing,
    withdraw_services,
)
from rozert_pay.payment.systems import base_controller
from rozert_pay.payment.systems.cardpay_systems.base_client import (
    CARDPAY_STATUS_MAP,
    CardpayCreds,
)
from rozert_pay.payment.systems.cardpay_systems.cardpay_cards.client import (
    CardpayClient,
    SandboxCardpayClient,
)
from rozert_pay.payment.types import T_Client, T_SandboxClient


class CardpayController(
    base_controller.PaymentSystemController[CardpayClient, SandboxCardpayClient]
):
    client_cls = CardpayClient
    sandbox_client_cls = SandboxCardpayClient

    def _run_deposit(
        self, trx_id: types.TransactionId, client: T_SandboxClient | T_Client
    ) -> None:
        with deposit_services.initiate_deposit(
            client=client,
            trx_id=trx_id,
            controller=self,
            allow_immediate_fail=True,
        ):
            pass

    def _parse_callback(
        self, cb: IncomingCallback
    ) -> RemoteTransactionStatus | Response:
        body = cb.body
        payload = json.loads(body)

        transaction_uuid = payload["merchant_order"]["id"]
        trx = PaymentTransaction.objects.get(uuid=transaction_uuid)

        operation_status = None
        refund_amount = None
        if "payout_data" in payload:
            transaction_data = payload.get("payout_data", {})
            id_in_payment_system = transaction_data["id"]
        elif rd := payload.get("refund_data"):
            assert rd["status"] == "COMPLETED", f"Incorrect payload: {payload}"
            operation_status = const.TransactionStatus.REFUNDED
            transaction_data = rd
            id_in_payment_system = trx.id_in_payment_system
            refund_amount = Money(rd["amount"], rd["currency"])
        else:
            transaction_data = payload.get("payment_data", {})
            id_in_payment_system = transaction_data["id"]

        if operation_status is None:
            operation_status = CARDPAY_STATUS_MAP[transaction_data["status"]]

        # need to round, because they send float
        amount = round_decimal(Decimal(transaction_data["amount"]))
        currency = transaction_data["currency"]

        status = transaction_data["status"]

        if status == "CHARGEBACK_RESOLVED":
            operation_status = const.TransactionStatus.CHARGED_BACK_REVERSAL

        return RemoteTransactionStatus(
            operation_status=operation_status,
            id_in_payment_system=id_in_payment_system,
            raw_data=payload,
            decline_code=transaction_data.get("decline_code"),
            decline_reason=transaction_data.get("decline_reason"),
            remote_amount=Money(amount, currency),
            transaction_id=trx.id,
            refund_amount=refund_amount,
        )

    def _is_callback_signature_valid(self, cb: IncomingCallback) -> bool:
        signature_from_request = cb.headers.get("signature")

        def signature_for_creds_callable(creds: CardpayCreds) -> str:
            return _calc_cardpay_signature(
                cb.body,
                creds.callback_secret.get_secret_value(),
            )

        return transaction_processing.validate_signature_for_callback(
            payment_system=self.payment_system,
            creds_cls=CardpayCreds,
            signature_from_request=signature_from_request,
            signature_for_creds_callable=signature_for_creds_callable,
        )

    def _run_withdraw(
        self, trx: PaymentTransaction, client: T_SandboxClient | T_Client
    ) -> None:
        with withdraw_services.execute_withdraw_query_and_schedule_status_checks(
            trx=trx,
            controller=self,
        ):
            pass


def _calc_cardpay_signature(callback_body: str, callback_secret: str) -> str:
    string_for_sign = str(callback_body) + callback_secret
    return sha512(bytes(string_for_sign, "utf-8")).hexdigest()


cardpay_cards_controller = CardpayController(
    payment_system=const.PaymentSystemType.CARDPAY_CARDS,
    default_credentials=dict(
        callback_secret="fake",
        terminal_password="fake",
        terminal_code=-1,
    ),
)
