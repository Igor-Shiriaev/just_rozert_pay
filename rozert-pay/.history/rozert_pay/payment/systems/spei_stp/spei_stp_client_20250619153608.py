import datetime
import json
import random
from decimal import Decimal
from typing import Any, Generator

import requests
from bm.datatypes import Money
from rozert_pay.common import const as common_const
from rozert_pay.payment import entities, models
from rozert_pay.payment.entities import RemoteTransactionStatus
from rozert_pay.payment.extra_fields import wallet_extra_fields
from rozert_pay.payment.services import base_classes, event_logs, sandbox_services
from rozert_pay.payment.systems.spei_stp import (
    controller,
    spei_stp_const,
    spei_stp_helpers,
)


class SpeiStpClient(base_classes.BasePaymentClient["spei_stp_helpers.SpeiStpCreds"]):
    credentials_cls = spei_stp_helpers.SpeiStpCreds

    def withdraw(self) -> entities.PaymentClientWithdrawResponse:
        assert self.trx.customer_external_account
        customer_wallet: models.CustomerExternalPaymentSystemAccount = (
            self.trx.customer_external_account
        )

        if not customer_wallet:
            event_logs.create_transaction_log(
                trx_id=self.trx.id,
                event_type=common_const.EventType.INFO,
                description="Can't instantiate payout: customer wallet not found",
                extra={
                    "customer_id": self.trx.customer_id,
                },
            )
            return entities.PaymentClientWithdrawResponse(
                status=entities.TransactionStatus.FAILED,
                decline_code=common_const.TransactionDeclineCodes.SYSTEM_DECLINE,
                decline_reason="cant find institucionOrdenante for wallet",
                raw_response={},
                id_in_payment_system="<error>",
            )

        institution_contraparte = customer_wallet.extra.get(
            wallet_extra_fields.INSTITUTION_ORDENANTE
        )
        if not institution_contraparte:
            event_logs.create_transaction_log(
                trx_id=self.trx.id,
                event_type=common_const.EventType.INFO,
                description="Can't instantiate payout: institution_ordenante not found",
                extra={
                    "customer_id": self.trx.customer_id,
                    "customer_wallet": customer_wallet.id,
                },
            )
            return entities.PaymentClientWithdrawResponse(
                status=entities.TransactionStatus.FAILED,
                decline_code=common_const.TransactionDeclineCodes.SYSTEM_DECLINE,
                decline_reason="cant find institucionOrdenante for wallet",
                raw_response={},
                id_in_payment_system="<error>",
            )

        data = spei_stp_helpers.get_withdraw_payload(
            trx_uuid=self.trx.uuid.hex[:30],
            description=f"Order {self.trx.uuid}",
            target_account=customer_wallet.unique_account_number,
            from_account=self.creds.withdrawal_target_account,
            amount=self.trx.amount,
            institution_contraparte=institution_contraparte,
        )
        data["firma"] = spei_stp_helpers.get_data_signature(
            spei_stp_helpers.sign_payload_for_payout(data), self.creds
        )

        resp = self._send_request(
            url=f"{self.creds.base_url}/speiws/rest/ordenPago/registra",
            data=data,
            method="put",
        )["resultado"]

        resp_id = int(resp["id"])
        is_success = len(str(resp_id)) > 3
        is_error = resp.get("descripcionError") is not None
        if is_error:
            assert not is_success

        return entities.PaymentClientWithdrawResponse(
            status=entities.TransactionStatus.PENDING
            if is_success
            else entities.TransactionStatus.FAILED,
            id_in_payment_system=str(resp_id) if resp_id > 0 else "<error>",
            raw_response=resp,
            decline_code=str(resp_id) if resp_id < 0 else resp.get("descripcionError"),
            decline_reason=resp.get("descripcionError"),
        )

    def _get_transaction_status(self) -> RemoteTransactionStatus:
        if self.trx.type != common_const.TransactionType.WITHDRAWAL:
            raise RuntimeError("Only payouts are supported")

        data = {
            "claveRastreo": self.trx.uuid.hex[:30],
            "empresa": spei_stp_const.PAYOUT_EMPRESA,
            "tipoOrden": "E"
            if self.trx.type == common_const.TransactionType.WITHDRAWAL
            else "R",
            "fechaOperacion": "",
        }

        data["firma"] = spei_stp_helpers.get_data_signature(
            data=f'||{data["empresa"]}|{data["claveRastreo"]}|{data["tipoOrden"]}|{data["fechaOperacion"]}||',
            creds=self.creds,
        )
        response = self._send_request(
            url=f"{self.creds.check_api_base_url}/efws/API/consultaOrden",
            data=data,
            method="post",
        )

        if response["estado"] == 0:
            estado = response["respuesta"].get("estado", "UNKNOWN")
            if estado == "TLQ":
                operation_status = entities.TransactionStatus.SUCCESS
            else:
                operation_status = entities.TransactionStatus.PENDING
            return entities.RemoteTransactionStatus(
                operation_status=operation_status,
                id_in_payment_system=str(response["respuesta"]["idEF"]),
                raw_data=response,
                remote_amount=Money(
                    response["respuesta"]["monto"],
                    self.trx.currency,
                ),
                # actualization_note=actualization_note,
            )

        if response["estado"] == 6:
            # Spei STP крайне ненадежная платежка, поэтому для пэйаутов никогда явно не возвращаем NOT_FOUND
            # TODO: check coverage
            return entities.RemoteTransactionStatus(
                operation_status=entities.TransactionStatus.PENDING,
                raw_data=response,
            )

        if response["estado"] == 3:
            raise RuntimeError(
                "Request to SPEI limit exceeded, rate is 100 requests/hour. "
                "Try later please."
            )

        return entities.RemoteTransactionStatus(
            operation_status=entities.TransactionStatus.PENDING,
            raw_data=response,
            # actualization_note=(
            #     "We don't know how to process this status. This is NOT success, so pending is returned.",
            #     messages.WARNING,
            # ),
        )

    def _send_request(
        self,
        url: str,
        data: dict[str, Any],
        method: str = "post",
    ) -> dict[str, Any]:
        response: requests.Response = getattr(self.session, method)(
            url, json=data, verify=False
        )
        # logger_and_check_response(response, ignore_statuses=ignore_statuses)
        return response.json(parse_float=Decimal)

    def conciliation(
        self,
        type: common_const.TransactionType,
        date: datetime.date | None = None,
    ) -> Generator[dict[str, Any], None, None]:
        payload = {
            "empresa": spei_stp_const.PAYOUT_EMPRESA,
            "firma": "",
            "page": 0,
            "tipoOrden": {
                common_const.TransactionType.WITHDRAWAL: "E",
                common_const.TransactionType.DEPOSIT: "R",
            }[type],
            "fechaOperacion": "",
        }
        if date:
            payload["fechaOperacion"] = date.strftime("%Y%m%d")

        def results(
            page: int, creds: spei_stp_helpers.SpeiStpCreds
        ) -> tuple[int, list[dict[str, Any]]]:
            payload["page"] = page
            sign_payload = f'||{payload["empresa"]}|{payload["tipoOrden"]}|{payload["fechaOperacion"]}||'
            payload["firma"] = spei_stp_helpers.get_data_signature(sign_payload, creds)
            response = self._send_request(
                url=f"{creds.check_api_base_url}/efws/API/V2/conciliacion",
                data=payload,
                method="post",
            )

            assert response["estado"] in [
                spei_stp_const.ESTADO_SUCCESS,
                spei_stp_const.ESTADO_NO_TRANSACTIONS_FOR_DATE,
            ]

            return response["total"], response.get("datos", [])

        yield {}
        # TODO: fix me
        # for creds in CustomCredentialsManager(cast(Logger, logger)).get_all_credentials(
        #     system=self.payment_system_name,
        #     credentials_cls=self.creds_cls,
        # ):
        #     total, data = results(0, creds)
        #     yield from data
        #     sleep(3)
        #     returned = len(data)
        #
        #     if returned < total:
        #         for page in range(1, total):
        #             total, data = results(page, creds)
        #             yield from data
        #             sleep(3)
        #             returned += len(data)
        #             if returned >= total:
        #                 break


