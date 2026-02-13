import logging
from typing import cast
from uuid import UUID

import xmltodict
from django.db import transaction
from django.shortcuts import redirect
from rest_framework.request import Request
from rest_framework.response import Response
from rozert_pay.common import const
from rozert_pay.payment import tasks, types
from rozert_pay.payment.models import IncomingCallback, PaymentTransaction
from rozert_pay.payment.services import db_services, deposit_services
from rozert_pay.payment.systems import base_controller
from rozert_pay.payment.systems.worldpay.worldpay_client import (
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
        self,
        trx_id: types.TransactionId,
        client: WorldpaySandboxClient | WorldpayClient,
    ) -> None:
        with deposit_services.initiate_deposit(
            client=client,
            trx_id=types.TransactionId(trx_id),
            controller=self,
            allow_immediate_fail=True,
        ):
            pass

    # def _run_withdraw(
    #     self, trx: PaymentTransaction, client: WorldpaySandboxClient | WorldpayClient
    # ) -> None:
    #     with withdraw_services.execute_withdraw_query_and_schedule_status_checks(
    #         trx=trx,
    #         controller=self,
    #     ):
    #         pass

    def _parse_callback(self, cb: IncomingCallback) -> Response:
        parsed_data = xmltodict.parse(cb.body)
        transaction_uuid_hex = parsed_data["paymentService"]["notify"][
            "orderStatusEvent"
        ]["@orderCode"]
        trx = db_services.get_transaction(
            id_in_payment_system=transaction_uuid_hex,
            for_update=False,
            system_type=const.PaymentSystemType.WORLDPAY,
        )
        tasks.check_status.delay(transaction_id=trx.id)
        return Response(str("[OK]"))

    def handle_redirect(
        self,
        request: Request,
    ) -> Response:
        logger.info(
            "Handle Worldpay redirect",
            extra={
                "request_query_params": request.query_params,
                "request_payload": request.POST,
            },
        )
        transaction_id = request.query_params["transaction_id"]

        with transaction.atomic():
            trx: PaymentTransaction = db_services.get_transaction(
                trx_uuid=UUID(transaction_id),
                for_update=False
            )

        self.create_log(
            trx_id=trx.id,
            event_type=const.EventType.CUSTOMER_REDIRECT_RECEIVED,
            description="Customer redirect received",
            extra={
                "request_payload": request.POST,
                "trx_uuid": trx.uuid,
            },
        )

        self.run_deposit_finalization(trx_id=trx.id)
        assert trx.redirect_url
        return cast(Response, redirect(trx.redirect_url))

    def _is_callback_signature_valid(self, _: IncomingCallback) -> bool:
        return True

    def build_callback_response(self, cb: IncomingCallback) -> Response:
        return Response(str("[OK]"))


worldpay_controller = WorldpayController(
    payment_system=const.PaymentSystemType.WORLDPAY,
    default_credentials={
        "base_url": "https://salam.worldpay.com",
        "username": "fake_username",
        "password": "fake_password",
        "merchant_code": "fake_merchant_code",
        # 3DS Flex JWT credentials
        "jwt_issuer": "fake_jwt_issuer",
        "jwt_org_unit_id": "fake_jwt_org_unit_id",
        "jwt_mac_key": "fake_jwt_mac_key",
    },
)
