from urllib.parse import urlencode

from django import forms
from django.contrib import admin, messages
from django.contrib.admin.utils import unquote
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import QuerySet
from django.http import HttpRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext
from rozert_pay.risk_lists.const import ListType, scope, ValidFor
from rozert_pay.risk_lists.models import (
    ALLOWED_MATCH_FIELDS,
    BlackListEntry,
    GrayListEntry,
    MatchFieldKey,
    MerchantBlackListEntry,
    RiskListEntry,
    WhiteListEntry,
)


def create_risk_list_form(
    model_class: type[RiskListEntry],
    list_type_value: ListType,
    is_read_only: bool = False,
) -> type[forms.ModelForm]:
    class _RiskListForm(forms.ModelForm):
        """
        A custom form to set default values (list types and special fields) and to hide immutable fields.
        """

        match_fields = forms.MultipleChoiceField(
            choices=[(f.value, f.value) for f in ALLOWED_MATCH_FIELDS],
            required=False,
            widget=forms.CheckboxSelectMultiple,
            help_text=_(
                "Choose fields to participate in matching. "
                "If all are selected, only non-empty values will be used."
            ),
        )

        class Meta:
            model = model_class
            # To avoid duplication, the readonly_fields in the ModelAdmin subclass
            # must be consistent with the exclude attribute in the form.
            exclude = (
                "added_by",
                "created_at",
                "updated_at",
                "delete_reason",
                "expires_at",
            )
            widgets = {
                "list_type": forms.HiddenInput(),
                # Excluding this field disables its database constraint check,
                # which is why we use this alternative approach to hide it.
                "is_deleted": forms.HiddenInput(),
            }

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if is_read_only:
                return

            self.fields["list_type"].initial = list_type_value
            self.fields["valid_for"].initial = ValidFor.PERMANENT

            if not self.instance.pk and not self.is_bound:
                self.fields["match_fields"].initial = [
                    f.value for f in ALLOWED_MATCH_FIELDS
                ]
            match list_type_value:
                case ListType.WHITE:
                    self.fields["valid_for"].initial = ValidFor.H24
                case ListType.GRAY:
                    self.fields["valid_for"].initial = ValidFor.PERMANENT
                case ListType.BLACK:
                    self.fields["valid_for"].initial = ValidFor.PERMANENT
                    self.fields["valid_for"].widget = forms.HiddenInput()

                case ListType.MERCHANT_BLACK:
                    self.fields["valid_for"].initial = ValidFor.PERMANENT
                    self.fields["valid_for"].widget = forms.HiddenInput()
                    self.fields[
                        "scope"
                    ].initial = scope.MERCHANT
                    self.fields["scope"].widget = forms.HiddenInput()

    return _RiskListForm


