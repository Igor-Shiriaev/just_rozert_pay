import datetime
import logging

import xmltodict
from django.db import transaction
from django.utils import timezone
from rest_framework.response import Response
from rozert_pay.common import const
from rozert_pay.payment import types
from rozert_pay.payment.entities import RemoteTransactionStatus
from rozert_pay.payment.models import IncomingCallback, PaymentTransaction
from rozert_pay.payment.services import (
    db_services,
    deposit_services,
    transaction_processing,
)
from rozert_pay.payment.systems import base_controller
from rozert_pay.payment.systems.wordpay.worldpay_client import (
    WorldpayClient,
    WorldpaySandboxClient,
)

logger = logging.getLogger(__name__)


class WorldpayController(
    base_controller.PaymentSystemController[WorldpayClient, WorldpaySandboxClient]
):
    client_cls = WorldpayClient
    sandbox_client_cls = WorldpaySandboxClient

    def _run_deposit(
        self, trx_id: int, client: WorldpaySandboxClient | WorldpayClient
    ) -> None:
        deposit_services.initiate_deposit(
            client=client,
            trx_id=types.TransactionId(trx_id),
        )

    def _run_withdraw(
        self, trx: PaymentTransaction, client: WorldpaySandboxClient | WorldpayClient
    ) -> None:
        self._execute_withdraw_query(trx, client)

        with transaction.atomic():
            transaction_processing.schedule_periodic_status_checks(
                trx=db_services.get_transaction(trx_id=trx.id, for_update=True),
                until=timezone.now()
                + datetime.timedelta(seconds=trx.system.withdrawal_allowed_ttl_seconds),
                schedule_check_immediately=True,
            )

    def _parse_callback(self, cb: IncomingCallback) -> RemoteTransactionStatus:
        data = xmltodict.parse(cb.body)
        transaction_id = data["paymentService"]["notify"]["orderStatusEvent"][
            "@orderCode"
        ]
        client: WorldpayClient | WorldpaySandboxClient = self.client_cls(
            trx_id=transaction_id
        )
        return client._get_transaction_status()

    def _is_callback_signature_valid(self, _: IncomingCallback) -> bool:
        return True

    def build_callback_response(self, cb: IncomingCallback) -> Response:
        return Response(str("[OK]"))


appex_controller = WorldpayController(
    payment_system=const.PaymentSystemType.APPEX,
    default_credentials={
        "base_url": "fake_account",
        "username": "fake_secret1",
        "password": "fake",
        "merchant_code": "http://appex",
        "installation_id": None,
    },
)
