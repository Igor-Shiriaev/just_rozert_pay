import pytest
from django.urls import reverse
from rest_framework import status
from tests.factories import (
    CustomerLimitFactory,
    LimitAlertFactory,
    MerchantFactory,
    MerchantLimitFactory,
    UserFactory,
)
from tests.payment.api_backoffice.test_views import login_as


@pytest.mark.django_db
def test_unacknowledged_alerts_performance(api_client, django_assert_max_num_queries):
    superuser = UserFactory.create(is_superuser=True)
    merchant = MerchantFactory.create()
    merchant.login_users.add(superuser)

    login_as(api_client, superuser.email, merchant_id=merchant.id)

    for _ in range(5):
        LimitAlertFactory.create(
            customer_limit=CustomerLimitFactory.create(), merchant_limit=None
        )
        LimitAlertFactory.create(
            merchant_limit=MerchantLimitFactory.create(), customer_limit=None
        )

    url = reverse("alerts-unacknowledged")

    with django_assert_max_num_queries(3):
        response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert len(response.json()) == 10
