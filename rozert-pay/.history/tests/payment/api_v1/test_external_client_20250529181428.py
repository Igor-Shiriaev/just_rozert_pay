from decimal import Decimal
from unittest import mock

from rozert_pay.payment.models import PaymentTransaction
from rozert_pay_shared import rozert_client
from tests.conftest import requests_mocker


class TestExternalClient:
    def test_success(self, wallet_paycash, external_client):
        with requests_mocker() as m:
            m.post(
                "http://fake.com/v1/reference",
                json={
                    "Reference": "123",
                },
            )
            m.get(
                "http://fake.com/v1/authre?key=fake",
                json={
                    "Authorization": "fake",
                    "ExpiresIn": "6/30/2071 2:36:51 PM",
                },
            )

            resp = external_client.start_deposit(
                rozert_client.DepositRequest(
                    wallet_id=wallet_paycash.uuid,
                    amount=Decimal(100),
                    currency="MXN",
                    callback_url="http://callback.url",
                ),
                url="/api/payment/v1/transaction/",
            )

            # get transaction
            trx_data = external_client.get_transaction(resp.id)
            trx = PaymentTransaction.objects.get(uuid=trx_data.id)
            assert trx.callback_url == "http://callback.url"

            print('11111111111111111', trx_data.dict())

            assert trx_data.dict() == {
                "amount": Decimal("100.00"),
                "currency": "MXN",
                "decline_code": None,
                "decline_reason": None,
                "id": trx_data.id,
                "instruction": {
                    "link": "http://ec2-3-140-103-165.us-east-2.compute.amazonaws.com:8085/formato.php?emisor=QzA1M0VDRjlFRDQxREYwMzExQjlERjEzQ0M2QzNCNjA3OEQyRDNDMg==&token=QzA1M0VDRjlFRDQxREYwMzExQjlERjEzQ0M2QzNCNjA3OEQyRDNDMg==&referencia=MTIz",
                    "type": "instruction_file",
                    "qr_code": None,
                    "reference": None,
                },
                "status": "pending",
                "type": "deposit",
                "wallet_id": mock.ANY,
                "user_form_data": None,
                "user_data": None,
                "card_token": None,
            }
