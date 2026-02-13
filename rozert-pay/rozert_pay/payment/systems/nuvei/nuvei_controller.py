import base64
import hashlib
import json
import logging
from typing import Any, cast
from urllib.parse import parse_qsl
from uuid import UUID

from bm.datatypes import Money
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils.http import urlencode
from rest_framework.request import Request
from rest_framework.response import Response
from rozert_pay.common import const
from rozert_pay.common.const import TransactionExtraFields
from rozert_pay.payment import entities, types
from rozert_pay.payment.models import IncomingCallback, PaymentTransaction
from rozert_pay.payment.services import (
    db_services,
    deposit_services,
    event_logs,
    transaction_processing,
    withdraw_services,
)
from rozert_pay.payment.systems import base_controller
from rozert_pay.payment.systems.nuvei import nuvei_const
from rozert_pay.payment.systems.nuvei.nuvei_client import (
    NuveiClient,
    NuveiCredentials,
    NuveiSandboxClient,
)

logger = logging.getLogger(__name__)


def _parse_cres(cres: str) -> dict[str, Any]:
    for candidate in [cres, f"{cres}=="]:
        try:
            return json.loads(base64.standard_b64decode(candidate).decode())
        except Exception as e:
            logger.exception("error decoding cres")
            exc = e

    raise exc


