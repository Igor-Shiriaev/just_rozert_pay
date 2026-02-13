from __future__ import annotations

import logging
from typing import Any, Callable, TypeVar

from django.conf import settings
from django.contrib import messages
from django.urls import reverse
from rozert_pay.common.helpers.log_utils import LogWriter
from rozert_pay.payment.models import Wallet
from rozert_pay.payment.services import errors
from rozert_pay.payment.services.base_classes import BasePaymentClient
from rozert_pay.payment.systems.base_controller import PaymentSystemController

logger = logging.getLogger(__name__)


TActionOnCredentialsChange = Callable[
    [Wallet, dict[str, Any], dict[str, Any], LogWriter],
    None | errors.Error,
]


def perform_wallet_credentials_change_action(
    *,
    controller: PaymentSystemController[Any, Any],
    wallet: Wallet,
    old_creds: dict[str, Any],
    new_creds: dict[str, Any],
    is_sandbox: bool,
    message_user: Callable[[str, int], None],
) -> LogWriter | None:
    if is_sandbox:
        return None

    action = controller.get_action_on_credentials_change()
    if not action:
        return None

    log_writer = LogWriter()
    error: errors.Error | None = action(
        wallet,
        old_creds,
        new_creds,
        log_writer,
    )

    if error:
        log_writer.write(f"Error performing credentials change action: {error}")
        message_user(
            f"Error performing credentials change action: {error}. "
            f"Please contact developer.",
            messages.WARNING,
        )
    else:
        log_writer.write("Credentials change action performed successfully")
        message_user(
            "Credentials change action performed successfully",
            messages.SUCCESS,
        )

    wallet.logs = "\n".join(log_writer.logs)
    if wallet.pk:
        wallet.save(update_fields=["logs"])
    else:
        wallet.save()

    return log_writer


T = TypeVar("T")


def setup_webhooks_credentials_change_action(
    client_cls: type[BasePaymentClient[Any]],
) -> TActionOnCredentialsChange:
    def credentials_change_action(
        wallet: Wallet,
        old_creds: dict[str, Any],
        new_creds: dict[str, Any],
        internal_logger: LogWriter,
    ) -> errors.Error | None:
        try:
            url = reverse("callback", kwargs=dict(system="paypal"))
            client_cls.setup_webhooks(
                url=f"{settings.EXTERNAL_ROZERT_HOST}{url}",
                creds=client_cls.credentials_cls(**new_creds),
                remove_existing=False,
                logger=internal_logger,
                wallet=wallet,
            )
        except Exception as e:  # pragma: no cover
            logger.warning(
                "Error setting up PayPal webhooks after credentials change",
                extra={"error": e},
            )
            return errors.Error(f"Error setting up {client_cls.__name__} webhooks: {e}")

        return None

    return credentials_change_action
