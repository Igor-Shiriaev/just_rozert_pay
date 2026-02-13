import logging
import typing as ty
from datetime import timedelta
from typing import cast

from django.contrib.auth import login
from django.db.models import TextChoices
from django.http import HttpRequest
from pydantic import BaseModel
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rozert_pay.account.models import User
from rozert_pay.payment.models import MerchantGroup

SESSION_KEY_ROLE = "session_role"

logger = logging.getLogger(__name__)


class LoginRole(serializers.Serializer):
    merchant_group_id = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )
    merchant_id = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )
    name = serializers.CharField(read_only=True)

    def validate(self, data: dict[str, ty.Any]) -> dict[str, ty.Any]:
        if not data.get("merchant_group_id") and not data.get("merchant_id"):
            raise ValidationError(
                "Either merchant_group_id or merchant_id should be passed"
            )
        return data

    class Meta:
        swagger_schema_fields = {
            "description": """
If user have multiple roles, you should pass which role to login as.
If role not passed, server will return 400 with list of supported roles to choose from.
            """,
        }


class LoginSerializer(serializers.Serializer):
    email = serializers.CharField()
    password = serializers.CharField()
    role = LoginRole(required=False)

    def create(self, data: dict[str, ty.Any]) -> None:
        user = User.objects.filter(email=data["email"]).first()
        if not user:
            raise AuthenticationFailed
        if not user.check_password(data["password"]):
            raise AuthenticationFailed

        role = self._get_login_role(data, user)

        login(self.context["request"], user)
        self.context["request"].session.set_expiry(timedelta(days=1))
        self.context["request"].session[SESSION_KEY_ROLE] = role

    def _get_login_role(self, data: dict[str, ty.Any], user: User) -> dict[str, ty.Any]:
        if not data.get("role"):
            roles = []

            if mg := MerchantGroup.objects.filter(user=user).first():
                roles.append(
                    {
                        "name": f"As Merchant Group {mg.name}",
                        "merchant_group_id": str(mg.id),
                    }
                )

            for merchant in user.merchants.all():
                roles.append(
                    {
                        "name": f"As Merchant {merchant.name}",
                        "merchant_id": str(merchant.id),
                    }
                )

            if not roles:
                raise ValidationError(
                    {
                        "role": [],
                    }
                )

            # Only one role, login as it
            if len(roles) == 1:
                return roles[0]

            raise ValidationError(
                {
                    "role": roles,
                }
            )

        # Validate passed role
        if mg_id := data["role"].get("merchant_group_id"):
            if not MerchantGroup.objects.filter(id=mg_id, user=user).exists():
                raise ValidationError(
                    {
                        "role": "Merchant Group not found",
                    }
                )

        if merchant_id := data["role"].get("merchant_id"):
            if not user.merchants.filter(id=merchant_id).exists():
                raise ValidationError(
                    {
                        "role": "Merchant not found",
                    }
                )

        return data["role"]


class SessionRole(TextChoices):
    MERCHANT_GROUP = "merchant_group"
    MERCHANT = "merchant"


class SessionRoleData(BaseModel):
    logged_in_as: SessionRole
    merchant_group_id: str | None
    merchant_id: str | None

    def clean(self) -> None:
        assert bool(self.merchant_group_id) ^ bool(
            self.merchant_id
        ), "Only one role should be set in session"
        if self.logged_in_as == SessionRole.MERCHANT_GROUP:
            assert self.merchant_group_id, "Merchant Group ID should be set"
        elif self.logged_in_as == SessionRole.MERCHANT:
            assert self.merchant_id, "Merchant ID should be set"


def get_session_role_data(request: HttpRequest) -> SessionRoleData:
    role: dict = request.session.get(SESSION_KEY_ROLE) or {}
    assert role, "Role not set in session"
    assert bool(role.get("merchant_group_id")) ^ bool(
        role.get("merchant_id")
    ), "Only one role should be set in session"
    result = SessionRoleData(
        logged_in_as=cast(
            SessionRole,
            SessionRole.MERCHANT_GROUP
            if role.get("merchant_group_id")
            else SessionRole.MERCHANT,
        ),
        merchant_group_id=role.get("merchant_group_id"),
        merchant_id=role.get("merchant_id"),
    )
    result.clean()
    logger.info(f"Session role data: {result}")
    return result


def get_role_from_session(request: HttpRequest) -> dict[str, ty.Any] | None:
    return request.session.get(SESSION_KEY_ROLE)


class AccountSerializer(serializers.ModelSerializer):
    role = LoginRole(read_only=True)

    def to_representation(self, instance: User) -> dict[str, ty.Any]:
        data = super().to_representation(instance)

        request = self.context["request"]
        role = get_role_from_session(request)
        assert role, "Role not set in session"
        data["role"] = {
            "merchant_group_id": role.get("merchant_group_id"),
            "merchant_id": role.get("merchant_id"),
        }
        return data

    class Meta:
        model = User
        fields = ["email", "first_name", "last_name", "role"]
