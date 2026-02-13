import json
import logging
from decimal import Decimal
from typing import cast

from bm.datatypes import Money
from django.db import transaction
from django.http import HttpResponse, QueryDict
from django.shortcuts import redirect
from rest_framework.request import Request
from rest_framework.response import Response
from rozert_pay.common import const
from rozert_pay.payment import entities, types
from rozert_pay.payment.entities import RemoteTransactionStatus
from rozert_pay.payment.models import IncomingCallback, PaymentTransaction
from rozert_pay.payment.services import (
    deposit_services,
    transaction_processing,
    withdraw_services,
)
from rozert_pay.payment.systems import base_controller
from rozert_pay.payment.systems.appex.appex_client import (
    AppexClient,
    AppexCreds,
    AppexSandboxClient,
)
from rozert_pay.payment.systems.appex.appex_const import APPEX_FOREIGN_MD, APPEX_PARES

logger = logging.getLogger(__name__)


class AppexController(
    base_controller.PaymentSystemController[AppexClient, AppexSandboxClient]
):
    client_cls = AppexClient
    sandbox_client_cls = AppexSandboxClient

    def _run_deposit(
        self, trx_id: types.TransactionId, client: AppexSandboxClient | AppexClient
    ) -> None:
        with deposit_services.initiate_deposit(
            client=client,
            trx_id=types.TransactionId(trx_id),
            controller=self,
            allow_immediate_fail=True,
        ):
            pass

    def _run_withdraw(
        self, trx: PaymentTransaction, client: AppexSandboxClient | AppexClient
    ) -> None:
        with withdraw_services.execute_withdraw_query_and_schedule_status_checks(
            trx=trx,
            controller=self,
        ):
            pass

    def _parse_callback(self, cb: IncomingCallback) -> RemoteTransactionStatus:
        data = QueryDict(cb.body)
        is_success_notification = (
            "payamount" in data and "percentplus" in data and "percentminus" in data
        )
        is_pares = "PaRes" in data and "MD" in data
        is_deposit_confirmation = data.get("opertype") == "pay"
        is_withdraw_confirmation = bool(data.get("operator"))
        id_in_payment_system = data.get("transID")

        remote_status = data.get("status")
        is_additional_withdraw_callback = (
            not is_success_notification
            and not is_pares
            and not is_deposit_confirmation
            and not is_withdraw_confirmation
        ) and remote_status in ("OK", "error")

        conditions = [
            is_success_notification,
            is_pares,
            is_deposit_confirmation,
            is_withdraw_confirmation,
            is_additional_withdraw_callback,
        ]
        assert sum(conditions) == 1, (
            f"bad invariant! " f'{", ".join(map(str, conditions))} ' f"{data}"
        )

        remote_amount = None

        if data.get("opertype") == "chargeback":
            assert data["trtype"] == "1"
            assert "payamount" in data

            trx = PaymentTransaction.objects.get(uuid=data.get("number"))

            return entities.RemoteTransactionStatus(
                operation_status=const.TransactionStatus.CHARGED_BACK,
                id_in_payment_system=id_in_payment_system,
                raw_data=data,
                transaction_id=trx.id,
                decline_code=f"Chargeback: {data['description']}",
            )

        if data.get("opertype") == "chargeback_reversal":
            trx = PaymentTransaction.objects.get(uuid=data.get("number"))

            return entities.RemoteTransactionStatus(
                operation_status=const.TransactionStatus.CHARGED_BACK_REVERSAL,
                id_in_payment_system=id_in_payment_system,
                raw_data=data,
                transaction_id=trx.id,
            )

        if is_success_notification:
            assert "opertype" not in data, f"bad payload: {data}"
            assert "PAN" in data, f"bad payload: {data}"

            # successful deposit
            status = const.TransactionStatus.SUCCESS
            remote_amount = Money(Decimal(data["amount"]), data["amountcurr"])
        elif is_deposit_confirmation:
            assert id_in_payment_system, f"bad payload {data}"
            status = const.TransactionStatus.PENDING

        elif is_pares:
            # TODO: add index on foreign_md for appex
            trx = PaymentTransaction.objects.get(
                extra__appex_foreign_md=str(data["MD"]),
            )
            return entities.RemoteTransactionStatus(
                operation_status=const.TransactionStatus.PENDING,
                id_in_payment_system=trx.id_in_payment_system,
                raw_data=data,
                transaction_id=trx.id,
            )

        elif is_withdraw_confirmation:
            status = const.TransactionStatus.PENDING

        elif is_additional_withdraw_callback:
            trx = PaymentTransaction.objects.get(uuid=data.get("number"))
            return entities.RemoteTransactionStatus(
                operation_status=(
                    const.TransactionStatus.SUCCESS
                    if remote_status == "OK"
                    else const.TransactionStatus(trx.status)
                ),
                id_in_payment_system=trx.id_in_payment_system,
                raw_data=data,
                decline_code=trx.decline_code,
                decline_reason=trx.decline_reason,
                remote_amount=remote_amount,
                transaction_id=trx.id,
            )
        else:
            raise RuntimeError(f"Unknown callback format! {data}")

        trx = PaymentTransaction.objects.get(uuid=data.get("number"))
        return entities.RemoteTransactionStatus(
            operation_status=status,
            id_in_payment_system=id_in_payment_system,
            raw_data=data,
            remote_amount=remote_amount,
            transaction_id=trx.id,
        )

    def _is_callback_signature_valid(self, cb: IncomingCallback) -> bool:
        if "json" in cb.headers.get("content-type", ""):
            data = json.loads(cb.body)
        else:
            data = QueryDict(cb.body, mutable=True)

        if "MD" in data and "PaRes" in data:
            # no signature check for PaRes 3d response
            return True

        signature_from_request = data["signature"]
        force_fields = None

        if data.get("percentplus"):
            # deposit success confirmation
            signature_keys = (
                "amount, amountcurr, currency, number, description, "
                "trtype, payamount, percentplus, percentminus, account, "
                "paytoken, backURL, transID, datetime".split(", ")
            )
        elif data.get("operator"):
            # withdraw confirmation
            signature_keys = (
                "account, operator, params, amount, "
                "amountcurr, number, transID, datetime".split(", ")
            )
        elif data.get("opertype") == "pay":
            # deposit confirmation
            signature_keys = (
                "PANmasked, cardholder, opertype, amount, amountcurr, "
                "number, description, trtype, account, cf1, cf2, cf3, "
                "paytoken, backURL, transID, datetime".split(", ")
            )
            force_fields = ["cardholder"]
        elif data.get("status") in ("OK", "error"):
            signature_keys = (
                "account, amount, amountcurr, number, transID, datetime, status".split(
                    ", "
                )
            )
        else:
            raise RuntimeError(f"Unknown format for signature validation! {data}")

        def signature_for_creds_callable(creds: AppexCreds) -> str:
            return self.client_cls._sign_payload(
                payload=data,
                fields_to_sign=signature_keys,
                secret1=creds.secret1,
                secret2=creds.secret2,
                force_fields=force_fields,
            )

        return transaction_processing.validate_signature_for_callback(
            payment_system=self.payment_system,
            creds_cls=AppexCreds,
            signature_from_request=signature_from_request,
            signature_for_creds_callable=signature_for_creds_callable,
        )

    def handle_redirect(
        self,
        request: Request,
    ) -> Response:
        transaction_id = request.query_params["transaction_id"]

        with transaction.atomic():
            trx: PaymentTransaction = (
                PaymentTransaction.objects.select_for_update().get(uuid=transaction_id)
            )
            if trx.extra.get(APPEX_PARES):
                # Appex fails transaction in case we send duplicate deposit finalize.
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

    def build_callback_response(self, cb: IncomingCallback) -> HttpResponse:
        data = QueryDict(cb.body)
        assert cb.transaction_id

        is_operation_confirmation = data.get("opertype") == "pay"
        if is_operation_confirmation:
            assert cb.transaction
            assert cb.transaction.id_in_payment_system
            return HttpResponse(str(cb.transaction.id_in_payment_system))

        if cb.transaction and cb.transaction.type == const.TransactionType.WITHDRAWAL:
            return HttpResponse("OK")

        return super().build_callback_response(cb)


appex_controller = AppexController(
    payment_system=const.PaymentSystemType.APPEX,
    default_credentials={
        "account": "fake_account",
        "secret1": "fake_secret1",
        "secret2": "fake",
        "host": "http://appex",
        "operator": None,
    },
)
