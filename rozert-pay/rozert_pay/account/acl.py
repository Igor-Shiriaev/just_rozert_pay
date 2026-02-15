from typing import cast

from django.db.models import QuerySet, TextChoices
from rest_framework.request import Request
from rozert_pay.account.models import User
from rozert_pay.account.serializers import (
    SessionRole,
    SessionRoleData,
    get_session_role_data,
)


class AclQueryset(TextChoices):
    WALLET = "wallet"
    TRANSACTION = "transaction"
    DEPOSIT_ACCOUNT = "deposit_account"
    CALLBACK = "callback"
    MERCHANT = "merchant"


def acl_queryset_limiter_for_request(
    queryset_type: AclQueryset,
    queryset: QuerySet,
    request: Request,
) -> QuerySet:
    return acl_queryset_limiter(
        queryset_type,
        queryset,
        cast(User, request.user),
        get_session_role_data(request),
    )


def acl_queryset_limiter(
    queryset_type: AclQueryset,
    queryset: QuerySet,
    user: User,
    session_role: SessionRoleData,
) -> QuerySet:
    session_role.clean()
    match (queryset_type, session_role.logged_in_as):
        case (AclQueryset.WALLET, SessionRole.MERCHANT):
            assert session_role.merchant_id
            return queryset.filter(
                merchant__login_users=user,
                merchant_id=session_role.merchant_id,
            )
        case (AclQueryset.WALLET, SessionRole.MERCHANT_GROUP):
            return queryset.filter(
                merchant__merchant_group__user=user,
                merchant__merchant_group_id=session_role.merchant_group_id,
            )
        case (AclQueryset.TRANSACTION, SessionRole.MERCHANT):
            return queryset.filter(
                wallet__wallet__merchant__login_users=user,
                wallet__wallet__merchant_id=session_role.merchant_id,
            )
        case (AclQueryset.TRANSACTION, SessionRole.MERCHANT_GROUP):
            return queryset.filter(
                wallet__wallet__merchant__merchant_group__user=user,
                wallet__wallet__merchant__merchant_group_id=session_role.merchant_group_id,
            )
        case (AclQueryset.DEPOSIT_ACCOUNT, SessionRole.MERCHANT):
            return queryset.filter(
                wallet__merchant__login_users=user,
                wallet__merchant_id=session_role.merchant_id,
            )
        case (AclQueryset.DEPOSIT_ACCOUNT, SessionRole.MERCHANT_GROUP):
            return queryset.filter(
                wallet__merchant__merchant_group__user=user,
                wallet__merchant__merchant_group_id=session_role.merchant_group_id,
            )
        case (AclQueryset.CALLBACK, SessionRole.MERCHANT):
            return queryset.filter(
                transaction__wallet__wallet__merchant__login_users=user,
                transaction__wallet__wallet__merchant_id=session_role.merchant_id,
            )
        case (AclQueryset.CALLBACK, SessionRole.MERCHANT_GROUP):
            return queryset.filter(
                transaction__wallet__wallet__merchant__merchant_group__user=user,
                transaction__wallet__wallet__merchant__merchant_group_id=session_role.merchant_group_id,
            )
        case (AclQueryset.MERCHANT, SessionRole.MERCHANT):
            return queryset.filter(
                login_users=user,
                id=session_role.merchant_id,
            )
        case (AclQueryset.MERCHANT, SessionRole.MERCHANT_GROUP):
            return queryset.filter(
                merchant_group__user=user,
                merchant_group_id=session_role.merchant_group_id,
            )

    raise RuntimeError(f"Unknown queryset-role type: {queryset_type, session_role}")
