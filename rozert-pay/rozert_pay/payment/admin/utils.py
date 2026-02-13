import datetime
import tempfile
import typing as ty

import xlsxwriter  # type: ignore[import-untyped]
from django.db import models as django_models
from django.http import FileResponse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rangefilter.filters import (  # type: ignore[import-untyped]
    DateRangeQuickSelectListFilter,
)
from rozert_pay.payment import models


def _write_transactions_stream(
    queryset_iterator: ty.Iterator[models.PaymentTransaction],
    stream: ty.IO[bytes],
) -> None:
    """
    Writes data to the provided open stream.
    """
    workbook = xlsxwriter.Workbook(
        stream, {"constant_memory": True, "remove_timezone": True}
    )
    worksheet = workbook.add_worksheet("Transactions")
    header_format = workbook.add_format({"bold": True})
    date_format = workbook.add_format({"num_format": "yyyy-mm-dd hh:mm:ss"})
    columns = [
        "ID",
        "Created At",
        "Updated At",
        "Type",
        "Amount",
        "Currency",
        "Status",
        "Decline Reason",
        "System",
        "Merchant",
        "Wallet",
    ]
    worksheet.write_row(0, 0, columns, header_format)

    for row_idx, obj in enumerate(queryset_iterator, start=1):
        data = [
            str(obj.id),
            obj.created_at,
            obj.updated_at,
            obj.get_type_display(),
            obj.amount,
            obj.currency,
            obj.status,
            obj.decline_reason or "",
            obj.wallet.wallet.system.name,
            obj.wallet.wallet.merchant.name,
            obj.wallet.wallet.name,
        ]
        worksheet.write_row(row_idx, 0, data)
        worksheet.write(row_idx, 1, obj.created_at, date_format)
        worksheet.write(row_idx, 2, obj.updated_at, date_format)

    workbook.close()


def export_transactions_as_response(
    queryset: django_models.QuerySet[models.PaymentTransaction],
    filename_prefix: str = "transactions",
) -> FileResponse:
    """
    Creates a temp file -> Writes data -> Returns a ready-to-stream FileResponse
    """
    iterator = queryset.select_related(
        "wallet__wallet__system",
        "wallet__wallet__merchant",
    ).iterator(chunk_size=2000)

    temp_file = tempfile.SpooledTemporaryFile(max_size=10 * 1024 * 1024)

    try:
        _write_transactions_stream(iterator, temp_file)
        temp_file.seek(0)
    except Exception:
        temp_file.close()
        raise

    timestamp = timezone.now().strftime("%Y%m%d_%H%M")
    full_filename = f"{filename_prefix}_{timestamp}.xlsx"

    return FileResponse(
        temp_file,
        as_attachment=True,
        filename=full_filename,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


class TransactionDateTimeQuickFilter(DateRangeQuickSelectListFilter):
    def __init__(self, field, request, params, model, model_admin, field_path):
        super().__init__(field, request, params, model, model_admin, field_path)
        now = timezone.localtime(timezone.now())
        today = now.date()
        yesterday = today - datetime.timedelta(days=1)

        self.links = (  # type: ignore[var-annotated]
            (_("Any date"), {}),
            (
                _("Today"),
                {
                    self.lookup_kwarg_gte: str(today),
                    self.lookup_kwarg_lte: str(today),
                },
            ),
            (
                _("Yesterday"),
                {
                    self.lookup_kwarg_gte: str(yesterday),
                    self.lookup_kwarg_lte: str(yesterday),
                },
            ),
            (
                _("Last 3 days"),
                {
                    self.lookup_kwarg_gte: str(today - datetime.timedelta(days=2)),
                    self.lookup_kwarg_lte: str(today),
                },
            ),
            (
                _("Last 7 days"),
                {
                    self.lookup_kwarg_gte: str(today - datetime.timedelta(days=6)),
                    self.lookup_kwarg_lte: str(today),
                },
            ),
            (
                _("Last 30 days"),
                {
                    self.lookup_kwarg_gte: str(today - datetime.timedelta(days=29)),
                    self.lookup_kwarg_lte: str(today),
                },
            ),
        )

    def choices(self, changelist):
        """
        Temporarily disables Django 5.0+ automatic facet counting for this filter.
        This overrides the `add_facets` flag on the changelist to prevent `Unsupported lookup`
        errors. The `django-admin-rangefilter` library uses custom query lookups (e.g., `range`)
        that are incompatible with Django's default facet aggregation logic.
        """
        original_add_facets = changelist.add_facets
        changelist.add_facets = False

        try:
            yield from super().choices(changelist)
        finally:
            changelist.add_facets = original_add_facets
