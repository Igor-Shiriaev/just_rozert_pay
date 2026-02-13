import argparse
from typing import Any, Iterable, Protocol, TypeVar, cast

from django.core.management import BaseCommand, CommandError
from django.db import models, transaction
from django.db.models import Q
from rozert_pay.balances.models import BalanceTransaction
from rozert_pay.common.helpers.big_table_operations import BigTableServices
from rozert_pay.payment.models import PaymentTransaction


class _ModelWithObjects(Protocol):
    objects: models.Manager[Any]


ModelT = TypeVar("ModelT", bound=_ModelWithObjects)


class Command(BaseCommand):
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--payment-transaction", action="store_true")
        parser.add_argument("--balance-transaction", action="store_true")
        parser.add_argument("--all", action="store_true")
        parser.add_argument("--chunk-size", type=int, default=1000)

    def handle(self, *args: Any, **options: Any) -> None:
        selected = self._get_selected_tables(options)
        chunk_size = options["chunk_size"]

        for name, config in selected.items():
            self._migrate_model(
                model=config["model"],
                field_map=config["field_map"],
                chunk_size=chunk_size,
                use_big_table=config["use_big_table"],
            )

    def _get_selected_tables(
        self, options: dict[str, Any]
    ) -> dict[str, dict[str, Any]]:
        configs = {
            "payment_transaction": {
                "model": PaymentTransaction,
                "field_map": {"amount": "amount2", "currency": "currency2"},
                "use_big_table": True,
            },
            "balance_transaction": {
                "model": BalanceTransaction,
                "field_map": {
                    "amount": "amount2",
                    "operational_before": "operational_before2",
                    "operational_after": "operational_after2",
                    "frozen_before": "frozen_before2",
                    "frozen_after": "frozen_after2",
                    "pending_before": "pending_before2",
                    "pending_after": "pending_after2",
                },
                "use_big_table": False,
            },
        }

        if options["all"]:
            return configs

        selected = {}
        for name, config in configs.items():
            if options[name]:
                selected[name] = config

        if not selected:
            raise CommandError("Select at least one table flag or pass --all.")

        return selected

    def _migrate_model(
        self,
        model: type[ModelT],
        field_map: dict[str, str],
        chunk_size: int,
        use_big_table: bool,
    ) -> None:
        additional_q = self._build_additional_q(field_map)
        if use_big_table:
            id_batches = BigTableServices.get_ids_ranges_for_big_table(
                model=cast(type[models.Model], model),
                additional_q=additional_q,
                chunk_size=chunk_size,
            )
        else:
            id_batches = self._iter_ids_by_queryset(
                model=model,
                additional_q=additional_q,
                chunk_size=chunk_size,
            )

        for ids in id_batches:
            with transaction.atomic():
                to_update = []
                for obj in model.objects.filter(id__in=ids):
                    updated = False
                    for old_field, new_field in field_map.items():
                        if getattr(obj, new_field) is None:
                            old_value = getattr(obj, old_field)
                            if old_value is not None:
                                setattr(obj, new_field, old_value)
                                updated = True
                    if updated:
                        to_update.append(obj)

                if to_update:
                    model.objects.bulk_update(
                        to_update,
                        fields=list(field_map.values()),
                    )

    def _build_additional_q(self, field_map: dict[str, str]) -> Q:
        q = Q()
        for old_field, new_field in field_map.items():
            q |= Q(**{f"{new_field}__isnull": True}) & Q(
                **{f"{old_field}__isnull": False}
            )
        return q

    def _iter_ids_by_queryset(
        self,
        model: type[ModelT],
        additional_q: Q,
        chunk_size: int,
    ) -> Iterable[list[Any]]:
        qs = (
            model.objects.filter(additional_q)
            .order_by("id")
            .values_list("id", flat=True)
        )
        batch = []
        for item_id in qs.iterator():
            batch.append(item_id)
            if len(batch) >= chunk_size:
                yield batch
                batch = []
        if batch:
            yield batch
