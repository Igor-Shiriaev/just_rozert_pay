import logging
from decimal import Decimal
from json import JSONDecodeError
from typing import Any, Literal, Optional
from unittest.mock import patch

from bm.datatypes import Money
from paymentsds import mpesa  # type: ignore[import-untyped]
from paymentsds.mpesa import Client as MpesaSdkClient  # type: ignore[import-untyped]
from paymentsds.mpesa.response import Response  # type: ignore[import-untyped]
from rozert_pay.common import const
from rozert_pay.common.const import EventType, TransactionType
from rozert_pay.payment import entities, types
from rozert_pay.payment.entities import RemoteTransactionStatus
from rozert_pay.payment.services import errors, event_logs, sandbox_services
from rozert_pay.payment.services.base_classes import (
    BasePaymentClient,
    BaseSandboxClientMixin,
)
from rozert_pay.payment.services.errors import SafeFlowInterruptionError
from rozert_pay.payment.systems.mpesa_mz.entities import MpesaMzCredentials

logger = logging.getLogger(__name__)


def _cleanup_phone(phone: str) -> str:
    if phone[0] == "+":
        return phone[1:]
    return phone


class MpesaMzClient(BasePaymentClient[MpesaMzCredentials]):
    credentials_cls = MpesaMzCredentials

    _deposit_status_by_foreign_status = {
        "Pending": entities.TransactionStatus.PENDING,
        "Success": entities.TransactionStatus.SUCCESS,
        "Failed": entities.TransactionStatus.FAILED,
    }

    _withdrawal_status_by_foreign_status = {
        "Pending": entities.TransactionStatus.PENDING,
        "Success": entities.TransactionStatus.SUCCESS,
        "Failed": entities.TransactionStatus.FAILED,
    }

    def _get_sdk_client(self) -> MpesaSdkClient:
        # Patch client
        patch.object(mpesa.Service, "detect_errors", return_value=[]).start()

        return MpesaSdkClient(
            api_key=self.creds.api_key.get_secret_value(),
            public_key=self.creds.public_key,
            service_provider_code=self.creds.service_provider_code,
            environment=self.creds.base_url,
            timeout=self.session.timeout,
            verify_ssl=True,
        )

    def _build_sdk_raw_response(self, response: Response) -> dict[str, Any]:
        return {
            "success": response.success,
            "status": {
                "code": response.status.code,
                "description": response.status.description,
            },
            "data": response.data,
        }

    def _extract_sdk_transaction_id(self, response: Any) -> str | None:
        if isinstance(response.data, dict):
            return response.data.get("transaction") or response.data.get("reference")
        return None

    def deposit(self) -> entities.PaymentClientDepositResponse:
        assert self.trx.user_data

        if not self.trx.user_data:
            raise errors.SafeFlowInterruptionError("No user data")

        if not self.trx.user_data.phone:
            raise errors.SafeFlowInterruptionError("No phone")

        uid = str(self.trx.uuid).split("-")[0]

        if self.trx.currency != "MZN":
            raise SafeFlowInterruptionError("Only MZN in supported")

        payload = {
            "from": _cleanup_phone(self.trx.user_data.phone),
            "amount": str(self.trx.amount.quantize(Decimal("0.01"))),
            "transaction": uid,
            "reference": uid,
        }

        response = self._get_sdk_client().receive(payload)
        raw_response = self._build_sdk_raw_response(response)

        event_logs.create_transaction_log(
            trx_id=types.TransactionId(self.trx_id),
            event_type=EventType.EXTERNAL_API_REQUEST,
            description="Mpesa lib request (deposit)",
            extra={
                "payload": payload,
                "raw_response": raw_response,
            },
        )
        response_code = response.status.code

        if response.success and response_code == "INS-0":
            return entities.PaymentClientDepositResponse(
                status=entities.TransactionStatus.PENDING,
                raw_response=raw_response,
                id_in_payment_system=self._extract_sdk_transaction_id(response),
            )

        return entities.PaymentClientDepositResponse(
            status=entities.TransactionStatus.FAILED,
            raw_response=raw_response,
            decline_code=response_code or "UNKNOWN_ERROR",
            decline_reason=response.status.description or "Unknown error",
        )

    def withdraw(self) -> entities.PaymentClientWithdrawResponse:
        assert self.trx.user_data
        assert (
            self.trx.customer_external_account
            and self.trx.customer_external_account.unique_account_number
        ), "Customer external account (phone number) is required"

        uid = str(self.trx.uuid).split("-")[0]

        payload = {
            "to": _cleanup_phone(
                self.trx.customer_external_account.unique_account_number
            ),
            "amount": str(self.trx.amount.quantize(Decimal("0.01"))),
            "transaction": uid,
            "reference": uid,
        }

        response = self._get_sdk_client().send(payload)

        raw_response = self._build_sdk_raw_response(response)
        event_logs.create_transaction_log(
            trx_id=types.TransactionId(self.trx_id),
            event_type=EventType.EXTERNAL_API_REQUEST,
            description="Mpesa lib request (withdraw)",
            extra={
                "payload": payload,
                "raw_response": raw_response,
            },
        )
        response_code = response.status.code

        if response.success and response_code == "INS-0":
            return entities.PaymentClientWithdrawResponse(
                status=entities.TransactionStatus.PENDING,
                raw_response=raw_response,
                id_in_payment_system=self._extract_sdk_transaction_id(response),
            )

        decline_reason = response.status.description or "Unknown error"
        return entities.PaymentClientWithdrawResponse(
            status=entities.TransactionStatus.FAILED,
            id_in_payment_system=None,
            raw_response=raw_response,
            decline_code=response_code or "UNKNOWN_ERROR",
            decline_reason=decline_reason,
        )

    def _get_transaction_status(self) -> RemoteTransactionStatus:
        uid = str(self.trx.uuid).split("-")[0]
        payload = {
            "subject": uid,
            "reference": uid,
        }

        try:
            response = self._get_sdk_client().query(payload)
        except JSONDecodeError as e:
            raise errors.NoSentryException("Error in mpesa client") from e

        raw_response = self._build_sdk_raw_response(response)
        event_logs.create_transaction_log(
            trx_id=types.TransactionId(self.trx_id),
            event_type=EventType.EXTERNAL_API_REQUEST,
            description=f"Mpesa lib request ({self.trx.type} status)",
            extra={
                "payload": payload,
                "raw_response": raw_response,
            },
        )

        if not response.success or response.status.code != "INS-0":
            return RemoteTransactionStatus(
                operation_status=entities.TransactionStatus.FAILED,
                raw_data=raw_response,
                decline_code=response.status.code,
                decline_reason=response.status.description,
            )

        status_str = response.data.get("output_ResponseTransactionStatus", "Pending")
        status_map = (
            self._deposit_status_by_foreign_status
            if self.trx.type == TransactionType.DEPOSIT
            else self._withdrawal_status_by_foreign_status
        )
        status = status_map.get(status_str, entities.TransactionStatus.PENDING)

        decline_code: Optional[str] = None
        decline_reason: Optional[str] = None

        if status == entities.TransactionStatus.FAILED:
            decline_code = response.status.code
            decline_reason = response.status.description

        id_in_payment_system = (
            self.trx.id_in_payment_system
            or response.data.get("transaction")
            or response.data.get("reference")
        )
        return RemoteTransactionStatus(
            operation_status=status,
            raw_data=raw_response,
            id_in_payment_system=id_in_payment_system,
            decline_code=str(decline_code) if decline_code else None,
            decline_reason=decline_reason,
            remote_amount=Money(abs(self.trx.amount), self.trx.currency)
            if self.trx.amount
            else None,
        )