class SpeiStpSandboxClient(
    SpeiStpClient, base_classes.BaseSandboxClientMixin[spei_stp_helpers.SpeiStpCreds]
):
    @classmethod
    def post_create_instruction(
        cls, account: models.CustomerDepositInstruction
    ) -> None:
        sandbox_services.imitate_callback(
            controller=controller.spei_controller,
            body=json.dumps(
                {
                    "id": random.randrange(10**10, 10**11, 1),
                    "fechaOperacion": 20200127,
                    "institucionOrdenante": 846,
                    "institucionBeneficiaria": 90646,
                    "claveRastreo": "12345",
                    "monto": "123.12",
                    "nombreOrdenante": "STP",
                    "tipoCuentaOrdenante": 40,
                    "cuentaOrdenante": "846180000400000001",
                    "rfcCurpOrdenante": "ND",
                    "nombreBeneficiario": "NOMBRE_DE_BENEFICIARIO",
                    "tipoCuentaBeneficiario": 40,
                    "nombreBeneficiario2": "NOMBRE_DE_BENEFICIARIO2",
                    "tipoCuentaBeneficiario2": 40,
                    "cuentaBeneficiario2": "64618012340000000D",
                    "rfcCurpBeneficiario": "ND",
                    "conceptoPago": "PRUEBA1",
                    "referenciaNumerica": 1234567,
                    "empresa": "NOMBRE_EMPRESA",
                    "tipoPago": 1,
                    "tsLiquidacion": "1634919027297",
                    "folioCodi": "f4c1111abd2b28a00abc",
                    "cuentaBeneficiario": account.deposit_account_number,
                }
            ),
        )

    def withdraw(self) -> entities.PaymentClientWithdrawResponse:
        return entities.PaymentClientWithdrawResponse(
            status=entities.TransactionStatus.PENDING,
            id_in_payment_system=sandbox_services.get_random_id(
                common_const.PaymentSystemType.STP_SPEI
            ),
            raw_response={"__note__": "Sandbox response, not real"},
        )
