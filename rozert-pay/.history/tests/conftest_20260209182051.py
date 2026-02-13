import contextlib
import logging
from logging import Logger
from typing import Generator
from unittest.mock import patch

import celery
import pytest
import requests_mock
from django.contrib.admin import AdminSite
from requests_mock import Mocker
from rest_framework.test import APIClient
from rozert_pay.account.models import User
from rozert_pay.common import const
from rozert_pay.common.helpers import cache
from rozert_pay.payment import models
from rozert_pay.payment.systems.stp_codi.client import create_key_pair
from rozert_pay.risk_lists.admin import (
    BlackListEntryAdmin,
    GrayListEntryAdmin,
    MerchantBlackListEntryAdmin,
    WhiteListEntryAdmin,
)
from rozert_pay.risk_lists.models import (
    BlackListEntry,
    GrayListEntry,
    MerchantBlackListEntry,
    WhiteListEntry,
)
from tests.factories import CustomerFactory, MerchantFactory, UserFactory, WalletFactory
from tests.payment.api_v1.test_views import force_authenticate


@pytest.fixture
def user(db):
    user = UserFactory.create()
    user.set_password("123")
    user.save()
    return user


@pytest.fixture
def superuser() -> User:
    return UserFactory.create(is_staff=True, is_superuser=True)


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def merchant_client(api_client, merchant) -> APIClient:
    force_authenticate(api_client, merchant)
    return api_client


@pytest.fixture
def merchant(db):
    return MerchantFactory.create()


@pytest.fixture
def customer(db) -> models.Customer:
    return CustomerFactory.create()


@pytest.fixture
def merchant_sandbox(db):
    return MerchantFactory.create(sandbox=True)


@pytest.fixture
def merchant_sandbox_client(api_client, merchant_sandbox) -> APIClient:
    force_authenticate(api_client, merchant_sandbox)
    return api_client


@pytest.fixture
def wallet(merchant) -> models.Wallet:
    return WalletFactory.create(
        merchant=merchant,
    )


@pytest.fixture
def wallet_spei(merchant: models.Merchant) -> models.Wallet:
    # TODO: remove, use wallet_stp_spei
    private, *_ = create_key_pair("123")

    return WalletFactory.create(
        merchant=merchant,
        system__type=const.PaymentSystemType.STP_SPEI,
        system__name="stp-spei",
        default_callback_url="https://callbacks",
        credentials=dict(
            account_number_prefix="123456789012{clabe}",
            base_url="http://spei",
            withdrawal_target_account="123456789012345678",
            check_api_base_url="http://spei",
            private_key=private,
            private_key_password="123",
        ),
    )


@pytest.fixture
def wallet_paypal(merchant):
    return WalletFactory.create(
        merchant=merchant,
        system__type=const.PaymentSystemType.PAYPAL,
        system__name="paypal",
        default_callback_url="https://callbacks",
        credentials={
            "mask": "123456789012{clabe}",
        },
    )


@pytest.fixture
def wallet_conekta_oxxo(merchant):
    return WalletFactory.create(
        merchant=merchant,
        system__type=const.PaymentSystemType.CONEKTA_OXXO,
        system__name="conekta_oxxo",
        default_callback_url="https://callbacks",
        credentials={
            "private_key": "123456789012",
            "public_key": "123456789012",
            "base_url": "https://conekta",
        },
    )


def mock_outcoming_callbacks(m: Mocker):
    m.post("https://callbacks/", json={})


@contextlib.contextmanager
def requests_mocker() -> Generator[requests_mock.Mocker, None, None]:
    with requests_mock.Mocker() as m:
        mock_outcoming_callbacks(m)
        yield m


_LOG_TRACKING_ENABLED = True


# @pytest.fixture(autouse=True)
# @pytest.fixture()
def disable_error_logs():
    global _LOG_TRACKING_ENABLED
    _LOG_TRACKING_ENABLED = False
    yield
    _LOG_TRACKING_ENABLED = True


@pytest.fixture(autouse=True)
def track_error_logs():
    orig_log = Logger._log

    found_error_logs = []

    def wrapper_log(self, level, msg, *args, **kwargs):
        result = orig_log(self, level, msg, *args, **kwargs)

        if level > logging.WARNING and _LOG_TRACKING_ENABLED:
            found_error_logs.append(f"{msg} {args} {kwargs}")
        return result

    try:
        Logger._log = wrapper_log  # type: ignore[method-assign]
        yield
    finally:
        Logger.log = orig_log  # type: ignore[assignment]
        if found_error_logs:
            raise AssertionError("FOUND ERROR LOGS:", "\n\t".join(found_error_logs))


@pytest.fixture
def mock_on_commit():
    with patch("django.db.transaction.on_commit", side_effect=lambda f: f()):
        yield


@pytest.fixture
def disable_celery_task():
    with patch.object(celery.Task, "apply_async") as m:
        yield m


@pytest.fixture
def mock_send_callback():
    with patch("rozert_pay.payment.tasks.send_callback") as m:
        yield m


@pytest.fixture
def mock_check_status_task():
    with cm_mock_check_status_task() as m:
        yield m


@contextlib.contextmanager
def cm_mock_check_status_task():
    with patch("rozert_pay.payment.tasks.check_status") as m:
        yield m


@pytest.fixture
def mock_slack_send_message():
    """Mock Slack client send_message to prevent actual Slack notifications during tests."""
    with patch("rozert_pay.common.slack.slack_client.send_message") as m:
        yield m


@pytest.fixture
def disable_cache():
    with cache.disable_cache_for_thread():
        yield


@pytest.fixture
def admin_site():
    return AdminSite()


@pytest.fixture
def white_list_entry_admin(admin_site) -> WhiteListEntryAdmin:
    return WhiteListEntryAdmin(WhiteListEntry, admin_site)


@pytest.fixture
def gray_list_entry_admin(admin_site) -> GrayListEntryAdmin:
    return GrayListEntryAdmin(GrayListEntry, admin_site)


@pytest.fixture
def black_list_entry_admin(admin_site) -> BlackListEntryAdmin:
    return BlackListEntryAdmin(BlackListEntry, admin_site)


@pytest.fixture
def merchant_black_list_entry_admin(admin_site) -> MerchantBlackListEntryAdmin:
    return MerchantBlackListEntryAdmin(MerchantBlackListEntry, admin_site)
