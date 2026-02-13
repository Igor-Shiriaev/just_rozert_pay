from django.db import transaction
from django.db.models import QuerySet
from rozert_pay.common import const
from rozert_pay.payment import models
from rozert_pay.payment.systems.paypal import (
    get_paypal_id_in_payment_system_from_response,
)


def update_paypal_order_id_to_capture_id() -> None:
    def _update(
        trx_: models.PaymentTransaction,
        responses: QuerySet[models.PaymentTransactionEventLog],
    ) -> None:
        for r in responses:
            try:
                req = r.extra["request"]
                if req["method"] == "POST":
                    if req["url"].endswith("capture"):
                        capture_id, t = get_paypal_id_in_payment_system_from_response(
                            r.extra["response"]["text"]
                        )
                        assert t == "capture"
                        with transaction.atomic():
                            trx_.id_in_payment_system = capture_id
                            trx_.save(update_fields=["id_in_payment_system"])
                            print(f"Updated {trx_.id} with {capture_id}")  # noqa
                            return
            except AttributeError:
                pass

    for trx in models.PaymentTransaction.objects.filter(
        wallet__wallet__system__type=const.PaymentSystemType.PAYPAL,
    ).order_by("-id"):
        response = trx.paymenttransactioneventlog_set.filter(
            event_type=const.EventType.EXTERNAL_API_REQUEST,
        )
        _update(trx, response)


# if __name__ == "__main__":
#     update_paypal_order_id_to_capture_id()
