import datetime
import logging
from typing import cast

import xmltodict
from django.db import transaction
from django.http import QueryDict
from django.shortcuts import redirect
from django.utils import timezone
from rest_framework.request import Request
from rest_framework.response import Response
from rozert_pay.common import const
from rozert_pay.payment import entities, types
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
from rozert_pay.payment.systems.appex.appex_const import APPEX_FOREIGN_MD, APPEX_PARES

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
        transaction_id = data["paymentService"]["notify"]["orderStatusEvent"]["@orderCode"]
        client: WorldpayClient | WorldpaySandboxClient = self.client_cls(trx_id=transaction_id)
        remote_transaction_status: entities.RemoteTransactionStatus = client._get_transaction_status()

        return entities.RemoteTransactionStatus(
            operation_status=status,
            id_in_payment_system=id_in_payment_system,
            raw_data=data,
            remote_amount=remote_amount,
            transaction_id=trx.id,
        )

    def _is_callback_signature_valid(self, _: IncomingCallback) -> bool:
        return True

    def handle_redirect(
        self,
        request: Request,
    ) -> Response:
        transaction_id = request.query_params["transaction_id"]
        trx: PaymentTransaction = PaymentTransaction.objects.select_for_update().get(
            uuid=transaction_id
        )
        if trx.extra.get(APPEX_PARES):
            # Worldpay fails transaction in case we send duplicate deposit finalize.
            # So if pares has been already received, don't create second finalization task.
            logger.warning(
                "duplicated appex pares callback",
                extra={
                    "_request": request.POST,
                    "_trx": trx,
                    "_trx_uuid": trx.uuid,
                },
            )
            return Response("OK")

        trx.extra[APPEX_PARES] = request.POST["PaRes"]
        trx.extra[APPEX_FOREIGN_MD] = request.POST["MD"]
        trx.save(update_fields=["extra", "updated_at"])

        self.create_log(
            trx_id=trx.id,
            event_type=const.EventType.CUSTOMER_REDIRECT_RECEIVED,
            description="Customer redirect received",
            extra={
                "request": request.POST,
                "trx_uuid": trx.uuid,
            },
        )

        self.run_deposit_finalization(
            trx_id=trx.id,
        )
        assert trx.redirect_url
        return cast(Response, redirect(trx.redirect_url))

    def build_callback_response(self, cb: IncomingCallback) -> Response:
        data = QueryDict(cb.body)
        assert cb.transaction_id

        is_operation_confirmation = data.get("opertype") == "pay"
        if is_operation_confirmation:
            assert cb.transaction and cb.transaction.id_in_payment_system
            return Response(str(cb.transaction.id_in_payment_system))

        return super().build_callback_response(cb)


appex_controller = WorldpayController(
    payment_system=const.PaymentSystemType.APPEX,
    default_credentials={
        "account": "fake_account",
        "secret1": "fake_secret1",
        "secret2": "fake",
        "host": "http://appex",
        "operator": None,
    },
)
