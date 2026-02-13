import pytest
from rozert_pay.payment.models import Merchant
from tests.factories import (
    MerchantFactory,
    MerchantGroupFactory,
    PaymentTransactionFactory,
    UserFactory,
    WalletFactory,
)


def login_as(
    api_client,
    email,
    merchant_group_id=None,
    merchant_id=None,
):
    # Login as merchant group
    response = api_client.post(
        "/api/account/v1/login/",
        data={
            "email": email,
            "password": "123",
            "role": {
                "merchant_group_id": merchant_group_id,
                "merchant_id": merchant_id,
            },
        },
        format="json",
    )
    assert response.status_code == 200, response.data


@pytest.mark.django_db
@pytest.mark.usefixtures("disable_cache")
class TestAclRoles:
    def test_acl(self, api_client):
        mg1 = MerchantGroupFactory.create()
        mg2 = MerchantGroupFactory.create()

        m11: Merchant = MerchantFactory.create(merchant_group=mg1)
        m12: Merchant = MerchantFactory.create(merchant_group=mg1)
        m21: Merchant = MerchantFactory.create(merchant_group=mg2)
        m22: Merchant = MerchantFactory.create(merchant_group=mg2)

        wallet_merchant_11_group_1 = WalletFactory.create(merchant=m11)
        transaction_merchant_11_group_1 = PaymentTransactionFactory.create(
            wallet__wallet=wallet_merchant_11_group_1
        )
        wallet_merchant_12_group_1 = WalletFactory.create(merchant=m12)
        transaction_merchant_12_group_1 = PaymentTransactionFactory.create(
            wallet__wallet=wallet_merchant_12_group_1
        )
        wallet_merchant_22_group_2 = WalletFactory.create(merchant=m22)
        transaction_merchant_22_group_2 = PaymentTransactionFactory.create(
            wallet__wallet=wallet_merchant_22_group_2
        )

        # Configuration: 2 groups each have 2 merchants. Each merchant has 1 wallet and 1 transaction on this wallet.

        # Case 1: login as merchant group 1 - see all wallets and transactions for the MG
        login_as(api_client, mg1.user.email, merchant_group_id=mg1.id)

        response = api_client.get("/api/backoffice/v1/wallet/")
        assert response.status_code == 200, response.data
        assert len(response.data) == 2
        assert response.data[0]["id"] == str(wallet_merchant_11_group_1.uuid)
        assert response.data[1]["id"] == str(wallet_merchant_12_group_1.uuid)

        response = api_client.get("/api/backoffice/v1/transaction/")
        assert response.status_code == 200, response.data
        assert len(response.data) == 2
        assert response.data[0]["id"] == str(transaction_merchant_11_group_1.uuid)
        assert response.data[1]["id"] == str(transaction_merchant_12_group_1.uuid)

        # Case 2: user1 can login as merchant11 and merchant 21
        user = UserFactory.create()
        m11.login_users.add(user)
        m21.login_users.add(user)

        login_as(api_client, user.email, merchant_id=m11.id)

        response = api_client.get("/api/backoffice/v1/wallet/")
        assert response.status_code == 200, response.data
        assert len(response.data) == 1
        assert response.data[0]["id"] == str(wallet_merchant_11_group_1.uuid)

        response = api_client.get("/api/backoffice/v1/transaction/")
        assert response.status_code == 200, response.data
        assert len(response.data) == 1
        assert response.data[0]["id"] == str(transaction_merchant_11_group_1.uuid)

        # Case 3: user2 can login as merchant11 and merchant22
        user2 = UserFactory.create()
        m11.login_users.add(user2)
        m22.login_users.add(user2)

        login_as(api_client, user.email, merchant_id=m11.id)

        response = api_client.get("/api/backoffice/v1/wallet/")
        assert response.status_code == 200, response.data
        assert len(response.data) == 1
        assert response.data[0]["id"] == str(wallet_merchant_11_group_1.uuid)

        response = api_client.get("/api/backoffice/v1/transaction/")
        assert response.status_code == 200, response.data
        assert len(response.data) == 1
        assert response.data[0]["id"] == str(transaction_merchant_11_group_1.uuid)

        login_as(api_client, user2.email, merchant_id=m22.id)

        response = api_client.get("/api/backoffice/v1/wallet/")
        assert response.status_code == 200, response.data
        assert len(response.data) == 1
        assert response.data[0]["id"] == str(wallet_merchant_22_group_2.uuid)

        response = api_client.get("/api/backoffice/v1/transaction/")
        assert response.status_code == 200, response.data
        assert len(response.data) == 1
        assert response.data[0]["id"] == str(transaction_merchant_22_group_2.uuid)
