from unittest.mock import patch

import pytest
from django.contrib.auth.models import Group
from django.test import RequestFactory
from rest_framework import status
from rest_framework.request import Request as DRFRequest
from rozert_pay.common.const import CeleryQueue
from rozert_pay.limits.models import LimitAlert
from rozert_pay.payment.api_backoffice.views import CabinetAlertViewSet
from rozert_pay.payment.models import Merchant
from tests.factories import (
    CustomerLimitFactory,
    DepositAccountFactory,
    LimitAlertFactory,
    MerchantFactory,
    MerchantGroupFactory,
    MerchantLimitFactory,
    OutcomingCallbackFactory,
    PaymentTransactionFactory,
    UserFactory,
    WalletFactory,
)
from tests.risk_lists.factories import WhiteListEntryFactory


def login_as(
    api_client,
    email,
    password="123",
    merchant_group_id=None,
    merchant_id=None,
):
    # Login as merchant group
    response = api_client.post(
        "/api/account/v1/login/",
        data={
            "email": email,
            "password": password,
            "role": {
                "merchant_group_id": merchant_group_id,
                "merchant_id": merchant_id,
            },
        },
        format="json",
    )
    assert response.status_code == 200, response.data
    return response


@pytest.mark.django_db
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
        deposit_account_m11 = DepositAccountFactory.create(
            wallet=wallet_merchant_11_group_1
        )
        callback_m11 = OutcomingCallbackFactory.create(
            transaction=transaction_merchant_11_group_1
        )

        wallet_merchant_12_group_1 = WalletFactory.create(merchant=m12)
        transaction_merchant_12_group_1 = PaymentTransactionFactory.create(
            wallet__wallet=wallet_merchant_12_group_1
        )
        deposit_account_m12 = DepositAccountFactory.create(
            wallet=wallet_merchant_12_group_1
        )
        callback_m12 = OutcomingCallbackFactory.create(
            transaction=transaction_merchant_12_group_1
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
        assert len(response.json()) == 2
        wallet_uuids = {item["id"] for item in response.json()}
        assert str(wallet_merchant_11_group_1.uuid) in wallet_uuids
        assert str(wallet_merchant_12_group_1.uuid) in wallet_uuids

        response = api_client.get("/api/backoffice/v1/transaction/")
        assert response.status_code == 200, response.data
        assert len(response.json()) == 2
        transaction_uuids = {item["id"] for item in response.json()}
        assert str(transaction_merchant_11_group_1.uuid) in transaction_uuids
        assert str(transaction_merchant_12_group_1.uuid) in transaction_uuids

        response = api_client.get("/api/backoffice/v1/deposit-account/")
        assert response.status_code == 200
        assert len(response.json()) == 2
        da_ids = {item["id"] for item in response.json()}
        assert deposit_account_m11.id in da_ids
        assert deposit_account_m12.id in da_ids

        response = api_client.get("/api/backoffice/v1/callback/")
        assert response.status_code == 200
        assert len(response.json()) == 2
        cb_ids = {item["id"] for item in response.json()}
        assert callback_m11.id in cb_ids
        assert callback_m12.id in cb_ids

        # Case 2: user1 can login as merchant11 and merchant 21
        user = UserFactory.create()
        m11.login_users.add(user)
        m21.login_users.add(user)

        login_as(api_client, user.email, merchant_id=m11.id)

        response = api_client.get("/api/backoffice/v1/wallet/")
        assert response.status_code == 200, response.data
        assert len(response.json()) == 1
        assert response.json()[0]["id"] == str(wallet_merchant_11_group_1.uuid)

        response = api_client.get("/api/backoffice/v1/transaction/")
        assert response.status_code == 200, response.data
        assert len(response.json()) == 1
        assert response.json()[0]["id"] == str(transaction_merchant_11_group_1.uuid)

        response = api_client.get("/api/backoffice/v1/deposit-account/")
        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["id"] == deposit_account_m11.id

        response = api_client.get("/api/backoffice/v1/callback/")
        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["id"] == callback_m11.id

        # Case 3: user2 can login as merchant11 and merchant22
        user2 = UserFactory.create()
        m11.login_users.add(user2)
        m22.login_users.add(user2)

        login_as(api_client, user2.email, merchant_id=m11.id)

        response = api_client.get("/api/backoffice/v1/wallet/")
        assert response.status_code == 200, response.data
        assert len(response.json()) == 1
        assert response.json()[0]["id"] == str(wallet_merchant_11_group_1.uuid)

        response = api_client.get("/api/backoffice/v1/transaction/")
        assert response.status_code == 200, response.data
        assert len(response.json()) == 1
        assert response.json()[0]["id"] == str(transaction_merchant_11_group_1.uuid)

        login_as(api_client, user2.email, merchant_id=m22.id)

        response = api_client.get("/api/backoffice/v1/wallet/")
        assert response.status_code == 200, response.data
        assert len(response.json()) == 1
        assert response.json()[0]["id"] == str(wallet_merchant_22_group_2.uuid)

        response = api_client.get("/api/backoffice/v1/transaction/")
        assert response.status_code == 200, response.data
        assert len(response.json()) == 1
        assert response.json()[0]["id"] == str(transaction_merchant_22_group_2.uuid)


@pytest.mark.django_db
class TestCabinetCallbackViewSet:
    @patch("rozert_pay.payment.tasks.send_callback.apply_async")
    def test_retry_action(self, mock_apply_async, api_client):
        user = UserFactory.create()
        merchant = MerchantFactory.create()
        merchant.login_users.add(user)
        login_as(api_client, user.email, merchant_id=merchant.id)

        callback = OutcomingCallbackFactory.create(
            transaction__wallet__wallet__merchant=merchant
        )

        response = api_client.post(f"/api/backoffice/v1/callback/{callback.id}/retry/")

        assert response.status_code == 200
        mock_apply_async.assert_called_once()
        call_args = mock_apply_async.call_args[1]
        assert call_args["args"] == (str(callback.id),)
        assert call_args["queue"] == CeleryQueue.NORMAL_PRIORITY


@pytest.mark.django_db
class TestCabinetAlertViewSet:
    def setup_method(self):
        self.superuser = UserFactory.create(is_superuser=True)
        self.regular_user = UserFactory.create()
        self.group = Group.objects.create(name="Testers")
        self.regular_user.groups.add(self.group)
        self.merchant = MerchantFactory.create()
        self.merchant.login_users.add(self.regular_user)
        self.merchant.login_users.add(self.superuser)

        self.alert_for_group = LimitAlertFactory.create(
            customer_limit=CustomerLimitFactory.create()
        )
        self.alert_for_group.notification_groups.add(self.group)

        self.alert_no_group = LimitAlertFactory.create(
            customer_limit=CustomerLimitFactory.create()
        )

        self.unrelated_alert = LimitAlertFactory.create(
            customer_limit=CustomerLimitFactory.create()
        )

    def test_unacknowledged_for_regular_user(self, api_client):
        login_as(api_client, self.regular_user.email, merchant_id=self.merchant.id)

        response = api_client.get("/api/backoffice/v1/alerts/unacknowledged/")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == self.alert_for_group.id

    def test_unacknowledged_for_superuser(self, api_client):
        login_as(api_client, self.superuser.email, merchant_id=self.merchant.id)

        response = api_client.get("/api/backoffice/v1/alerts/unacknowledged/")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        alert_ids = {item["id"] for item in data}
        assert self.alert_for_group.id in alert_ids
        assert self.alert_no_group.id in alert_ids
        assert self.unrelated_alert.id in alert_ids

    def test_acknowledge_alert(self, api_client):
        login_as(api_client, self.regular_user.email, merchant_id=self.merchant.id)

        response = api_client.post(
            f"/api/backoffice/v1/alerts/{self.alert_for_group.id}/acknowledge/"
        )
        assert response.status_code == 204

        alert = LimitAlert.objects.get(id=self.alert_for_group.id)
        assert self.regular_user in alert.acknowledged_by.all()

        response = api_client.get("/api/backoffice/v1/alerts/unacknowledged/")
        assert response.status_code == 200
        assert len(response.json()) == 0

    def test_acknowledge_unauthorized_alert(self, api_client):
        login_as(api_client, self.regular_user.email, merchant_id=self.merchant.id)

        # self.unrelated_alert is not in the user's queryset
        response = api_client.post(
            f"/api/backoffice/v1/alerts/{self.unrelated_alert.id}/acknowledge/"
        )
        assert response.status_code == 404

    def test_acknowledge_alert_not_found(self, api_client):
        login_as(api_client, self.superuser.email, merchant_id=self.merchant.id)

        non_existent_pk = self.unrelated_alert.id + 100
        response = api_client.post(
            f"/api/backoffice/v1/alerts/{non_existent_pk}/acknowledge/"
        )
        assert response.status_code == 404

    def test_acknowledge_all_alerts(self, api_client):
        another_alert = LimitAlertFactory.create()
        another_alert.notification_groups.add(self.group)

        login_as(api_client, self.regular_user.email, merchant_id=self.merchant.id)

        response = api_client.get("/api/backoffice/v1/alerts/unacknowledged/")
        assert len(response.json()) == 2

        response = api_client.post("/api/backoffice/v1/alerts/acknowledge-all/")
        assert response.status_code == 204

        response = api_client.get("/api/backoffice/v1/alerts/unacknowledged/")
        assert len(response.json()) == 0

        assert (
            self.regular_user
            in LimitAlert.objects.get(id=self.alert_for_group.id).acknowledged_by.all()
        )
        assert (
            self.regular_user
            in LimitAlert.objects.get(id=another_alert.id).acknowledged_by.all()
        )

    def test_acknowledge_alert_with_no_pk(self, api_client):
        login_as(api_client, self.superuser.email, merchant_id=self.merchant.id)

        factory = RequestFactory()
        request = factory.post("/fake-url-does-not-matter/")
        request.user = self.superuser

        drf_request = DRFRequest(request)
        view = CabinetAlertViewSet()
        view.request = drf_request

        response = CabinetAlertViewSet.acknowledge(view, drf_request, pk=None)

        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestMerchantProfileViewSet:
    def test_retrieve_profile(self, api_client):
        user = UserFactory.create()
        merchant = MerchantFactory.create()
        merchant.login_users.add(user)

        wallet = WalletFactory.create(merchant=merchant)
        currency_wallet = wallet.currencywallet_set.create(
            currency="USD",
            operational_balance="120.00",
            frozen_balance="20.00",
            pending_balance="10.00",
        )
        PaymentTransactionFactory.create(wallet=currency_wallet)
        MerchantLimitFactory.create(merchant=merchant, wallet=None)
        WhiteListEntryFactory.create(merchant=merchant)

        login_as(api_client, user.email, merchant_id=merchant.id)

        response = api_client.get(f"/api/backoffice/v1/merchant-profile/{merchant.id}/")

        assert response.status_code == 200, response.data
        payload = response.json()
        assert payload["merchant"]["id"] == str(merchant.id)
        assert payload["merchant"]["status"]["operational"]["code"] == "ACTIVE"
        assert payload["balances"]["data_status"] == "READY"
        assert payload["balances"]["currencies"][0]["currency"] == "USD"
        assert payload["balances"]["currencies"][0]["available"] == "90.00"
        assert payload["wallets"][0]["wallet_id"] == str(wallet.uuid)
        assert payload["limits"]
        assert payload["client_lists"]

    def test_cannot_retrieve_other_merchant_profile(self, api_client):
        user = UserFactory.create()
        merchant_allowed = MerchantFactory.create()
        merchant_allowed.login_users.add(user)
        merchant_blocked = MerchantFactory.create()

        login_as(api_client, user.email, merchant_id=merchant_allowed.id)

        response = api_client.get(
            f"/api/backoffice/v1/merchant-profile/{merchant_blocked.id}/"
        )

        assert response.status_code == 404