class MpesaMzSandboxClient(MpesaMzClient, BaseSandboxClientMixin[MpesaMzCredentials]):
    credentials_cls = MpesaMzCredentials

    def deposit(self) -> entities.PaymentClientDepositResponse:
        response = {
            "output_ResponseCode": "INS-0",
            "output_ResponseDesc": "Request processed successfully",
            "output_TransactionID": sandbox_services.get_random_id(
                const.PaymentSystemType.MPESA_MZ
            ),
            "output_ConversationID": "test_conversation_id",
        }

        return entities.PaymentClientDepositResponse(
            status=entities.TransactionStatus.PENDING,
            raw_response=response,
            id_in_payment_system=response.get("output_TransactionID"),
        )

    def withdraw(self) -> entities.PaymentClientWithdrawResponse:
        response = {
            "output_ResponseCode": "INS-0",
            "output_ResponseDesc": "Request processed successfully",
            "output_TransactionID": sandbox_services.get_random_id(
                const.PaymentSystemType.MPESA_MZ
            ),
            "output_ConversationID": "test_conversation_id",
        }

        return entities.PaymentClientWithdrawResponse(
            status=entities.TransactionStatus.PENDING,
            raw_response=response,
            id_in_payment_system=response.get("output_TransactionID"),
        )

    def _make_request(
        self,
        method: Literal["get", "post"],
        url_with_path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        path = url_with_path.split("/")[-2] if "/" in url_with_path else url_with_path

        if "singleStage" in path or "c2bPayment" in path:
            # Deposit request
            return {
                "output_ResponseCode": "INS-0",
                "output_ResponseDesc": "Request processed successfully",
                "output_TransactionID": sandbox_services.get_random_id(
                    const.PaymentSystemType.MPESA_MZ
                ),
                "output_ConversationID": "test_conversation_id",
            }
        elif "b2cPayment" in path:
            # Withdrawal request
            return {
                "output_ResponseCode": "INS-0",
                "output_ResponseDesc": "Request processed successfully",
                "output_TransactionID": sandbox_services.get_random_id(
                    const.PaymentSystemType.MPESA_MZ
                ),
                "output_ConversationID": "test_conversation_id",
            }
        elif "queryTransactionStatus" in path:
            # Status check
            return {
                "output_ResponseCode": "INS-0",
                "output_ResponseDesc": "Request processed successfully",
                "output_ResponseTransactionStatus": "Success",
                "output_TransactionID": self.trx.id_in_payment_system
                or "test_transaction_id",
            }
        else:
            raise RuntimeError(f"Unknown path: {path}")
