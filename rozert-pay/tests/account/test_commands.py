from unittest.mock import patch

import pytest
from django.core.management import call_command
from rozert_pay.account.management.commands import fill_database
from rozert_pay.account.models import User
from rozert_pay.payment.controller_registry import PAYMENT_SYSTEMS
from rozert_pay.payment.models import Merchant, MerchantGroup, PaymentSystem


@pytest.mark.django_db
class TestCommands:
    def test_can_create_superuser(self):
        call_command(
            "createsuperuser", email="test@test.com", no_input=True, interactive=False
        )

        assert User.objects.count() == 1
        user = User.objects.first()
        assert user
        assert user.email == "test@test.com"
        assert user.is_superuser


class TestFillDbCommand:
    def test_run_command(self, transactional_db):
        with patch.object(fill_database.Command, "log_error") as m:
            call_command("fill_database", email="admin@rozert-pay.com", password="123")

            assert m.call_count == 0, m.call_args_list

        user = User.objects.get(email="admin@rozert-pay.com")
        assert user.check_password("123")

        mg = MerchantGroup.objects.get(name="Betmaster (Test)")
        assert mg.user == user

        merchant = Merchant.objects.get(name="Betmaster (Sandbox)")
        assert merchant.merchant_group == mg

        # Second run has no effect
        call_command("fill_database", email="admin@rozert-pay.com", password="123")

        assert PaymentSystem.objects.count() == len(PAYMENT_SYSTEMS)
