import json
import logging
from decimal import Decimal
from typing import Any

from bm.datatypes import Money
from currency.utils import from_minor_units
from rozert_pay.common import const
from rozert_pay.payment import entities
from rozert_pay.payment.models import IncomingCallback, PaymentTransaction
from rozert_pay.payment.services import (
    db_services,
    errors,
    transactions_created_on_callback,
    withdraw_services,
)
from rozert_pay.payment.systems import base_controller
from rozert_pay.payment.systems.muwe_spei import (
    bank_service,
    muwe_spei_const,
    muwe_spei_helpers,
)
from rozert_pay.payment.systems.muwe_spei.client import (
    MuweSpeiClient,
    MuweSpeiClientSandbox,
)
from rozert_pay.payment.systems.muwe_spei.muwe_spei_const import (
    ACCOUNT_NAME_EXTRA_KEY,
    BANK_CODE_EXTRA_KEY,
)

logger = logging.getLogger(__name__)


class MuweSpeiController(
    base_controller.PaymentSystemController[MuweSpeiClient, MuweSpeiClientSandbox]
):
    client_cls = MuweSpeiClient
    sandbox_client_cls = MuweSpeiClientSandbox

    def on_db_transaction_created_via_api(self, trx: PaymentTransaction) -> None:
        """
        Deposits are created via webhook in final status, no additional actions needed.
        Withdrawals require normal processing.
        """
        if trx.type == const.TransactionType.DEPOSIT:
            return
        super().on_db_transaction_created_via_api(trx)

    def _parse_callback(self, cb: IncomingCallback) -> entities.RemoteTransactionStatus:
        """
        Parse webhook callback from MUWE.

        Webhooks can be for:
        - Deposits (accountName + reference present)
        - Withdrawals (mchOrderNo present)
        - Test pings (notify.ping event)

        Returns:
            RemoteTransactionStatus with transaction status
        """
        payload = json.loads(cb.body)
        logger.info(
            "Received muwe webhook",
            extra={
                "payload": payload,
                "callback_id": cb.id,
                "callback_body": cb.body,
            },
        )

        # Determine callback type based on payload fields
        # Deposits have: reference (CLABE), accountNo
        # Withdrawals have: mchOrderNo (UUID)

        if "reference" in payload:
            return self._parse_deposit_callback(payload)
        elif "mchOrderNo" in payload:
            return self._parse_withdrawal_callback(payload)
        elif payload.get("event") == muwe_spei_const.EVENT_NOTIFY_PING:
            logger.info("Received notify.ping test webhook")
            return entities.RemoteTransactionStatus(
                operation_status=const.TransactionStatus.SUCCESS,
                raw_data=payload,
                decline_code=None,
            )
        else:
            raise ValueError(f"Unknown webhook type: {payload}")

    def _parse_deposit_callback(
        self, payload: dict[str, Any]
    ) -> entities.RemoteTransactionStatus:
        """
        Parse deposit webhook from MUWE.

        Deposit webhooks contain:
        - reference: CLABE (18 digits)
        - accountNo: Sender's account number
        - accountName: Sender's account name
        - bankCode: Sender's bank code
        - amount: Total amount (centavos)
        - income: Amount credited (centavos, after fees)
        - fee: Transaction fee (centavos)
        - status: 2=SUCCESS, 3=FAILED
        - orderId: MUWE transaction ID
        """
        reference = payload.get("reference")  # CLABE
        order_id = payload.get("orderId")  # MUWE transaction ID
        muwe_status = payload.get("status")  # 2=SUCCESS, 3=FAILED

        if not reference:
            raise ValueError("No reference (CLABE) in deposit webhook")

        if not order_id:
            raise ValueError("No orderId in deposit webhook")

        amount = payload.get("amount", 0)
        amount_mxn = from_minor_units(Decimal(amount), "MXN")

        if muwe_status not in muwe_spei_const.STATUS_MAP:
            logger.warning("Unknown MUWE deposit status", extra={"status": muwe_status})
            operation_status = const.TransactionStatus.PENDING
        else:
            operation_status = muwe_spei_const.STATUS_MAP[muwe_status]

        decline_code = None
        decline_reason = None
        if operation_status == const.TransactionStatus.FAILED:
            # For deposits (payin), MUWE only sends errMsg, not errMsgCode
            # Use errCode if available, otherwise use status code as fallback
            decline_code = payload.get("errCode") or str(muwe_status)
            decline_reason = payload.get("errMsg")

        # Create transaction via callback (deposits are created directly from webhook)
        with transactions_created_on_callback.process_transaction_creation_on_callback(
            deposit_instruction_account_number=reference,
            deposited_from_account_number=reference,
            system_type=const.PaymentSystemType.MUWE_SPEI,
            controller=self,
            amount=Money(amount_mxn, "MXN"),
            id_in_payment_system=order_id,
        ) as err_or_trx:
            if isinstance(err_or_trx, errors.Error):
                raise RuntimeError(err_or_trx)

            trx = err_or_trx

            trx.extra.update(muwe_spei_helpers.build_transaction_extra_data(payload))
            trx.save()

            if trx.customer_external_account:
                external_account = trx.customer_external_account
                if not external_account.extra:
                    external_account.extra = {}
                if "bankCode" in payload:
                    external_account.extra[BANK_CODE_EXTRA_KEY] = payload["bankCode"]
                else:
                    external_account.extra[
                        BANK_CODE_EXTRA_KEY
                    ] = bank_service.get_bank_code_by_clabe(
                        payload.get("accountNo", "")
                    )
                if "accountName" in payload:
                    external_account.extra[ACCOUNT_NAME_EXTRA_KEY] = payload[
                        "accountName"
                    ]
                external_account.save()

            return entities.RemoteTransactionStatus(
                operation_status=operation_status,
                transaction_id=trx.id,
                id_in_payment_system=order_id,
                raw_data=payload,
                remote_amount=Money(amount_mxn, "MXN"),
                decline_code=decline_code,
                decline_reason=decline_reason,
            )

    def _parse_withdrawal_callback(
        self, payload: dict[str, Any]
    ) -> entities.RemoteTransactionStatus:
        """
        Parse withdrawal webhook from MUWE.

        Withdrawal webhooks contain:
        - orderId: MUWE transaction ID
        - mchOrderNo: Our transaction UUID
        - amount: Total amount (centavos)
        - fee: Transaction fee (centavos)
        - status: 2=SUCCESS, 3=FAILED
        - errCode/errMsg: Error details if failed
        """
        order_id = payload.get("orderId")
        muwe_status = payload.get("status")

        if not order_id:
            raise ValueError("No orderId in withdrawal webhook")

        trx = PaymentTransaction.objects.for_system(
            const.PaymentSystemType.MUWE_SPEI
        ).get(
            id_in_payment_system=order_id,
            type=const.TransactionType.WITHDRAWAL,
        )

        if muwe_status not in muwe_spei_const.STATUS_MAP:
            logger.warning(
                "Unknown MUWE withdrawal status", extra={"status": muwe_status}
            )
            operation_status = const.TransactionStatus.PENDING
        else:
            operation_status = muwe_spei_const.STATUS_MAP[muwe_status]

        decline_code = None
        decline_reason = None
        if operation_status == const.TransactionStatus.FAILED:
            # For withdrawals (payout), MUWE sends errMsgCode (numeric like "40011")
            decline_code = (
                payload.get("errMsgCode") or payload.get("errCode") or str(muwe_status)
            )
            decline_reason = payload.get("errMsg")

        trx.extra.update(muwe_spei_helpers.build_transaction_extra_data(payload))
        trx.save()

        amount = payload.get("amount", 0)
        amount_mxn = from_minor_units(Decimal(amount), "MXN")

        return entities.RemoteTransactionStatus(
            operation_status=operation_status,
            transaction_id=trx.id,
            id_in_payment_system=order_id,
            raw_data=payload,
            remote_amount=Money(amount_mxn, "MXN"),
            decline_code=decline_code,
            decline_reason=decline_reason,
        )

    def _is_callback_signature_valid(self, cb: IncomingCallback) -> bool:
        """
        Validate MD5 signature of incoming webhook.

        MUWE webhooks include a 'sign' field which is MD5 hash of:
        1. Sorted non-empty parameters
        2. Appended with &key={api_key}
        3. MD5 hashed and uppercased

        Returns:
            True if signature is valid, False otherwise
        """
        payload = json.loads(cb.body)

        if "reference" in payload:
            reference = payload.get("reference")
            customer_instruction = db_services.find_deposit_instruction_by_account(
                system_type=const.PaymentSystemType.MUWE_SPEI,
                deposit_account_number=reference,
            )

            if not customer_instruction:
                logger.warning(
                    "No customer instruction found for reference, cannot validate signature",
                    extra={"reference": reference},
                )
                return False

            wallet = customer_instruction.wallet
            creds = self.client_cls.parse_and_validate_credentials(wallet.credentials)
        else:
            order_id = payload.get("orderId")
            if not order_id:
                logger.warning("No orderId in webhook, cannot validate signature")
                return False

            trx = PaymentTransaction.objects.for_system(
                const.PaymentSystemType.MUWE_SPEI
            ).get(id_in_payment_system=order_id)
            creds = self.get_client(trx).creds

        api_key = creds.api_key.get_secret_value()  # type: ignore[attr-defined]
        is_valid = muwe_spei_helpers.verify_signature(payload, api_key)

        if not is_valid:
            logger.warning(
                "Invalid webhook signature",
                extra={
                    "received_sign": payload.get("sign"),
                    "payload_keys": list(payload.keys()),
                },
            )

        return is_valid

    def _run_withdraw(
        self, trx: PaymentTransaction, client: MuweSpeiClient | MuweSpeiClientSandbox
    ) -> None:
        with withdraw_services.execute_withdraw_query_and_schedule_status_checks(
            trx=trx,
            controller=self,
        ):
            pass


muwe_spei_controller = MuweSpeiController(
    payment_system=const.PaymentSystemType.MUWE_SPEI,
    default_credentials={
        "base_api_url": "https://test.sipelatam.mx",
        "app_id": "app123",
        "mch_id": "mch123",
        "api_key": "fake_api_key_123",
    },
)
