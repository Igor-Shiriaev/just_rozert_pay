import pytest
from django.urls import reverse
from rozert_pay.payment import models
from tests.factories import PaymentTransactionFactory
from tests.payment.api_v1.test_signature import sign_request


class TestAuthorization:
    def test_authorization(self, api_client, merchant):
        url = reverse("wallet-list")
        response = api_client.get(url)
        assert response.status_code == 401

        # HMAC authorization with wrong secret
        header = sign_request("", "wrong_secret")
        response = api_client.get(
            url, HTTP_X_MERCHANT_ID=str(merchant.uuid), HTTP_X_SIGNATURE=header
        )
        assert response.status_code == 401

        # HMAC authorization with correct secret
        header = sign_request("", merchant.secret_key)
        response = api_client.get(
            url, HTTP_X_MERCHANT_ID=str(merchant.uuid), HTTP_X_SIGNATURE=header
        )
        assert response.status_code == 200

    def test_sandbox_mode(
        self,
        external_client,
        external_client_sandbox,
        merchant,
        wallet_paycash: models.Wallet,
    ):
        trx = PaymentTransactionFactory.create(wallet__wallet=wallet_paycash)

        # Test non sandbox client can access non sandbox merchant data
        external_client.get_transaction(trx.uuid)

        # Test sandbox client CAN NOT access non sandbox merchant data
        with pytest.raises(Exception):
            external_client_sandbox.get_transaction(trx.uuid)

        # Test sandbox client can access sandbox merchant data
        merchant.sandbox = True
        merchant.save()

        external_client_sandbox.get_transaction(trx.uuid)

        # Test non sandbox client CAN NOT access sandbox merchant data
        with pytest.raises(Exception):
            external_client.get_transaction(trx.uuid)
