from typing import Optional, cast

from auditlog.models import LogEntry as AuditLogEntry
from django.db.models import QuerySet
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rozert_pay.account.acl import AclQueryset, acl_queryset_limiter_for_request
from rozert_pay.account.models import User
from rozert_pay.account.views import CSRFExemptSessionAuthentication
from rozert_pay.common.const import CeleryQueue
from rozert_pay.limits.models import LimitAlert
from rozert_pay.payment import tasks
from rozert_pay.payment.api_backoffice.serializers import (
    CabinetCallbackSerializer,
    CabinetDepositAccountSerializer,
    LimitAlertSerializer,
)
from rozert_pay.payment.api_v1.serializers import (
    TransactionResponseSerializer,
    WalletSerializer,
)
from rozert_pay.payment.models import (
    DepositAccount,
    OutcomingCallback,
    PaymentTransaction,
    Wallet,
)


class CabinetWalletViewSet(viewsets.GenericViewSet, mixins.ListModelMixin):
    authentication_classes = (CSRFExemptSessionAuthentication,)
    serializer_class = WalletSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet[Wallet]:
        return acl_queryset_limiter_for_request(
            queryset_type=AclQueryset.WALLET,
            queryset=Wallet.objects.all(),
            request=self.request,
        )


class CabinetTransactionViewSet(viewsets.GenericViewSet, mixins.ListModelMixin):
    authentication_classes = (CSRFExemptSessionAuthentication,)
    serializer_class = TransactionResponseSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet[PaymentTransaction]:
        return acl_queryset_limiter_for_request(
            queryset_type=AclQueryset.TRANSACTION,
            queryset=PaymentTransaction.objects.all(),
            request=self.request,
        )


class CabinetDepositAccountViewSet(viewsets.GenericViewSet, mixins.ListModelMixin):
    authentication_classes = (CSRFExemptSessionAuthentication,)
    serializer_class = CabinetDepositAccountSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet[DepositAccount]:
        return acl_queryset_limiter_for_request(
            queryset_type=AclQueryset.DEPOSIT_ACCOUNT,
            queryset=DepositAccount.objects.all(),
            request=self.request,
        )


class CabinetCallbackViewSet(
    viewsets.GenericViewSet[OutcomingCallback], mixins.ListModelMixin
):
    authentication_classes = (CSRFExemptSessionAuthentication,)
    permission_classes = [IsAuthenticated]
    serializer_class = CabinetCallbackSerializer

    @action(detail=True, methods=["post"], serializer_class=None)
    def retry(self, request: Request, pk: int | None = None) -> Response:
        callback = self.get_object()
        tasks.send_callback.apply_async(
            args=(str(callback.id),), queue=CeleryQueue.NORMAL_PRIORITY
        )
        return Response({})

    def get_queryset(self) -> QuerySet[OutcomingCallback]:
        if getattr(self, "swagger_fake_view", False):
            return OutcomingCallback.objects.none()

        return acl_queryset_limiter_for_request(
            queryset_type=AclQueryset.CALLBACK,
            queryset=OutcomingCallback.objects.all(),
            request=self.request,
        )


class CabinetAlertViewSet(viewsets.GenericViewSet):
    authentication_classes = (CSRFExemptSessionAuthentication,)
    permission_classes = [IsAuthenticated]
    serializer_class = LimitAlertSerializer

    def get_queryset(self) -> QuerySet[LimitAlert]:
        user = self.request.user
        if not user.is_authenticated:
            return LimitAlert.objects.none()

        if user.is_superuser:
            return LimitAlert.objects.all()

        user_groups = user.groups.all()
        return LimitAlert.objects.filter(notification_groups__in=user_groups).distinct()

    @action(detail=False, methods=["get"])
    def unacknowledged(self, request: Request) -> Response:
        user = cast(User, request.user)
        alerts_qs = self.get_queryset().exclude(acknowledged_by=user)
        alerts = alerts_qs.order_by("-created_at")
        serializer = self.get_serializer(alerts, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def acknowledge(self, request: Request, pk: Optional[int] = None) -> Response:
        user = cast(User, request.user)
        if pk is None:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        try:
            alert = self.get_queryset().get(pk=pk)
            alert.acknowledged_by.add(user)
            AuditLogEntry.objects.log_create(
                instance=alert,
                force_log=True,
                action=AuditLogEntry.Action.UPDATE,
                changes={"acknowledged_by": f"Limit alert acknowledged by user with ID {str(user.id)}"},
                actor=user,
            )
            return Response(status=status.HTTP_204_NO_CONTENT)
        except LimitAlert.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=["post"], url_path="acknowledge-all")
    def acknowledge_all(self, request: Request) -> Response:
        user = cast(User, request.user)
        alerts_to_acknowledge = self.get_queryset().exclude(acknowledged_by=user)
        for alert in alerts_to_acknowledge:
            AuditLogEntry.objects.log_create(
                instance=alert,
                force_log=True,
                action=AuditLogEntry.Action.UPDATE,
                changes={"acknowledged_by": f"Limit alert acknowledged by user with ID {str(user.id)}"},
                actor=user,
            )

        through_model = LimitAlert.acknowledged_by.through
        bulk_create_list = [
            through_model(limitalert_id=alert_id, user_id=user.id)
            for alert_id in alerts_to_acknowledge.values_list("id", flat=True)
        ]
        if bulk_create_list:
            through_model.objects.bulk_create(bulk_create_list, ignore_conflicts=True)

        return Response(status=status.HTTP_204_NO_CONTENT)
