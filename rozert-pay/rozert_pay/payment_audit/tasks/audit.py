import typing as ty

from rozert_pay.celery_app import app
from rozert_pay.common.const import CeleryQueue, PaymentSystemType
from rozert_pay.payment import models as payment_models
from rozert_pay.payment import types
from rozert_pay.payment.factories import get_payment_system_controller_by_type
from rozert_pay.payment.models import Wallet
from rozert_pay.payment_audit.services.audit_items_synchronization import (
    AuditItemsSynchronizationClientMixin,
    synchronize_audit_items_for_wallet,
)


@app.task(
    name="payment_audit.task_periodic_run_audit_data_collection",
    queue=CeleryQueue.LOW_PRIORITY,
)
def task_periodic_run_audit_data_collection(
    system_types: list[str] | None = None,
) -> None:
    if system_types:
        system_types = ty.cast(
            list[PaymentSystemType],
            [PaymentSystemType(i) for i in system_types],  # type: ignore[assignment]
        )

    for system_type in [PaymentSystemType.ILIXIUM]:
        if system_types and system_type not in system_types:
            continue

        controller = get_payment_system_controller_by_type(system_type)
        assert issubclass(
            controller.client_cls, AuditItemsSynchronizationClientMixin
        ), (
            f"{controller.client_cls} must be subclass of AuditItemsSynchronizationClientMixin "
            f"to be used in audit data collection"
        )

        for wallet in payment_models.Wallet.objects.filter(
            system__type=controller.payment_system
        ):
            task_sync_audit_data_for_wallet.delay(wallet.id)


@app.task(queue=CeleryQueue.LOW_PRIORITY)
def task_sync_audit_data_for_wallet(wallet_id: types.WalletId) -> None:
    wallet = Wallet.objects.get(id=wallet_id)

    controller = get_payment_system_controller_by_type(wallet.system.type)
    assert issubclass(controller.client_cls, AuditItemsSynchronizationClientMixin)

    synchronize_audit_items_for_wallet(
        client_cls=controller.client_cls,
        wallet=wallet,
    )
