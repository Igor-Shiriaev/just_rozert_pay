from typing import Any

from django.core.management import BaseCommand
from django.db import transaction
from django.db.models import Q
from rozert_pay.common.helpers.big_table_operations import BigTableServices
from rozert_pay.payment.models import Customer


class Command(BaseCommand):
    def handle(self, *args: Any, **options: Any) -> None:
        self.stdout.write("Migrating Customer sensitive data...")

        for ids in BigTableServices.get_ids_ranges_for_big_table(
            model=Customer,
            additional_q=Q(
                extra_encrypted__isnull=True,
            ),
        ):
            with transaction.atomic():
                to_update = []

                customer: Customer
                for customer in Customer.objects.filter(id__in=ids):
                    if customer.extra_encrypted:
                        continue

                    customer.extra_encrypted = customer.extra
                    if customer._email is not None:
                        customer.email_encrypted = customer._email
                        customer.email_determenistic_hash = customer._email  # type: ignore[assignment]
                    if customer._phone is not None:
                        customer.phone_encrypted = customer._phone
                        customer.phone_hash = customer._phone  # type: ignore[assignment]

                    to_update.append(customer)

                Customer.objects.bulk_update(
                    to_update,
                    fields=[
                        "extra_encrypted",
                        "email_encrypted",
                        "phone_encrypted",
                        "email_determenistic_hash",
                        "phone_hash",
                    ],
                )
        self.stdout.write("Customer sensitive data migrated successfully")

                
