from django.conf import settings
from django.contrib import messages
from django.db import models
from django.http import HttpRequest
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django_object_actions import action  # type: ignore[attr-defined]
from rozert_pay.common.helpers.admin_utils import LinkItem, make_links
from rozert_pay.limits.models import LimitAlert
from rozert_pay.payment.models import Customer, Merchant, PaymentTransaction, Wallet


class RiskControlActionsMixin:
    change_actions: list[str] = ["enable_risk_control", "disable_risk_control"]

    @action(label=_("Enable Risk control"), description=_("Enable Risk control"))  # type: ignore[misc]
    def enable_risk_control(self, request: HttpRequest, obj: models.Model) -> None:
        if not isinstance(obj, (Merchant, Wallet, Customer)):
            raise ValueError("Object must be a Merchant, Wallet or Customer")
        obj.risk_control = True
        obj.save()
        messages.success(request, "Risk control enabled successfully.")

    @action(label=_("Disable Risk control"), description=_("Disable Risk control"))  # type: ignore[misc]
    def disable_risk_control(self, request: HttpRequest, obj: models.Model) -> None:
        if not isinstance(obj, (Merchant, Wallet, Customer)):
            raise ValueError("Object must be a Merchant, Wallet or Customer")
        obj.risk_control = False
        obj.save()
        messages.success(request, "Risk control disabled successfully.")


class TransactionLinksMixin:
    """
    Generating navigation links for transactions
    Used in PaymentTransactionAdmin and TransactionManagerAdmin.
    """

    def links(self, obj: PaymentTransaction) -> str:
        data: list[LinkItem] = [
            {
                "link": reverse("admin:payment_paymenttransactioneventlog_changelist")
                + f"?transaction__id__exact={obj.id}",
                "name": _("Logs"),
            },
            {
                "link": reverse("admin:payment_incomingcallback_changelist")
                + f"?transaction__id__exact={obj.id}",
                "name": _("Incoming callbacks"),
            },
            {
                "link": reverse(
                    "admin:payment_wallet_change", args=[obj.wallet.wallet_id]
                ),
                "name": _("Wallet"),
            },
            {
                "link": (
                    f"{settings.BETMASTER_BASE_URL}admin/payment/paymenttransaction/"
                    f"?id_in_payment_system={obj.uuid}"
                ),
                "name": _("Betmaster transactions"),
            },
        ]

        self._append_limit_links(obj, data)

        return make_links(data)

    def _append_limit_links(
        self, obj: PaymentTransaction, data: list[LinkItem]
    ) -> None:
        """Append limit related links"""

        if obj.customer:
            triggered_customer_limit_ids = list(
                LimitAlert.objects.filter(
                    transaction_id=obj.id,
                    customer_limit__customer_id=obj.customer.pk,
                )
                .values_list("customer_limit_id", flat=True)
                .distinct()
            )

            if triggered_customer_limit_ids:
                customer_ids_param = ",".join(
                    str(pk) for pk in triggered_customer_limit_ids
                )
                data.append(
                    {
                        "link": reverse("admin:limits_customerlimit_changelist")
                        + f"?id__in={customer_ids_param}",
                        "name": _("Triggered Customer Limits"),
                    }
                )

        triggered_wallet_limit_ids = list(
            LimitAlert.objects.filter(
                transaction_id=obj.id,
                merchant_limit__wallet_id=obj.wallet.wallet.pk,
            )
            .values_list("merchant_limit_id", flat=True)
            .distinct()
        )

        if triggered_wallet_limit_ids:
            wallet_ids_param = ",".join(str(pk) for pk in triggered_wallet_limit_ids)
            data.append(
                {
                    "link": reverse("admin:limits_merchantlimit_changelist")
                    + f"?id__in={wallet_ids_param}",
                    "name": _("Triggered Wallet Limits"),
                }
            )

        triggered_merchant_limit_ids = list(
            LimitAlert.objects.filter(
                transaction_id=obj.id,
                merchant_limit__merchant_id=obj.wallet.wallet.merchant.pk,
            )
            .values_list("merchant_limit_id", flat=True)
            .distinct()
        )

        if triggered_merchant_limit_ids:
            merchant_ids_param = ",".join(
                str(pk) for pk in triggered_merchant_limit_ids
            )
            data.append(
                {
                    "link": reverse("admin:limits_merchantlimit_changelist")
                    + f"?id__in={merchant_ids_param}",
                    "name": _("Triggered Merchant Limits"),
                }
            )

        if triggered_wallet_limit_ids or triggered_merchant_limit_ids:
            data.append(
                {
                    "link": reverse("admin:limits_limitalert_changelist")
                    + f"?transaction__id__exact={obj.id}",
                    "name": _("Triggered Limit Alerts"),
                }
            )
