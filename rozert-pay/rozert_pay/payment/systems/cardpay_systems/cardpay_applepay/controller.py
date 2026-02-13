from hashlib import sha512

from rest_framework.response import Response
from rozert_pay.common import const
from rozert_pay.payment import types
from rozert_pay.payment.entities import RemoteTransactionStatus
from rozert_pay.payment.models import IncomingCallback, PaymentTransaction
from rozert_pay.payment.services import deposit_services, withdraw_services
from rozert_pay.payment.systems import base_controller
from rozert_pay.payment.systems.cardpay_systems.cardpay_applepay.client import (
    CardpayApplepayClient,
    SandboxCardpayApplepayClient,
)
from rozert_pay.payment.systems.cardpay_systems.services.cardpay_callback_parsing import (
    CardpayCallbackServices,
)
from rozert_pay.payment.types import T_Client, T_SandboxClient


class CardpayController(
    base_controller.PaymentSystemController[
        CardpayApplepayClient, SandboxCardpayApplepayClient
    ]
):
    client_cls = CardpayApplepayClient
    sandbox_client_cls = SandboxCardpayApplepayClient

    def _run_deposit(
        self, trx_id: types.TransactionId, client: T_SandboxClient | T_Client
    ) -> None:
        with deposit_services.initiate_deposit(
            client=client,
            trx_id=trx_id,
            controller=self,
        ):
            pass

    def _parse_callback(
        self, cb: IncomingCallback
    ) -> RemoteTransactionStatus | Response:
        return CardpayCallbackServices.parse_cardpay_callback(cb)

    def _is_callback_signature_valid(self, cb: IncomingCallback) -> bool:
        return CardpayCallbackServices.validate_callback_signature(
            cb=cb,
            payment_system=self.payment_system,
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


cardpay_applepay_controller = CardpayController(
    payment_system=const.PaymentSystemType.CARDPAY_APPLEPAY,
    default_credentials=dict(
        callback_secret="fake",
        terminal_password="fake",
        terminal_code=-1,
        applepay_key="fake",
        applepay_certificate="fake",
    ),
)
