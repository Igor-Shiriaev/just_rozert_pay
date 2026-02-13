import typing as ty

from rozert_pay.payment import entities
from rozert_pay.payment.services import base_classes
from rozert_pay.payment.systems.cardpay_systems.base_client import (
    CardpayCreds,
    _BaseCardpayClient,
)


class CardpayClient(_BaseCardpayClient):
    payment_method = "BANKCARD"

    def _get_withdraw_request(self) -> dict[str, ty.Any]:
        req = super()._get_withdraw_request()

        assert self.trx.customer_card
        assert self.trx.customer

        assert self.trx.customer_card.card_data_entity
        card_data: entities.CardData = self.trx.customer_card.card_data_entity
        req["card_account"] = {
            "card": {
                "pan": card_data.card_num.get_secret_value(),
                "expiration": card_data.card_expiration,
            },
            "recipient_info": card_data.card_holder,
        }
        return req

    def _enrich_payment_request(self, req: dict[str, ty.Any]) -> dict[str, ty.Any]:
        assert self.trx.customer
        assert self.trx.customer_card

        card_data = self.trx.customer_card.card_data_entity
        assert card_data

        req["card_account"] = {
            "card": {
                "pan": card_data.card_num.get_secret_value(),
                "holder": card_data.card_holder,
                "expiration": card_data.card_expiration,
                "security_code": card_data.card_cvv.get_secret_value()
                if card_data.card_cvv
                else None,
            },
        }
        return req


class SandboxCardpayClient(
    base_classes.BaseSandboxClientMixin[CardpayCreds], CardpayClient
):
    pass
