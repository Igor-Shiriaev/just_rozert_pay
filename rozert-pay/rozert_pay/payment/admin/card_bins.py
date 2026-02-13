from django.contrib import admin, messages
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.translation import gettext_lazy as _
from rozert_pay.common.helpers.admin_utils import LinkItem, make_links
from rozert_pay.payment.admin.merchant import BaseRozertAdmin
from rozert_pay.payment.models import Bank, PaymentCardBank
from rozert_pay.payment.systems.bitso_spei.models import BitsoSpeiCardBank


class BetmasterNoteAdminMixin:
    """Adds a note about changes affecting Betmaster."""

    NOTE_MESSAGE = _(
        "Warning: Changing this model will also apply corresponding updates on the Betmaster side."
    )

    def changelist_view(self, request, extra_context=None):
        messages.warning(request, self.NOTE_MESSAGE)
        return super().changelist_view(request, extra_context)  # type: ignore[misc]

    def add_view(self, request, form_url="", extra_context=None):
        messages.warning(request, self.NOTE_MESSAGE)
        return super().add_view(request, form_url, extra_context)  # type: ignore[misc]

    def change_view(self, request, object_id, form_url="", extra_context=None):
        messages.warning(request, self.NOTE_MESSAGE)
        return super().change_view(request, object_id, form_url, extra_context)  # type: ignore[misc]


@admin.register(Bank)
class BankAdmin(BetmasterNoteAdminMixin, BaseRozertAdmin):
    list_display = ("id", "name", "is_non_bank", "links")
    search_fields = ("name",)
    readonly_fields = ("links",)

    @admin.display(description=_("Links"))
    def links(self, obj: Bank) -> str:
        data: list[LinkItem] = [
            {
                "link": reverse("admin:payment_paymentcardbank_changelist")
                + f"?bank__id__exact={obj.pk}",
                "name": _("Related BINs"),
            }
        ]
        return make_links(data)


@admin.register(PaymentCardBank)
class PaymentCardBankAdmin(BetmasterNoteAdminMixin, BaseRozertAdmin):
    list_display = (
        "id",
        "bin",
        "bank",
        "card_type",
        "card_class",
        "country",
        "created_at",
        "updated_at",
        "links",
    )
    search_fields = ("bin", "bank__name")
    list_filter = ("card_type", "card_class", "country", "bank")
    raw_id_fields = ("bank",)
    readonly_fields = ("created_at", "updated_at", "links")

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("bank")
            .prefetch_related("bitso_banks")
        )

    @admin.display(description=_("Links"))
    def links(self, obj: PaymentCardBank) -> str:
        data: list[LinkItem] = [
            {
                "link": reverse("admin:payment_bank_change", args=[obj.bank_id]),
                "name": _("Bank"),
            }
        ]
        if hasattr(obj, "bitso_banks") and obj.bitso_banks.exists():
            bitso_banks_ids = ",".join(
                str(b.pk) for b in obj.bitso_banks.order_by("pk")
            )
            bitso_banks_query = urlencode({"id__in": bitso_banks_ids})
            data.append(
                {
                    "link": reverse("admin:payment_bitsospeicardbank_changelist")
                    + f"?{bitso_banks_query}",
                    "name": _("Related Bitso SPEI Banks"),
                }
            )
        return make_links(data)


@admin.register(BitsoSpeiCardBank)
class BitsoSpeiCardBankAdmin(BetmasterNoteAdminMixin, BaseRozertAdmin):
    list_display = (
        "id",
        "code",
        "name",
        "country_code",
        "is_active",
        "created_at",
        "updated_at",
        "links",
    )
    search_fields = ("code", "name")
    list_filter = ("country_code", "is_active")
    exclude = ("banks",)
    readonly_fields = ("created_at", "updated_at", "links")

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("banks")

    @admin.display(description=_("Links"))
    def links(self, obj: BitsoSpeiCardBank) -> str:
        data: list[LinkItem] = []
        if obj.banks.exists():
            bin_ids = ",".join([str(b.pk) for b in obj.banks.order_by("pk")])
            bins_query = urlencode({"id__in": bin_ids})
            data.append(
                {
                    "link": reverse("admin:payment_paymentcardbank_changelist")
                    + f"?{bins_query}",
                    "name": _("Related BINs"),
                }
            )

            bank_pks = obj.banks.values_list("bank_id", flat=True).distinct()
            if bank_pks:
                banks_query = urlencode({"id__in": ",".join(map(str, bank_pks))})
                data.append(
                    {
                        "link": reverse("admin:payment_bank_changelist")
                        + f"?{banks_query}",
                        "name": _("Related Banks"),
                    }
                )

        return make_links(data) if data else "-"