class BaseRiskListAdmin(admin.ModelAdmin):
    set_list_type: ListType
    raw_id_fields = ("customer", "wallet", "merchant")
    list_select_related = ("customer", "wallet", "merchant", "added_by")
    readonly_fields = (
        "added_by",
        "created_at",
        "updated_at",
        "delete_reason",
        "expires_at",
    )
    search_fields = (
        "customer__external_id",
        "customer__email",
        "email",
        "phone",
        "ip",
        "masked_pan",
        "customer_name",
        "provider_code",
    )
    list_display = (
        "customer",
        "scope",
        "valid_for",
        "expires_at",
        "added_by",
        "reason",
        "operation_type",
        "is_deleted",
    )
    list_filter = (
        "scope",
        "operation_type",
        "added_by",
        "created_at",
        "is_deleted",
        "provider_code",
    )
    actions = ("delete_selected",)

    @admin.action(description=_("Delete selected items (soft delete)"))
    def delete_selected(self, request, queryset: QuerySet[RiskListEntry]):
        """
        Using soft deletion only. Permanent deletion is disabled as it's not required.
        """
        return self.soft_delete(request, queryset)

    def get_form(
        self,
        request: HttpRequest,
        obj: RiskListEntry | None = None,
        change: bool = False,
        **kwargs,
    ) -> type[forms.ModelForm]:
        CustomForm = create_risk_list_form(
            self.model,
            self.set_list_type,
            is_read_only=not self.has_change_permission(request, obj),
        )
        kwargs["form"] = CustomForm
        return super().get_form(request, obj, change, **kwargs)

    def get_queryset(self, request: HttpRequest):
        """
        Default filter shows active items only.
        Users can explicitly choose to display deleted items.
        """
        qs = super().get_queryset(request)
        return qs.filter(list_type=self.set_list_type)

    def save_model(
        self,
        request: HttpRequest,
        obj: RiskListEntry,
        form: forms.ModelForm,
        change: bool,
    ) -> None:
        all_keys: list[str] = [f.value for f in ALLOWED_MATCH_FIELDS]
        selected: set[str] = set(form.cleaned_data.get("match_fields") or all_keys)
        all_selected: bool = selected == set(all_keys)

        non_empty_entry_fields: list[str] = [
            f.value
            for f in ALLOWED_MATCH_FIELDS
            if getattr(obj, f.value) not in (None, "")
        ]

        if all_selected:
            final_match_fields: list[str] = non_empty_entry_fields
        else:
            final_match_fields = [
                key
                for key in all_keys
                if key in selected and key in non_empty_entry_fields
            ]

        if not change:
            obj.added_by = request.user  # type: ignore[assignment]

        obj.match_fields = [MatchFieldKey(k) for k in final_match_fields]

        obj.save()

    def changelist_view(self, request: HttpRequest, extra_context=None):
        if request.method == "GET" and "is_deleted__exact" not in request.GET:
            params = request.GET.copy()
            params["is_deleted__exact"] = "0"
            return redirect(f"{request.path}?{params.urlencode()}")

        return super().changelist_view(request, extra_context=extra_context)

    def soft_delete(self, request: HttpRequest, queryset: QuerySet[RiskListEntry]):
        qs = queryset.filter(is_deleted=False)

        if "confirm" in request.POST:
            reason = (request.POST.get("deletion_reason") or "").strip()
            if not reason:
                return render(
                    request,
                    "admin/risk_lists/soft_delete_confirmation.html",
                    {
                        "objects": queryset,
                        "error": gettext("Reason is required."),
                    },
                )

            count = 0
            with transaction.atomic():
                for obj in qs:
                    obj.soft_delete(reason=reason)
                    count += 1

            msg = ngettext(
                "{count} item was soft deleted.",
                "{count} items were soft deleted.",
                count,
            ).format(count=count)

            self.message_user(request, msg, level=messages.SUCCESS)
            return None

        return render(
            request,
            "admin/risk_lists/soft_delete_confirmation.html",
            {"objects": qs},
        )

    def delete_view(self, request: HttpRequest, object_id: str, extra_context=None):
        """
        Overrides the default delete view to perform a soft delete,
        reusing the soft_delete() confirmation logic.
        """
        obj_id_unquoted = unquote(object_id)
        obj = self.get_object(request, obj_id_unquoted)

        if obj is None:
            self.message_user(
                request,
                _(
                    '{name} with ID "{key}" doesn\'t exist or was already deleted.'
                ).format(
                    name=self.opts.verbose_name,
                    key=obj_id_unquoted,
                ),
                level=messages.WARNING,
            )
            changelist_url = reverse(
                f"admin:{self.opts.app_label}_{self.opts.model_name}_changelist"  # noqa: E231
            )
            return redirect(changelist_url)

        if not self.has_delete_permission(request, obj):
            raise PermissionDenied

        if getattr(obj, "is_deleted", False):
            self.message_user(
                request,
                _("This {name} is already soft deleted.").format(
                    name=self.opts.verbose_name
                ),
                level=messages.INFO,
            )
            changelist_url = reverse(
                f"admin:{self.opts.app_label}_{self.opts.model_name}_changelist"  # noqa: E231
            )
            return redirect(changelist_url)

        queryset = self.get_queryset(request).filter(pk=obj.pk)
        response = self.soft_delete(request, queryset)

        if response:
            return response

        changelist_url = reverse(
            f"admin:{self.opts.app_label}_{self.opts.model_name}_changelist"  # noqa: E231
        )
        return redirect(changelist_url)

    def has_change_permission(
        self, request: HttpRequest, obj: RiskListEntry | None = None
    ) -> bool:
        if obj and obj.is_deleted:
            return False
        return super().has_change_permission(request, obj)

    def clone_view(self, request: HttpRequest, object_id: int):
        """
        Redirects to the 'add' form, pre-filled with data from the
        original object. Handles ForeignKey fields correctly
        """
        obj: RiskListEntry = get_object_or_404(self.model, pk=object_id)

        initial_data = {}
        for field in self.model._meta.fields:
            if field.auto_created or field.primary_key:
                continue

            value = getattr(obj, field.name)
            if value is None:
                continue

            if field.is_relation:
                initial_data[field.name] = value.pk
            else:
                initial_data[field.name] = value

        initial_data["is_deleted"] = False
        initial_data.pop("created_at", None)
        initial_data.pop("updated_at", None)

        assert self.opts.model_name is not None
        add_url = reverse(
            f"admin:{self.opts.app_label}_{self.opts.model_name}_add"  # noqa: E231
        )
        redirect_url = f"{add_url}?{urlencode(initial_data)}"

        return redirect(redirect_url)

    def get_urls_prefix(self) -> str:
        assert self.opts.model_name is not None
        return f"{self.opts.app_label}_{self.opts.model_name}_"

    def get_urls(self) -> list:
        urls = super().get_urls()
        assert self.opts.model_name is not None
        custom_urls = [
            path(
                "<int:object_id>/clone/",
                self.admin_site.admin_view(self.clone_view),
                name=f"{self.opts.app_label}_{self.opts.model_name}_clone",
            ),
        ]
        return custom_urls + urls


@admin.register(WhiteListEntry)
class WhiteListEntryAdmin(BaseRiskListAdmin):
    set_list_type = ListType.WHITE


@admin.register(BlackListEntry)
class BlackListEntryAdmin(BaseRiskListAdmin):
    set_list_type = ListType.BLACK


@admin.register(GrayListEntry)
class GrayListEntryAdmin(BaseRiskListAdmin):
    set_list_type = ListType.GRAY


@admin.register(MerchantBlackListEntry)
class MerchantBlackListEntryAdmin(BaseRiskListAdmin):
    set_list_type = ListType.MERCHANT_BLACK
