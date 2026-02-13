import json
import logging
from typing import TYPE_CHECKING, Any, Optional

from pydantic import SecretStr
from rozert_pay.common import const
from rozert_pay.common.const import TransactionStatus, TransactionType
from rozert_pay.payment import types
from rozert_pay.payment.entities import RemoteTransactionStatus
from rozert_pay.payment.models import IncomingCallback, PaymentTransaction
from rozert_pay.payment.services import db_services, deposit_services, withdraw_services
from rozert_pay.payment.services.transaction_status_validation import (
    CleanRemoteTransactionStatus,
)
from rozert_pay.payment.systems.base_controller import PaymentSystemController
from rozert_pay.payment.systems.mpesa_mz.client import (
    MpesaMzClient,
    MpesaMzSandboxClient,
)

if TYPE_CHECKING:
    from rozert_pay.payment.services.db_services import LockedTransaction

logger = logging.getLogger(__name__)


class MpesaMzController(PaymentSystemController[MpesaMzClient, MpesaMzSandboxClient]):
    client_cls = MpesaMzClient
    sandbox_client_cls = MpesaMzSandboxClient

    def on_db_transaction_created_via_api(self, trx: PaymentTransaction) -> None:
        if (
            trx.type == TransactionType.DEPOSIT
            and trx.user_data
            and trx.user_data.phone
        ):
            self._ensure_customer_external_account(trx)
        super().on_db_transaction_created_via_api(trx)

    def _run_deposit(
        self,
        trx_id: types.TransactionId,
        client: MpesaMzClient | MpesaMzSandboxClient,
    ) -> None:
        with deposit_services.initiate_deposit(
            client,
            trx_id,
            controller=self,
            allow_immediate_fail=True,
        ):
            pass

    def _run_withdraw(
        self,
        trx: PaymentTransaction,
        client: MpesaMzClient | MpesaMzSandboxClient,
    ) -> None:
        with withdraw_services.execute_withdraw_query_and_schedule_status_checks(
            trx, self
        ):
            pass

    def sync_remote_status_with_transaction(
        self,
        *,
        remote_status: CleanRemoteTransactionStatus,
        trx_id: int | None = None,
        trx: Optional["LockedTransaction"] = None,
        allow_transition_from_final_statuses: bool = False,
    ) -> None:
        # Call parent method first to handle balance updates
        super().sync_remote_status_with_transaction(
            remote_status=remote_status,
            trx_id=trx_id,
            trx=trx,
            allow_transition_from_final_statuses=allow_transition_from_final_statuses,
        )

        # After successful deposit, create/update CustomerExternalPaymentSystemAccount
        if trx is None:
            assert trx_id is not None
            trx = db_services.get_transaction(trx_id=trx_id, for_update=True)

        if (
            trx.status == TransactionStatus.SUCCESS
            and trx.type == TransactionType.DEPOSIT
            and trx.user_data
            and trx.user_data.phone
        ):
            self._ensure_customer_external_account(trx)

    def _ensure_customer_external_account(self, trx: PaymentTransaction) -> None:
        """Create or update CustomerExternalPaymentSystemAccount after successful deposit."""
        assert trx.customer
        assert trx.user_data
        assert trx.user_data.phone

        from rozert_pay.payment.models import CustomerExternalPaymentSystemAccount

        account, created = CustomerExternalPaymentSystemAccount.objects.get_or_create(
            system_type=const.PaymentSystemType.MPESA_MZ,
            wallet=trx.wallet.wallet,
            customer=trx.customer,
            unique_account_number=trx.user_data.phone,
            defaults={"active": True},
        )

        if not created:
            # Update existing account to ensure it's active
            if not account.active:
                account.active = True
                account.save(update_fields=["active"])

        # Link account to transaction if not already linked
        if trx.customer_external_account != account:
            trx.customer_external_account = account
            trx.save(update_fields=["customer_external_account"])

        logger.info(
            "Customer external account ensured for M-Pesa MZ",
            extra={
                "transaction_id": trx.id,
                "customer_id": trx.customer.external_id,
                "phone": trx.user_data.phone,
                "account_created": created,
            },
        )

    def _parse_callback(self, cb: IncomingCallback) -> RemoteTransactionStatus:
        """Parse incoming callback from M-Pesa."""
        try:
            payload: dict[str, Any] = json.loads(cb.body)
        except json.JSONDecodeError:
            logger.error(
                "Failed to parse M-Pesa callback JSON",
                extra={"callback_id": cb.id, "body": cb.body},
            )
            raise

        # Find transaction by id_in_payment_system or ThirdPartyReference
        id_in_payment_system = payload.get("output_TransactionID")
        third_party_reference = payload.get("output_ThirdPartyReference")

        trx = None
        if id_in_payment_system:
            try:
                trx = db_services.get_transaction(
                    id_in_payment_system=id_in_payment_system,
                    for_update=False,
                    system_type=const.PaymentSystemType.MPESA_MZ,
                )
            except PaymentTransaction.DoesNotExist:
                trx = None

        if not trx and third_party_reference:
            # Try to find by UUID (ThirdPartyReference)
            from uuid import UUID

            try:
                trx_uuid = UUID(third_party_reference)
                trx = db_services.get_transaction(
                    trx_uuid=trx_uuid,
                    for_update=False,
                    system_type=const.PaymentSystemType.MPESA_MZ,
                )
            except (ValueError, TypeError):
                logger.warning(
                    "Invalid ThirdPartyReference in callback",
                    extra={
                        "callback_id": cb.id,
                        "third_party_reference": third_party_reference,
                    },
                )

        if not trx:
            logger.error(
                "Transaction not found for M-Pesa callback",
                extra={
                    "callback_id": cb.id,
                    "id_in_payment_system": id_in_payment_system,
                    "third_party_reference": third_party_reference,
                },
            )
            raise ValueError("Transaction not found")

        # Get transaction status from M-Pesa API
        remote_trx_status = self.get_client(trx)._get_transaction_status()
        remote_trx_status.transaction_id = trx.id
        return remote_trx_status

    def _is_callback_signature_valid(self, cb: IncomingCallback) -> bool:
        # TODO: Implement signature validation if M-Pesa uses it
        # For now, we rely on IP whitelist and callback_secret_key
        return True


mpesa_mz_controller = MpesaMzController(
    payment_system=const.PaymentSystemType.MPESA_MZ,
    default_credentials={
        "api_key": SecretStr(""),
        "public_key": "",
        "service_provider_code": "171717",
        "base_url": "https://api.mpesa.vm.co.mz",
    },
)
