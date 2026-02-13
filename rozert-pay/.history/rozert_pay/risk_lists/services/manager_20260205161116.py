import typing as ty

from rozert_pay.common.const import EventType, TransactionExtraFields, TransactionType
from rozert_pay.payment.services import event_logs
from rozert_pay.risk_lists.models import (
    BlackListEntry,
    Scope,
    ValidFor,
)

if ty.TYPE_CHECKING:
    from rozert_pay.payment.models import PaymentTransaction


def blacklist_for_merchant_by_trx(
    trx: "PaymentTransaction",
    reason: str,
) -> None:
    assert trx.customer  # Black list entry needs customer to be not None
    assert trx.type == TransactionType.DEPOSIT
    assert not trx.extra.get(TransactionExtraFields.IS_CUSTOMER_BLACKLISTED)

    trx.extra[TransactionExtraFields.IS_CUSTOMER_BLACKLISTED] = True
    trx.save()

    customer = trx.customer
    merchant = trx.wallet.wallet.merchant

    black_list_entry = BlackListEntry.objects.create(
        customer=customer,
        merchant=merchant,
        transaction=trx,
        added_by=None,  # Added by the system
        scope=Scope.MERCHANT,
        merchant=merchant,
        valid_for=ValidFor.PERMANENT,
        reason=reason,
    )

    event_logs.create_transaction_log(
        trx_id=trx.id,
        event_type=EventType.INFO,
        description=(
            f"Customer has been blacklisted "
            f"for merchant <uuid:{merchant.uuid}>"
        ),
        extra={
            "customer_uuid": customer.uuid,
            "merchant_uuid": merchant.uuid,
            "black_list_entry_id": black_list_entry.id,
        },
    )
