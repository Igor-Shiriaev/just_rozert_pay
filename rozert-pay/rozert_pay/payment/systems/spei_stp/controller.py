import json
import logging
from decimal import Decimal
from typing import Optional

from bm.datatypes import Money
from currency.const import MXN
from rest_framework.response import Response
from rozert_pay.common import const
from rozert_pay.common.helpers.db_searching_utils import filter_by_uuid_prefix
from rozert_pay.payment import entities
from rozert_pay.payment.entities import RemoteTransactionStatus
from rozert_pay.payment.extra_fields import wallet_extra_fields
from rozert_pay.payment.models import IncomingCallback, PaymentTransaction
from rozert_pay.payment.services import (
    errors,
    transactions_created_on_callback,
    withdraw_services,
)
from rozert_pay.payment.systems import base_controller
from rozert_pay.payment.systems.spei_stp import spei_stp_helpers
from rozert_pay.payment.systems.spei_stp.spei_stp_client import (
    SpeiStpClient,
    SpeiStpSandboxClient,
)

logger = logging.getLogger(__name__)


class SpeiPaymentSystemController(
    base_controller.PaymentSystemController[SpeiStpClient, SpeiStpSandboxClient]
):
    client_cls = SpeiStpClient
    sandbox_client_cls = SpeiStpSandboxClient

    def on_db_transaction_created_via_api(self, trx: PaymentTransaction) -> None:
        """
        Transaction is created on callback in final status, no additional actions required.
        """
        if trx.type == const.TransactionType.DEPOSIT:
            return
        super().on_db_transaction_created_via_api(trx)

    def _parse_callback(
        self, cb: IncomingCallback
    ) -> RemoteTransactionStatus | Response:
        payload = json.loads(cb.body)

        try:
            return self._parse_spei_callback(payload)
        except spei_stp_helpers.SpeiStpTransactionAlreadyExist:
            return Response({"message": "recibido"})
        except spei_stp_helpers.SpeiCallbackError as e:
            resp = Response(e.to_payload())
            resp.status_code = 400
            logger.warning(
                "unaccepted spei stp callback",
                extra={
                    "_error": e,
                    "_response": e.to_payload(),
                },
                exc_info=True,
            )
            return resp
        except Exception as e:
            if isinstance(e, PaymentTransaction.DoesNotExist):
                logger.warning(
                    "spei stp callback for unknown transaction",
                    extra={
                        "_error": e,
                    },
                    exc_info=True,
                )
            else:
                logger.exception(
                    "spei stp callback error",
                    extra={
                        "_error": e,
                    },
                )
            response = spei_stp_helpers.SpeiCallbackError(
                id=2,
                message="Error during callback processing",
            ).to_payload()
            logger.warning(
                "response to spei stp",
                extra={
                    "_response": response,
                },
            )
            return Response(response, status=400)

    def _parse_spei_callback(
        self, payload: dict[str, str]
    ) -> RemoteTransactionStatus | Response:
        if "cuentaBeneficiario" in payload:
            # deposit callback

            remote_amount = Money(payload["monto"], "MXN")
            decline_code: Optional[str]
            # NOTE: feature currently disabled
            # deposit_min_mxn = _get_deposit_min_mxn()
            # if remote_amount.value < deposit_min_mxn:
            #     operation_status = entities.TransactionStatus.DECLINED
            #     decline_code = 'amount_less_than_debit_threshold'
            # else:
            operation_status = entities.TransactionStatus.SUCCESS
            decline_code = None

            # For deposit callbacks then can send id which collides with payout ids.
            # So for deposits construct complex id_in_payment_system to keep uniqueness.
            id_in_payment_system = spei_stp_helpers.spei_deposit_id_in_payment_system(
                payload
            )
            if (
                trx := PaymentTransaction.objects.for_system(
                    const.PaymentSystemType.STP_SPEI,
                )
                .filter(
                    id_in_payment_system=id_in_payment_system,
                    type=const.TransactionType.DEPOSIT,
                )
                .first()
            ):
                logger.warning(
                    "spei transaction already exists",
                    extra={
                        "transaction": trx,
                        "payload": payload,
                    },
                )
            else:
                with transactions_created_on_callback.process_transaction_creation_on_callback(
                    deposit_instruction_account_number=payload["cuentaBeneficiario"],
                    deposited_from_account_number=payload["cuentaOrdenante"],
                    system_type=const.PaymentSystemType.STP_SPEI,
                    controller=self,
                    amount=Money(Decimal(payload["monto"]), MXN),
                    id_in_payment_system=id_in_payment_system,
                ) as err_or_trx:
                    if isinstance(err_or_trx, errors.Error):
                        return Response(
                            {"id": 2, "message": err_or_trx.message}, status=400
                        )

                    trx = err_or_trx
                    trx.extra["id"] = payload["id"]
                    trx.extra["claveRastreo"] = payload["claveRastreo"]
                    trx.save()

                    institution_ordenante = payload.get("institucionOrdenante")
                    customer_external_account = trx.customer_external_account
                    assert customer_external_account

                    # Save institution_ordenante to customer wallet or check if it is the same
                    if institution_ordenante:
                        if io := customer_external_account.extra.get(
                            wallet_extra_fields.INSTITUTION_ORDENANTE
                        ):
                            assert str(io) == str(
                                institution_ordenante
                            ), f"{io!r} != {institution_ordenante!r}"
                        else:
                            customer_external_account.extra[
                                wallet_extra_fields.INSTITUTION_ORDENANTE
                            ] = str(institution_ordenante)
                            customer_external_account.save(
                                update_fields=["extra", "updated_at"]
                            )

            assert trx.type == const.TransactionType.DEPOSIT

            return entities.RemoteTransactionStatus(
                operation_status=operation_status,
                id_in_payment_system=trx.id_in_payment_system,
                raw_data=payload,
                remote_amount=remote_amount,
                decline_code=decline_code,
                transaction_id=trx.id,
            )
        else:
            # payout callback
            qs = PaymentTransaction.objects.for_system(
                const.PaymentSystemType.STP_SPEI,
            )
            fo = payload.get("folioOrigen")
            filtered_by_uuid = filter_by_uuid_prefix(qs, fo) if fo else None
            if isinstance(filtered_by_uuid, errors.Error):
                return Response(
                    {"id": 2, "message": "Invalid deposit account"}, status=400
                )

            if filtered_by_uuid:
                assert len(filtered_by_uuid) == 1, filtered_by_uuid
                trx = filtered_by_uuid[0]
            else:
                try:
                    # Case of payout callback, simple id
                    trx = qs.get(id_in_payment_system=payload["id"])
                except PaymentTransaction.DoesNotExist:
                    # case of deposit callback, claveRastreo:id
                    logger.info(
                        "Trying to find transaction by claveRastreo:id",
                        extra={
                            "payload": payload,
                        },
                    )
                    trx = qs.get(
                        extra__id__iexact=str(payload["id"]),
                    )

            if trx is None:
                raise PaymentTransaction.DoesNotExist()

            return entities.RemoteTransactionStatus(
                operation_status={
                    "Success": entities.TransactionStatus.SUCCESS,
                    "Decline": entities.TransactionStatus.FAILED,
                    "Refund": entities.TransactionStatus.FAILED,
                    "Cancel": entities.TransactionStatus.FAILED,
                }[payload["estado"]],
                id_in_payment_system=str(payload["id"]),
                transaction_id=trx.id,
                raw_data=payload,
                remote_amount=Money(abs(trx.amount), trx.currency),
                decline_code=payload.get("causaDevolucion") or payload.get("estado"),
                decline_reason=payload.get("causaDevolucion"),
            )

    def _is_callback_signature_valid(self, cb: IncomingCallback) -> bool:
        """
        No callback signature as we use custom proxy for communication
        """
        return True

    def build_callback_response(self, cb: IncomingCallback) -> Response:
        return Response({"message": "recibido"})

    def _run_withdraw(
        self, trx: PaymentTransaction, client: SpeiStpClient | SpeiStpSandboxClient
    ) -> None:
        with withdraw_services.execute_withdraw_query_and_schedule_status_checks(
            trx=trx,
            controller=self,
            schedule_periodic_checks=False,
        ):
            pass


spei_controller = SpeiPaymentSystemController(
    payment_system=const.PaymentSystemType.STP_SPEI,
    default_credentials={
        "account_number_prefix": "",
        "base_url": "",
        "withdrawal_target_account": "",
        "check_api_base_url": "",
        "private_key": "",
        "private_key_password": "",
    },
)
