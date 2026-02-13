from typing import Any

from django.core.management import BaseCommand
from django.db import transaction
from django.db.models import Q
from rozert_pay.common.helpers.big_table_operations import BigTableServices
from rozert_pay.payment.models import Customer


class Command(BaseCommand):
    def handle(self, *args: Any, **options: Any) -> None:
        for ids in BigTableServices.get_ids_ranges_for_big_table(
            model=Customer,
            additional_q=Q(
                Q(email_encrypted__isnull=False, email_deterministic_hash__isnull=True)
                | Q(phone_encrypted__isnull=False, phone_hash__isnull=True)
            ),
        ):
            with transaction.atomic():
                to_update = []

                customer: Customer
                for customer in Customer.objects.filter(id__in=ids):
                    if (
                        customer.email_encrypted
                        and customer.email_deterministic_hash is None
                    ):
                        email_value = customer.email_encrypted.get_secret_value()
                        if email_value is not None:
                            customer.email_deterministic_hash = email_value  # type: ignore[assignment]
                    if customer.phone_encrypted and customer.phone_hash is None:
                        phone_value = customer.phone_encrypted.get_secret_value()
                        if phone_value is not None:
                            customer.phone_hash = phone_value  # type: ignore[assignment]

                    to_update.append(customer)

                Customer.objects.bulk_update(
                    to_update,
                    fields=[
                        "email_deterministic_hash",
                        "phone_hash",
                    ],
                )