class NuveiController(
    base_controller.PaymentSystemController[NuveiClient, NuveiSandboxClient]
):
    client_cls = NuveiClient
    sandbox_client_cls = NuveiSandboxClient

    def _run_deposit(
        self, trx_id: types.TransactionId, client: NuveiSandboxClient | NuveiClient
    ) -> None:
        with deposit_services.initiate_deposit(
            client=client,
            trx_id=trx_id,
            controller=self,
        ):
            pass

    def _run_withdraw(
        self, trx: PaymentTransaction, client: NuveiSandboxClient | NuveiClient
    ) -> None:
        with withdraw_services.execute_withdraw_query_and_schedule_status_checks(
            trx=trx,
            controller=self,
        ):
            pass

    def _on_deposit_finalization_response_received(
        self,
        response: entities.PaymentClientDepositFinalizeResponse,
        locked_trx: "db_services.LockedTransaction",
    ) -> None:
        if response.status != const.TransactionStatus.SUCCESS:
            return

        final_transaction_id = response.raw_response.get("transactionId")
        if not final_transaction_id:
            return

        if locked_trx.id_in_payment_system == final_transaction_id:
            return

        known_ids = locked_trx.extra.get(
            nuvei_const.TRX_EXTRA_FIELD_THREEDS_TRANSACTION_IDS
        )
        if not isinstance(known_ids, list):
            known_ids = []

        if (
            locked_trx.id_in_payment_system
            and locked_trx.id_in_payment_system not in known_ids
        ):
            known_ids.append(locked_trx.id_in_payment_system)

        if final_transaction_id not in known_ids:
            known_ids.append(final_transaction_id)

        db_services.save_extra_field(
            locked_trx, nuvei_const.TRX_EXTRA_FIELD_THREEDS_TRANSACTION_IDS, known_ids
        )

        locked_trx.id_in_payment_system = final_transaction_id
        locked_trx.save(update_fields=["id_in_payment_system", "extra", "updated_at"])

    def _parse_callback(
        self, cb: IncomingCallback
    ) -> entities.RemoteTransactionStatus | Response:
        payload = self._parse_callback_payload(cb)
        if not payload:
            raise RuntimeError("Empty Nuvei callback payload")

        if payload.get("EventType") == "Chargeback":
            return self._parse_chargeback_callback(payload)

        if "wdRequestId" in payload or "wdRequestStatus" in payload:
            return self._parse_withdrawal_callback(payload)

        if "Status" in payload:
            return self._parse_deposit_callback(payload)

        raise RuntimeError(f"Unexpected Nuvei callback payload: {payload}")

    def _is_callback_signature_valid(self, cb: IncomingCallback) -> bool:
        payload = self._parse_callback_payload(cb)
        if "advanceResponseChecksum" in payload:
            signature = payload["advanceResponseChecksum"]

            def signature_for_creds_callable(creds: NuveiCredentials) -> str:
                base_string_for_sign = "{0}{1}{2}{3}{4}{5}".format(
                    payload["totalAmount"],
                    payload["currency"],
                    payload["responseTimeStamp"],
                    payload["PPP_TransactionID"],
                    payload["Status"],
                    payload["productId"],
                )
                base_string_for_sign = base_string_for_sign.replace("+", " ")
                string_for_sign = (
                    creds.secret_key.get_secret_value() + base_string_for_sign
                )
                return hashlib.sha256(string_for_sign.encode()).hexdigest()

        elif "checksum" in payload:
            signature = payload["checksum"]

            def signature_for_creds_callable(creds: NuveiCredentials) -> str:
                string_for_sign = str(cb.body) + creds.secret_key.get_secret_value()
                return hashlib.sha256(string_for_sign.encode()).hexdigest()

        else:
            logger.error(
                "Invalid signature format in Nuvei callback payload",
                extra={"payload": payload},
            )
            raise ValueError("Invalid signature format in Nuvei callback payload")

        return transaction_processing.validate_signature_for_callback(
            payment_system=self.payment_system,
            creds_cls=NuveiCredentials,
            signature_from_request=signature,
            signature_for_creds_callable=signature_for_creds_callable,
        )

    def handle_redirect(self, request: Request) -> Response:
        transaction_id = request.query_params["transaction_id"]
        cres = request.data.get("cres")

        if cres:
            data = _parse_cres(cres)
        else:
            if hasattr(request.data, "dict"):
                data = request.data.dict()
            else:
                data = dict(request.data)

        logger.info("Received redirect from Nuvei", extra={"data": data})

        with transaction.atomic():
            trx = db_services.get_transaction(
                trx_uuid=UUID(transaction_id), for_update=True
            )
            if data:
                trx.extra[TransactionExtraFields.REDIRECT_RECEIVED_DATA] = data
                trx.save(update_fields=["extra", "updated_at"])

            if not data:
                assert trx.redirect_url
                return cast(Response, redirect(trx.redirect_url))

            if data.get("transStatus") != "Y":
                self.fail_transaction(
                    trx=trx,
                    decline_code=data.get("errorCode")
                    or const.TransactionDeclineCodes.USER_HAS_NOT_FINISHED_FLOW,
                    decline_reason=data.get(
                        "errorDescription", "User did not pass 3DS challenge"
                    ),
                )
                assert trx.redirect_url
                return cast(Response, redirect(trx.redirect_url))

        event_logs.create_transaction_log(
            trx_id=trx.id,
            event_type=const.EventType.CUSTOMER_REDIRECT_RECEIVED,
            description="Customer redirect received",
            extra={
                "request": data,
                "trx_uuid": str(trx.uuid),
            },
        )

        self.run_deposit_finalization(trx_id=trx.id)
        assert trx.redirect_url
        return cast(Response, redirect(trx.redirect_url))

    def build_callback_response(self, cb: IncomingCallback) -> HttpResponse:
        raw_data = cb.remote_transaction_status.get("raw_data", {})
        if not raw_data or not raw_data.get("wdRequestState"):
            return HttpResponse("OK")

        request_state = raw_data["wdRequestState"]
        request_status = nuvei_const.WITHDRAW_STATUS_MATCHING[
            raw_data["wdRequestStatus"]
        ]

        if (
            request_state in ("Open", "In Progress")
            and request_status == const.TransactionStatus.PENDING
        ):
            action = "Approve"
        else:
            action = "Decline"

        response_payload = {
            "action": action,
            "merchantUniqueId": str(cb.transaction.uuid)
            if cb.transaction
            else raw_data.get("clientUniqueId"),
        }
        return HttpResponse(urlencode(response_payload))

    def _parse_callback_payload(self, cb: IncomingCallback) -> dict[str, Any]:
        if "application/json" in cb.headers.get("content-type", ""):
            return cast(dict[str, Any], json.loads(cb.body))
        return dict(parse_qsl(cb.body, keep_blank_values=True))

    def _parse_deposit_callback(
        self, payload: dict[str, Any]
    ) -> entities.RemoteTransactionStatus:
        transaction_uuid = payload.get("clientUniqueId")
        if not transaction_uuid:
            raise RuntimeError(f"Missing clientUniqueId in payload: {payload}")

        trx = PaymentTransaction.objects.get(uuid=transaction_uuid)
        mapping_of_statuses = {
            "PENDING": const.TransactionStatus.PENDING,
            "DECLINED": const.TransactionStatus.FAILED,
            "ERROR": const.TransactionStatus.FAILED,
            "APPROVED": const.TransactionStatus.SUCCESS,
        }
        return entities.RemoteTransactionStatus(
            operation_status=mapping_of_statuses[payload["Status"]],
            transaction_id=trx.id,
            id_in_payment_system=self._get_callback_id_in_payment_system(payload, trx),
            raw_data=payload,
            decline_code=payload.get("ReasonCode"),
            decline_reason=payload.get("Reason"),
            remote_amount=Money(payload["totalAmount"], payload["currency"])
            if "totalAmount" in payload
            else None,
        )

    def _parse_withdrawal_callback(
        self, payload: dict[str, Any]
    ) -> entities.RemoteTransactionStatus:
        transaction_uuid = payload.get("clientUniqueId")
        if not transaction_uuid:
            raise RuntimeError(f"Missing clientUniqueId in payload: {payload}")

        trx = PaymentTransaction.objects.get(uuid=transaction_uuid)
        return entities.RemoteTransactionStatus(
            operation_status=nuvei_const.WITHDRAW_STATUS_MATCHING[
                payload["wdRequestStatus"]
            ],
            transaction_id=trx.id,
            id_in_payment_system=self._get_callback_id_in_payment_system(payload, trx),
            raw_data=payload,
            decline_code=payload.get("gwReasonCode") or payload.get("gwErrCode"),
            decline_reason=payload.get("gwReason"),
            remote_amount=Money(payload["wd_amount"], payload["wd_currency"])
            if "wd_amount" in payload
            else None,
        )

    def _parse_chargeback_callback(
        self, payload: dict[str, Any]
    ) -> entities.RemoteTransactionStatus:
        chargeback_entity = payload["Chargeback"]
        if chargeback_entity.get("Type") != "Chargeback":
            raise RuntimeError(f"Unexpected chargeback payload: {payload}")

        trx_uuid = payload["TransactionDetails"]["ClientUniqueId"]
        trx = PaymentTransaction.objects.get(uuid=trx_uuid)
        return entities.RemoteTransactionStatus(
            operation_status=const.TransactionStatus.CHARGED_BACK,
            transaction_id=trx.id,
            id_in_payment_system=self._get_callback_id_in_payment_system(payload, trx),
            raw_data=payload,
            remote_amount=Money(
                chargeback_entity["ReportedAmount"],
                chargeback_entity["ReportedCurrency"],
            ),
        )

    @staticmethod
    def _get_callback_id_in_payment_system(
        payload: dict[str, Any], trx: PaymentTransaction
    ) -> str | None:
        return (
            trx.id_in_payment_system
            or payload.get("TransactionID")
            or payload.get("PPP_TransactionID")
            or payload.get("transactionId")
        )


nuvei_controller = NuveiController(
    payment_system=const.PaymentSystemType.NUVEI,
    default_credentials={
        "merchant_id": "fake",
        "merchant_site_id": "fake",
        "base_url": "http://fake",
        "secret_key": "fake",
    },
)
