import pytest
from django.core.management import call_command
from rozert_pay.payment.models import Customer


@pytest.mark.django_db
class TestMigrateSensitiveDataCommand:
    """Test suite for migrate_sensitive_data management command."""

    def test_backfills_hashes_for_customer(self) -> None:
        customer = Customer.objects.create(
            external_id="test-customer-1",
            email_encrypted="test@example.com",
            phone_encrypted="+1234567890",
            extra_encrypted={"key": "value"},
        )
        Customer.objects.filter(id=customer.id).update(
            email_deterministic_hash=None,
            phone_hash=None,
        )
        call_command("migrate_sensitive_data")

        customer.refresh_from_db()

        assert customer.email_deterministic_hash is not None
        assert customer.phone_hash is not None
        assert customer.email_encrypted
        assert customer.phone_encrypted
        assert customer.email_encrypted.get_secret_value() == "test@example.com"
        assert customer.phone_encrypted.get_secret_value() == "+1234567890"

    def test_skips_when_hashes_present(self) -> None:
        customer = Customer.objects.create(
            external_id="test-customer-2",
            email_encrypted="email@example.com",
            phone_encrypted="+1111111111",
        )

        call_command("migrate_sensitive_data")

        customer.refresh_from_db()

        assert (
            customer.email_deterministic_hash
            == "v1$$default$$23c2f6969d196e798c14aebc656311a0fc664a6e26300287c1bbc5f981b104a2"
        )
        assert (
            customer.phone_hash
            == "v1$$default$$993c449578294f126b5f7bcdf07f7e42f312aa5e67a6f920af846db7507fa006"
        )

    def test_handles_missing_encrypted_values(self) -> None:
        customer = Customer.objects.create(
            external_id="test-customer-3",
            email_encrypted=None,
            phone_encrypted=None,
        )
        Customer.objects.filter(id=customer.id).update(
            email_deterministic_hash=None,
            phone_hash=None,
        )
        call_command("migrate_sensitive_data")

        customer.refresh_from_db()

        assert customer.email_deterministic_hash is None
        assert customer.phone_hash is None

    def test_idempotent_execution(self) -> None:
        customer = Customer.objects.create(
            external_id="test-idempotent",
            email_encrypted="idempotent@example.com",
        )
        Customer.objects.filter(id=customer.id).update(
            email_deterministic_hash=None,
            phone_hash=None,
        )
        call_command("migrate_sensitive_data")

        customer.refresh_from_db()
        first_hash = customer.email_deterministic_hash

        call_command("migrate_sensitive_data")

        customer.refresh_from_db()

        assert customer.email_deterministic_hash == first_hash
