import logging
from datetime import datetime, timedelta
from typing import Any, Generator, Iterable, cast

import requests
from django.db import transaction
from django.utils import timezone
from pydantic import ValidationError
from rozert_pay.common.const import PaymentSystemType, TransactionStatus
from rozert_pay.payment.models import PaymentTransaction, Wallet
from rozert_pay.payment.services import db_services
from rozert_pay.payment.services.transaction_status_validation import (
    CleanRemoteTransactionStatus,
)
from rozert_pay.payment.systems.bitso_spei.bitso_spei_const import (
    BITSO_SPEI_STATUS_SUCCESS,
)
from rozert_pay.payment.systems.bitso_spei.bitso_spei_controller import (
    BitsoSpeiCallbackData,
    BitsoSpeiCallbackPayload,
    bitso_spei_controller,
)
from rozert_pay.payment.systems.bitso_spei.client import BitsoSpeiClient, BitsoSpeiCreds

logger = logging.getLogger(__name__)


class BitsoSpeiAudit:
    dry_run: bool
    start_date: datetime
    end_date: datetime

    help = "Hourly audit of Bitso SPEI deposits"

    ACTION_CREATE = "Creating missed deposit"
    ACTION_UPDATE = "Updating existing deposit"
    ACTION_FAIL = "Failing existing deposit"
    STATUS_MISMATCH = "Status mismatch detected"
    FAILED_CALLBACK = "Failed to process deposit callback"

    STATUS_MAP = {
        "failed": TransactionStatus.FAILED,
        "pending": TransactionStatus.PENDING,
        "processing": TransactionStatus.PENDING,
        BITSO_SPEI_STATUS_SUCCESS: TransactionStatus.SUCCESS,
    }

    def __init__(
        self,
        *,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        dry_run: bool = False,
    ):
        self.dry_run = dry_run
        computed_end = end_date or timezone.now()
        computed_start = start_date or (computed_end - timedelta(hours=24))

        if timezone.is_naive(computed_start):
            computed_start = timezone.make_aware(computed_start)
        if timezone.is_naive(computed_end):
            computed_end = timezone.make_aware(computed_end)

        if computed_start >= computed_end:
            raise ValueError("start_date must be earlier than end_date")

        self.start_date = computed_start
        self.end_date = computed_end

    def run(self) -> None:
        deposit_count = 0
        for deposit in self.fetch_bitso_deposits():
            try:
                self.process_deposit(deposit)
            except Exception:
                logger.exception(
                    "Bitso spei deposit processing error",
                    extra={"deposit": deposit.model_dump()},
                )
            deposit_count += 1

        logger.info("Bitso SPEI audit completed (Scanned deposits: %s)", deposit_count)

        if self.dry_run:
            logger.info("Dry run mode enabled. No changes made")

    def fetch_bitso_deposits(self) -> Generator[BitsoSpeiCallbackData, None, None]:
        """Fetch deposits from Bitso API for specified or last 24 hours"""
        logger.info(
            "Getting Bitso transactions",
            extra={
                "start_date": self.start_date,
                "end_date": self.end_date,
            },
        )
        for raw_deposit in self._fetch_remote_deposits():
            try:
                callback_data = self._build_callback_data(raw_deposit)
            except (ValidationError, KeyError) as exc:
                logger.warning(
                    "Skipping malformed Bitso deposit entry",
                    extra={"deposit": raw_deposit, "error": str(exc)},
                )
                continue

            if not callback_data.details.sender_clabe:
                logger.info(
                    "Skipping refund deposit with fid %s due to empty sender_clabe",
                    raw_deposit.get("fid"),
                )
                continue

            yield callback_data

    def process_deposit(self, callback_data: BitsoSpeiCallbackData) -> None:
        """Process a single deposit and handle its status"""
        payload = callback_data.payload
        remote_status = payload.status.lower()

        try:
            trx = db_services.get_transaction(
                for_update=False,
                id_in_payment_system=callback_data.payload.fid,
                system_type=PaymentSystemType.BITSO_SPEI,
            )
        except PaymentTransaction.DoesNotExist:
            trx = None

        if trx:
            mapped_remote_status = self.STATUS_MAP.get(remote_status)

            if (
                trx.status == TransactionStatus.PENDING
                and mapped_remote_status == TransactionStatus.FAILED
            ):
                self._process_remote_data(callback_data, action=self.ACTION_FAIL)

            elif (
                trx.status == TransactionStatus.PENDING
                and mapped_remote_status == TransactionStatus.SUCCESS
            ):
                self._process_remote_data(callback_data, action=self.ACTION_UPDATE)

            elif mapped_remote_status and trx.status != mapped_remote_status:
                logger.error(
                    "Status mismatch for deposit",
                    extra={
                        "fid": callback_data.payload.fid,
                        "local_status": trx.status,
                        "remote_status": remote_status,
                        "mapped_remote_status": mapped_remote_status,
                        "clave_rastreo": callback_data.payload.details.clave_rastreo,
                        "transaction_id": str(trx.id),
                    },
                )
            return

        if remote_status != BITSO_SPEI_STATUS_SUCCESS:
            return

        assert (
            remote_status == BITSO_SPEI_STATUS_SUCCESS
        ), f"Expected {BITSO_SPEI_STATUS_SUCCESS} status for {callback_data.payload.fid}"
        self._process_remote_data(callback_data, action=self.ACTION_CREATE)

    @transaction.atomic
    def _process_remote_data(
        self, callback_data: BitsoSpeiCallbackData, action: str
    ) -> None:
        callback_with_message = self._attach_message(callback_data, message=action)
        logger.info(
            "Processing Bitso SPEI audit action",
            extra={
                "action": action,
                "fid": callback_data.raw_data.get("payload", {}).get("fid"),
                "status": callback_data.payload.status,
            },
        )

        if self.dry_run:
            logger.info(
                "Dry run: skipping Bitso SPEI audit action",
                extra={
                    "action": action,
                    "fid": callback_data.raw_data.get("payload", {}).get("fid"),
                },
            )
            return

        try:
            remote_status = bitso_spei_controller.callback_logic(
                callback_data=callback_with_message
            )
            bitso_spei_controller.sync_remote_status_with_transaction(
                trx_id=remote_status.transaction_id,
                # No transaction here -> no transaction validation
                remote_status=cast(CleanRemoteTransactionStatus, remote_status),
            )
        except Exception:
            logger.exception(
                self.FAILED_CALLBACK,
                extra={
                    "action": action,
                    "fid": callback_data.raw_data.get("payload", {}).get("fid"),
                },
            )

    def _fetch_remote_deposits(self) -> Iterable[dict[str, Any]]:
        for wallet in Wallet.objects.filter(system__type=PaymentSystemType.BITSO_SPEI):
            yield from BitsoSpeiClient._get_all_transactions_v2(
                start_date=self.start_date,
                end_date=self.end_date,
                max_pages=100,
                creds=BitsoSpeiCreds(**wallet._credentials),
                session=requests.Session(),
            )

    @staticmethod
    def _build_callback_data(deposit: dict[str, Any]) -> BitsoSpeiCallbackData:
        details = deposit.get("details") or {}
        payload_dict = {
            "amount": deposit["amount"],
            "currency": deposit["currency"] or "MXN",
            "status": deposit["status"],
            "details": {
                "sender_clabe": deposit.get("sender_clabe"),
                "receive_clabe": deposit.get("receiver_clabe"),
                "clave_rastreo": details.get("clave_rastreo"),
            },
            "fid": deposit.get("fid") or deposit.get("id") or deposit.get("wid"),
            "wid": deposit.get("wid"),
            "created_at": deposit.get("created_at"),
            "updated_at": deposit.get("updated_at"),
        }

        payload = BitsoSpeiCallbackPayload(**payload_dict)

        return BitsoSpeiCallbackData(
            raw_data=deposit,
            event_type="funding",
            payload=payload,
        )

    @staticmethod
    def _attach_message(
        callback_data: BitsoSpeiCallbackData, message: str
    ) -> BitsoSpeiCallbackData:
        payload_dict = callback_data.payload.model_dump()
        payload_dict["MESSAGE"] = message

        raw_payload = {**callback_data.raw_data.get("payload", {})}
        raw_payload["MESSAGE"] = message

        return BitsoSpeiCallbackData(
            raw_data={
                "event": callback_data.event_type,
                "payload": raw_payload,
            },
            event_type=callback_data.event_type,
            payload=BitsoSpeiCallbackPayload(**payload_dict),
        )
