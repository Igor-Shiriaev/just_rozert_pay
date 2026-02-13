import logging

from celery import shared_task
from django.conf import settings
from rozert_pay.common import const, slack
from rozert_pay.common.const import CeleryQueue
from rozert_pay.limits.const import SLACK_PS_STATUS_CHANNEL
from rozert_pay.payment.models import PaymentSystem, Wallet
from rozert_pay.payment.systems.muwe_spei import bank_service

logger = logging.getLogger(__name__)


@shared_task(queue=CeleryQueue.LOW_PRIORITY)
def sync_muwe_spei_bank_list() -> None:
    from rozert_pay.payment.systems.muwe_spei.client import MuweSpeiClient

    logger.info("Starting MUWE SPEI bank list synchronization")

    payment_system = PaymentSystem.objects.filter(
        type=const.PaymentSystemType.MUWE_SPEI,
        is_active=True,
    ).first()

    if not payment_system:
        logger.warning(
            "No active MUWE SPEI payment system found, skipping bank list sync"
        )
        return

    wallet_instance = Wallet.objects.filter(system=payment_system).first()

    if not wallet_instance:
        logger.warning(
            "No wallet found for MUWE SPEI payment system, skipping bank list sync"
        )
        return

    creds = MuweSpeiClient.parse_and_validate_credentials(wallet_instance.credentials)

    success = bank_service.sync_bank_list(
        base_api_url=creds.base_api_url,
        mch_id=creds.mch_id,
        api_key=creds.api_key.get_secret_value(),
    )

    if success:
        logger.info("Successfully synchronized MUWE SPEI bank list")
    else:
        logger.error("Failed to synchronize MUWE SPEI bank list")
        raise RuntimeError("MUWE SPEI bank list sync failed")


@shared_task(queue=CeleryQueue.SERVICE)
def send_bank_not_found_slack_notification(
    bank_code: str,
    transaction_id: int,
    transaction_uuid: str,
    customer_id: int,
    customer_external_id: str,
) -> None:
    env = "production" if settings.IS_PRODUCTION else "preprod"
    user_admin_url = (
        f"{settings.EXTERNAL_ROZERT_HOST}/admin/payment/customer/{customer_id}/change/"
    )
    trx_admin_url = (
        f"{settings.EXTERNAL_ROZERT_HOST}/admin/payment/paymenttransaction/"
        f"{transaction_id}/change/"
    )

    message = (
        f"❕ ENV: {env} ❕\n"
        f"Event:🚫 failed withdrawal (bank is not available)\n"
        f"User UUID: <{user_admin_url}|{customer_external_id}>\n"
        f"Transaction ID: <{trx_admin_url}|{transaction_uuid}>"
    )

    slack.slack_client.send_message(channel=SLACK_PS_STATUS_CHANNEL, text=message)

    logger.warning(
        "Bank code not found in bank list, Slack notification sent",
        extra={
            "bank_code": bank_code,
            "transaction_id": transaction_id,
            "customer_id": customer_id,
        },
    )
