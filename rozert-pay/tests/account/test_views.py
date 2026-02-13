from unittest import mock

from django.urls import reverse
from rozert_pay.payment.models import Merchant
from tests.factories import MerchantFactory, MerchantGroupFactory


class TestLoginView:
    url = reverse("login")
    account_url = reverse("account")

    def test_login(self, api_client, user):
        MerchantGroupFactory.create(user=user)

        response = api_client.post(
            self.url, data={"email": user.email, "password": "incorrect"}
        )
        assert response.status_code == 403, response.data

        response = api_client.post(
            self.url, data={"email": "incorrect@test.com", "password": "123"}
        )
        assert response.status_code == 403, response.data

        # no auth
        response = api_client.get(self.account_url)
        assert response.status_code == 403, response.data

        # success
        response = api_client.post(
            self.url, data={"email": user.email, "password": "123"}
        )
        assert response.status_code == 200, response.data

        # cookie auth
        response = api_client.get(self.account_url)
        assert response.status_code == 200
        assert response.data["email"] == user.email

        # logout
        response = api_client.post(reverse("logout"))
        assert response.status_code == 200

        # no auth
        response = api_client.get(self.account_url)
        assert response.status_code == 403, response.data

    def test_login_with_role(
        self,
        api_client,
        user,
    ):
        m1: Merchant = MerchantFactory.create()
        m1.login_users.add(user)

        m2: Merchant = MerchantFactory.create()
        m2.login_users.add(user)

        mg = MerchantGroupFactory.create(user=user)

        response = api_client.post(
            self.url, data={"email": user.email, "password": "123"}
        )
        assert response.status_code == 400, response.data
        assert response.data == {
            "role": [
                {"merchant_group_id": mock.ANY, "name": mock.ANY},
                {"merchant_id": mock.ANY, "name": mock.ANY},
                {"merchant_id": mock.ANY, "name": mock.ANY},
            ]
        }

        # Login as merchant group
        response = api_client.post(
            self.url,
            data={
                "email": user.email,
                "password": "123",
                "role": {
                    "merchant_group_id": mg.id,
                },
            },
            format="json",
        )
        assert response.status_code == 200, response.data

        # Get account
        response = api_client.get(self.account_url)
        assert response.status_code == 200
        assert response.data == {
            "email": mock.ANY,
            "first_name": "",
            "last_name": "",
            "role": {"merchant_group_id": mock.ANY, "merchant_id": None},
        }
