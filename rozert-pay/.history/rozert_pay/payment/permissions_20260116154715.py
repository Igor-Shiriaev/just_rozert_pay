from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from rozert_pay.account.models import User


class Permission(BaseModel):
    app: str
    name: str
    display_name: str

    def to_meta_tuple(self) -> tuple[str, str]:
        return (
            self.name,
            self.display_name,
        )

    def allowed_for(self, user: User) -> bool:
        return user.has_perm(f"{self.app}.{self.name}")


class PaymentPermissions:
    CAN_ACTUALIZE_TRANSACTION = "can_actualize_transaction"
    CAN_SET_TRANSACTION_STATUS = "can_set_transaction_status"


class CommonUserPermissions:
    CAN_VIEW_PERSONAL_DATA = Permission(
        app="account",
        name="can_view_personal_data",
        display_name="[!WARNING!] Can view User Personal Data",
    )
    CAN_VIEW_WALLET_CREDENTIALS = Permission(
        app="payment",
        name="can_view_wallet_credentials",
        display_name="[!WARNING!] Can view Wallet Credentials",
    )
    CAN_VIEW_CUSTOMER_CARD_DATA = Permission(
        app="payment",
        name="can_view_customer_card_data",
        display_name="[!WARNING!] Can View Customer Card Data",
    )
