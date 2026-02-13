import json
from typing import Any

from bm.datatypes import Money
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from rozert_pay.common import const
from rozert_pay.payment.entities import RemoteTransactionStatus
from rozert_pay.payment.models import IncomingCallback
from rozert_pay.payment.services import (
    db_services,
    deposit_services,
    transaction_processing,
)
from rozert_pay.payment.systems.base_controller import PaymentSystemController
from rozert_pay.payment.systems.stp_codi.client import (
    StpCodiClient,
    StpCodiSandboxClient,
)
from rozert_pay.payment.systems.stp_codi.entities import StpCodiDepositType
from rozert_pay.payment.systems.stp_codi.models import StpCodiUniqueIds
from rozert_pay.payment.systems.stp_codi.views import StpCodiSerializer


class StpCodiController(PaymentSystemController[StpCodiClient, StpCodiSandboxClient]):
    client_cls = StpCodiClient
    sandbox_client_cls = StpCodiSandboxClient

    def _run_deposit(
        self, trx_id: int, client: StpCodiClient | StpCodiSandboxClient
    ) -> None:
        trx = db_services.get_transaction(trx_id=trx_id, for_update=False)
        stp_codi_type = StpCodiSerializer.get_stp_codi_type(trx)

        qr_code_payload = None
        if stp_codi_type == StpCodiDepositType.APP:
            resp = client.deposit_app()
        elif stp_codi_type == StpCodiDepositType.QR_CODE:
            resp = client.deposit_qr_code()
            payload: str = json.dumps(resp.raw_response)
            qr_code_payload = payload
        else:
            raise RuntimeError

        with transaction.atomic():
            trx = db_services.get_transaction(trx_id=trx_id, for_update=True)

            if resp.status == const.TransactionStatus.FAILED:
                assert resp.decline_code
                return self.fail_transaction(
                    trx,
                    decline_code=resp.decline_code,
                    decline_reason=resp.decline_reason,
                )

            assert resp.status == const.TransactionStatus.PENDING

            if qr_code_payload:
                deposit_services.create_deposit_instruction(
                    trx=trx,
                    type=const.InstructionType.INSTRUCTION_QR_CODE,
                    qr_code_payload=qr_code_payload,
                )

            # TODO: generic logic for assert and saving
            # TODO: check id_in_payment_system for stp codi on prod
            # assert resp.id_in_payment_system
            if resp.id_in_payment_system:
                trx.id_in_payment_system = resp.id_in_payment_system
                trx.save(update_fields=["id_in_payment_system", "updated_at"])

            # After deposit PS sends notification to user by phone.
            # When user pays, we receive callback.
            transaction_processing.schedule_periodic_status_checks(trx)

    def _parse_callback(self, cb: IncomingCallback) -> RemoteTransactionStatus:
        payload: dict[str, Any] = json.loads(cb.body)

        # Not QR transaction
        try:
            trx = db_services.get_transaction(
                id_in_payment_system=payload["id"],
                for_update=False,
                system_type=const.PaymentSystemType.STP_CODI,
            )
        except ObjectDoesNotExist:
            # QR transaction
            trx = StpCodiUniqueIds.objects.get(id=payload["id"]).transaction

        return RemoteTransactionStatus(
            operation_status={
                "Success": const.TransactionStatus.SUCCESS,
                "Decline": const.TransactionStatus.FAILED,
                "Cancel": const.TransactionStatus.FAILED,
            }[payload["estado"]],
            id_in_payment_system=str(payload["id"]),
            raw_data=payload,
            transaction_id=trx.id,
            decline_code=payload.get("causaDevolucion"),
            decline_reason=payload.get("causaDevolucion"),
            remote_amount=Money(trx.amount, trx.currency),
        )

    def _is_callback_signature_valid(self, cb: IncomingCallback) -> bool:
        # TODO
        return True


stp_codi_controller = StpCodiController(
    payment_system=const.PaymentSystemType.STP_CODI,
    default_credentials={
        "base_url": "https://sandbox-api.stpmex.com",
        "tipo_cuenta_beneficiario2": 40,
        "cuenta_beneficiario2": "Reinvent MxLatam",
        "qrcode_nombre_beneficiario2": "test",
        "nombre_beneficiario2": "646180301503000001",
        "empresa": "BETMASTER_MX",
        "private_key_password": "",
        "private_key": "",
    },
    bypass_amount_validation_for=[const.TransactionType.DEPOSIT],
)
