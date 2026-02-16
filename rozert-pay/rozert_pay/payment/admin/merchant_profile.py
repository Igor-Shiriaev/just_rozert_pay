from typing import cast

from django.contrib import admin
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet
from django.http import Http404, HttpRequest, HttpResponse
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.test import APIRequestFactory
from rozert_pay.account.serializers import SESSION_KEY_ROLE
from rozert_pay.common import const
from rozert_pay.payment.api_backoffice.views import CabinetMerchantProfileViewSet
from rozert_pay.payment import models
from rozert_pay.payment.admin.merchant import BaseRozertAdmin
from rozert_pay.profiles.merchant import dto
from rozert_pay.profiles.merchant.service import get_admin_accessible_merchants_queryset


@admin.register(models.MerchantProfile)
class MerchantProfileAdmin(BaseRozertAdmin):
    change_form_template = "admin/payment/merchant_profile/change_form.html"
    list_display = (
        "id",
        "name",
        "operational_status_display",
        "risk_status_display",
        "created_at",
        "merchant_page_link",
    )
    list_display_links = ("id", "name")
    list_filter = ("operational_status", "risk_status", "created_at")
    search_fields = ("id", "name", "merchant_group__name")
    list_select_related = ("merchant_group",)
    ordering = ("-id",)

    def get_queryset(self, request: HttpRequest) -> QuerySet[models.MerchantProfile]:
        queryset = get_admin_accessible_merchants_queryset(user=request.user)
        return cast(QuerySet[models.MerchantProfile], queryset)

    def changeform_view(
        self,
        request: HttpRequest,
        object_id: str | None = None,
        form_url: str = "",
        extra_context: dict | None = None,
    ) -> HttpResponse:
        if object_id is None:
            raise Http404("Merchant profile id is required")

        merchant = self.get_queryset(request).filter(pk=object_id).first()
        if merchant is None:
            raise Http404("Merchant profile not found")
        if not self.has_view_permission(request, merchant):
            raise PermissionDenied

        merchant_profile = self._get_merchant_profile_from_api(
            request=request,
            merchant=merchant,
        )
        merchant_info = merchant_profile.merchant
        audit_url = self._get_audit_url(merchant=merchant)
        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "object": merchant,
            "original": merchant,
            "title": _("Merchant profile"),
            "merchant_info": merchant_info,
            "merchant_admin_url": reverse("admin:payment_merchant_change", args=[merchant.pk]),
            "audit_url": audit_url,
            "operations_history_url": merchant_info.links.operations_history,
            "operational_is_active": (
                merchant_info.status.operational.code
                == const.MerchantOperationalStatus.ACTIVE
            ),
        }
        return TemplateResponse(
            request,
            self.change_form_template,
            context,
        )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_module_permission(self, request: HttpRequest) -> bool:
        return request.user.is_authenticated and request.user.is_staff

    def has_view_permission(
        self,
        request: HttpRequest,
        obj: models.MerchantProfile | None = None,
    ) -> bool:
        if not (request.user.is_authenticated and request.user.is_staff):
            return False
        if obj is None:
            return True
        return self.get_queryset(request).filter(pk=obj.pk).exists()

    def has_change_permission(
        self,
        request: HttpRequest,
        obj: models.MerchantProfile | None = None,
    ) -> bool:
        return False

    def has_delete_permission(
        self,
        request: HttpRequest,
        obj: models.MerchantProfile | None = None,
    ) -> bool:
        return False

    @admin.display(description=_("Operational status"), ordering="operational_status")
    def operational_status_display(self, obj: models.MerchantProfile) -> str:
        return obj.get_operational_status_display()

    @admin.display(description=_("Risk status"), ordering="risk_status")
    def risk_status_display(self, obj: models.MerchantProfile) -> str:
        return obj.get_risk_status_display()

    @admin.display(description=_("Merchant"))
    def merchant_page_link(self, obj: models.MerchantProfile) -> str:
        url = reverse("admin:payment_merchant_change", args=[obj.pk])
        return format_html('<a href="{}">{}</a>', url, _("Open merchant"))

    def _get_audit_url(self, merchant: models.MerchantProfile) -> str:
        content_type = ContentType.objects.get_for_model(models.Merchant)
        audit_params = {"content_type__id__exact": str(content_type.id)}
        if isinstance(merchant.pk, int):
            audit_params["object_id__exact"] = str(merchant.pk)
        else:
            audit_params["object_pk__exact"] = str(merchant.pk)
        return reverse("admin:auditlog_logentry_changelist") + "?" + urlencode(audit_params)

    def _get_merchant_profile_from_api(
        self,
        *,
        request: HttpRequest,
        merchant: models.MerchantProfile,
    ) -> dto.MerchantProfileDto:
        api_request = APIRequestFactory().get(
            f"/api/backoffice/v1/merchant-profile/{merchant.pk}/"
        )
        api_request.user = request.user
        api_request.session = self._build_api_session_role(
            request=request,
            merchant=merchant,
        )

        view = CabinetMerchantProfileViewSet.as_view({"get": "retrieve"})
        response = view(api_request, pk=str(merchant.pk))
        if response.status_code != status.HTTP_200_OK:
            raise Http404("Merchant profile API response is not available")
        return dto.MerchantProfileDto.model_validate(response.data)

    def _build_api_session_role(
        self,
        *,
        request: HttpRequest,
        merchant: models.MerchantProfile,
    ) -> dict[str, dict[str, str]]:
        if merchant.merchant_group.user_id == request.user.id:
            role = {"merchant_group_id": str(merchant.merchant_group_id)}
        else:
            role = {"merchant_id": str(merchant.pk)}
        return {SESSION_KEY_ROLE: role}
