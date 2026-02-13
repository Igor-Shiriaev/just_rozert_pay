import typing as ty

from rozert_pay.common.const import EventType, TransactionExtraFields, TransactionType
from rozert_pay.payment.services import event_logs
from rozert_pay.risk_lists.const import Reason
from rozert_pay.risk_lists.models import BlackListEntry, Scope, ValidFor

if ty.TYPE_CHECKING:
    from rozert_pay.payment.models import PaymentTransaction


def add_customer_to_blacklist_by_trx(
    trx: "PaymentTransaction",
    reason: Reason,
) -> None:
    assert trx.customer
    assert trx.type == TransactionType.DEPOSIT
    assert not trx.extra.get(TransactionExtraFields.IS_CUSTOMER_BLACKLISTED)

    trx.extra[TransactionExtraFields.IS_CUSTOMER_BLACKLISTED] = True
    trx.save()

    customer = trx.customer
    merchant = trx.wallet.wallet.merchant

    existent_black_list_entry = BlackListEntry.objects.filter(
        customer=customer,
        merchant=merchant,
        scope=Scope.MERCHANT,
        valid_for=ValidFor.PERMANENT,
    ).first()
    if existent_black_list_entry:
        logger.error(
            "Customer is already blacklisted",
        )
    else:
        black_list_entry = BlackListEntry.objects.create(
            customer=customer,
            merchant=merchant,
            transaction=trx,
            added_by=None,  # Added by the system
            scope=Scope.MERCHANT,
            valid_for=ValidFor.PERMANENT,
            reason=reason,
        )

    event_logs.create_transaction_log(
        trx_id=trx.id,
        event_type=EventType.INFO,
        description=("Customer has been blacklisted"),
        extra={
            "customer_id": customer.id,
            "merchant_id": merchant.id,
            "blacklist_id": black_list_entry.id,
        },
    )
