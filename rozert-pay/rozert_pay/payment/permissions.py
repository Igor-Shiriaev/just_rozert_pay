from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth.models import AnonymousUser

if TYPE_CHECKING:
    from rozert_pay.account.models import User


class Permission:
    app: str
    name: str
    display_name: str

    def __init__(self, *, app: str, name: str, display_name: str) -> None:
        self.app = app
        self.name = name
        self.display_name = display_name

    def to_meta_tuple(self) -> tuple[str, str]:
        return (
            self.name,
            self.display_name,
        )

    def to_permission_str(self) -> str:
        return f"{self.app}.{self.name}"

    def allowed_for(self, user: User | AnonymousUser) -> bool:
        if not user.is_authenticated:
            return False
        return user.has_perm(f"{self.app}.{self.name}")


class PaymentPermissions:
    CAN_ACTUALIZE_TRANSACTION = "can_actualize_transaction"
    CAN_SET_TRANSACTION_STATUS = Permission(
        app="payment",
        name="can_set_transaction_status",
        display_name="Can set transaction status (custom)",
    )


class CommonUserPermissions:
    CAN_VIEW_PERSONAL_DATA = Permission(
        app="account",
        name="can_view_personal_data",
        display_name="[!WARNING!] Can View User Personal Data",
    )
