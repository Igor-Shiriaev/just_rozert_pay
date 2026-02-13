import pytest
from django.core.management import call_command
from rozert_pay.payment.models import Customer, Wallet
from tests.factories import WalletFactory


@pytest.mark.django_db
class TestMigrateSensitiveDataCommand:
    """Test suite for migrate_sensitive_data management command."""

    def test_migrates_customer_with_all_fields(self) -> None:
        """Test that command migrates customer with email, phone, and extra data."""
        # Create customer with old fields but no encrypted fields
        # Use update() to bypass save() method that auto-encrypts
        customer = Customer(
            external_id="test-customer-1",
            _email="test@example.com",
            _phone="+1234567890",
            _extra={"key": "value", "nested": {"data": 123}},
        )
        customer.save()
        # Clear encrypted fields that were set by save()
        Customer.objects.filter(id=customer.id).update(
            extra_encrypted=None,
            email_encrypted=None,
            phone_encrypted=None,
        )
        customer.refresh_from_db()

        # Run the migration command
        call_command("migrate_sensitive_data")

        # Refresh from database
        customer.refresh_from_db()

        # Verify encrypted fields are populated
        assert customer.extra_encrypted is not None
        assert customer.extra_encrypted.get_secret_value() == {
            "key": "value",
            "nested": {"data": 123},
        }
        assert customer.email_encrypted is not None
        assert customer.email_encrypted.get_secret_value() == "test@example.com"
        assert customer.phone_encrypted is not None
        assert customer.phone_encrypted.get_secret_value() == "+1234567890"

        # Verify hash fields are populated
        assert customer.email_determenistic_hash is not None
        assert customer.phone_hash is not None

    def test_migrates_customer_with_partial_fields(self) -> None:
        """Test that command migrates customer with only some fields populated."""
        # Create customer with only email
        # Use update() to bypass save() method that auto-encrypts
        customer = Customer(
            external_id="test-customer-2",
            _email="email@example.com",
            _phone=None,
            _extra={},
        )
        customer.save()
        # Clear encrypted fields that were set by save()
        Customer.objects.filter(id=customer.id).update(
            extra_encrypted=None,
            email_encrypted=None,
            phone_encrypted=None,
        )
        customer.refresh_from_db()

        call_command("migrate_sensitive_data")

        customer.refresh_from_db()

        assert customer.extra_encrypted is not None
        assert customer.extra_encrypted.get_secret_value() == {}
        assert customer.email_encrypted is not None
        assert customer.email_encrypted.get_secret_value() == "email@example.com"
        # None values should still be None (or SecretValue(None))
        assert (
            customer.phone_encrypted is None
            or customer.phone_encrypted.get_secret_value() is None
        )
        assert customer.phone_hash is None
        assert customer.email_determenistic_hash is not None

    def test_skips_customer_with_existing_extra_encrypted(self) -> None:
        """Test that command skips customers that already have extra_encrypted."""
        # Create customer with existing encrypted data
        # First create without encrypted fields, then set them directly
        customer = Customer(
            external_id="test-customer-3",
            _email="old@example.com",
            _phone="+9876543210",
            _extra={"old": "data"},
        )
        # Set encrypted field before saving to bypass auto-encryption in save()
        customer.extra_encrypted = {"existing": "encrypted_data"}
        customer.save()

        original_extra_encrypted = customer.extra_encrypted.get_secret_value()  # type: ignore[attr-defined]

        call_command("migrate_sensitive_data")

        customer.refresh_from_db()

        # Verify that extra_encrypted was not changed
        assert customer.extra_encrypted.get_secret_value() == original_extra_encrypted  # type: ignore[attr-defined]

    def test_migrates_multiple_customers(self) -> None:
        """Test that command processes multiple customers correctly."""
        customers = []
        for i in range(5):
            customer = Customer(
                external_id=f"test-customer-{i}",
                _email=f"user{i}@example.com",
                _phone=f"+123456789{i}",
                _extra={"index": i, "data": f"value{i}"},
            )
            customer.save()
            # Clear encrypted fields that were set by save()
            Customer.objects.filter(id=customer.id).update(
                extra_encrypted=None,
                email_encrypted=None,
                phone_encrypted=None,
            )
            customer.refresh_from_db()
            customers.append(customer)

        call_command("migrate_sensitive_data")

        # Verify all customers were migrated
        for i, customer in enumerate(customers):
            customer.refresh_from_db()
            assert customer.extra_encrypted is not None
            assert customer.extra_encrypted.get_secret_value() == {
                "index": i,
                "data": f"value{i}",
            }
            assert customer.email_encrypted is not None
            assert customer.email_encrypted.get_secret_value() == f"user{i}@example.com"
            assert customer.phone_encrypted is not None
            assert customer.phone_encrypted.get_secret_value() == f"+123456789{i}"

    def test_migrates_customer_with_empty_extra(self) -> None:
        """Test that command handles customer with empty extra dict."""
        # Use update() to bypass save() method that auto-encrypts
        customer = Customer(
            external_id="test-customer-empty",
            _email="empty@example.com",
            _phone="+1111111111",
            _extra={},
        )
        customer.save()
        # Clear encrypted fields that were set by save()
        Customer.objects.filter(id=customer.id).update(
            extra_encrypted=None,
            email_encrypted=None,
            phone_encrypted=None,
        )
        customer.refresh_from_db()

        call_command("migrate_sensitive_data")

        customer.refresh_from_db()

        assert customer.extra_encrypted is not None
        assert customer.extra_encrypted.get_secret_value() == {}
        assert customer.email_encrypted is not None
        assert customer.phone_encrypted is not None

    def test_migrates_customer_with_none_values(self) -> None:
        """Test that command handles customer with None values."""
        # Use update() to bypass save() method that auto-encrypts
        customer = Customer(
            external_id="test-customer-none",
            _email=None,
            _phone=None,
            _extra={},
        )
        customer.save()
        # Clear encrypted fields that were set by save()
        Customer.objects.filter(id=customer.id).update(
            extra_encrypted=None,
            email_encrypted=None,
            phone_encrypted=None,
        )
        customer.refresh_from_db()

        call_command("migrate_sensitive_data")

        customer.refresh_from_db()

        assert customer.extra_encrypted is not None
        assert customer.extra_encrypted.get_secret_value() == {}
        # None values should still be set (as None)
        assert (
            customer.email_encrypted is None
            or customer.email_encrypted.get_secret_value() is None
        )
        assert (
            customer.phone_encrypted is None
            or customer.phone_encrypted.get_secret_value() is None
        )

    def test_migrates_only_customers_without_extra_encrypted(self) -> None:
        """Test that command only processes customers where extra_encrypted is None."""
        # Customer without extra_encrypted - should be migrated
        # Use update() to bypass save() method that auto-encrypts
        customer_to_migrate = Customer(
            external_id="test-migrate",
            _email="migrate@example.com",
            _phone="+1111111111",
            _extra={"should": "migrate"},
        )
        customer_to_migrate.save()
        # Clear encrypted fields that were set by save()
        Customer.objects.filter(id=customer_to_migrate.id).update(
            extra_encrypted=None,
            email_encrypted=None,
            phone_encrypted=None,
        )
        customer_to_migrate.refresh_from_db()

        # Customer with extra_encrypted - should be skipped
        customer_to_skip = Customer(
            external_id="test-skip",
            _email="skip@example.com",
            _phone="+2222222222",
            _extra={"should": "not_migrate"},
        )
        customer_to_skip.extra_encrypted = {"already": "encrypted"}
        customer_to_skip.save()

        original_skip_extra = customer_to_skip.extra_encrypted.get_secret_value()  # type: ignore[attr-defined]

        call_command("migrate_sensitive_data")

        customer_to_migrate.refresh_from_db()
        customer_to_skip.refresh_from_db()

        # Verify first customer was migrated
        assert customer_to_migrate.extra_encrypted is not None
        assert customer_to_migrate.extra_encrypted.get_secret_value() == {  # type: ignore[attr-defined]
            "should": "migrate"
        }

        # Verify second customer was not changed
        assert (
            customer_to_skip.extra_encrypted.get_secret_value() == original_skip_extra  # type: ignore[attr-defined]
        )

    def test_idempotent_execution(self) -> None:
        """Test that running the command multiple times produces the same result."""
        # Use update() to bypass save() method that auto-encrypts
        customer = Customer(
            external_id="test-idempotent",
            _email="idempotent@example.com",
            _phone="+3333333333",
            _extra={"test": "data"},
        )
        customer.save()
        # Clear encrypted fields that were set by save()
        Customer.objects.filter(id=customer.id).update(
            extra_encrypted=None,
            email_encrypted=None,
            phone_encrypted=None,
        )
        customer.refresh_from_db()

        # Run command first time
        call_command("migrate_sensitive_data")
        customer.refresh_from_db()
        first_run_extra = customer.extra_encrypted.get_secret_value()  # type: ignore[union-attr]
        first_run_email = customer.email_encrypted.get_secret_value()  # type: ignore[union-attr]

        # Run command second time
        call_command("migrate_sensitive_data")
        customer.refresh_from_db()
        second_run_extra = customer.extra_encrypted.get_secret_value()  # type: ignore[union-attr]
        second_run_email = customer.email_encrypted.get_secret_value()  # type: ignore[union-attr]

        # Results should be the same
        assert first_run_extra == second_run_extra
        assert first_run_email == second_run_email

    def test_migrates_customer_with_complex_extra_data(self) -> None:
        """Test that command handles complex nested data in extra field."""
        complex_data = {
            "user_data": {
                "first_name": "John",
                "last_name": "Doe",
                "address": {
                    "street": "123 Main St",
                    "city": "New York",
                    "zip": "10001",
                },
            },
            "metadata": ["item1", "item2", "item3"],
            "numbers": [1, 2, 3, 4, 5],
        }

        # Use update() to bypass save() method that auto-encrypts
        customer = Customer(
            external_id="test-complex",
            _email="complex@example.com",
            _phone="+4444444444",
            _extra=complex_data,
        )
        customer.save()
        # Clear encrypted fields that were set by save()
        Customer.objects.filter(id=customer.id).update(
            extra_encrypted=None,
            email_encrypted=None,
            phone_encrypted=None,
        )
        customer.refresh_from_db()

        call_command("migrate_sensitive_data")

        customer.refresh_from_db()

        assert customer.extra_encrypted is not None
        migrated_data = customer.extra_encrypted.get_secret_value()
        assert migrated_data == complex_data
        assert migrated_data["user_data"]["first_name"] == "John"
        assert migrated_data["metadata"] == ["item1", "item2", "item3"]

    def test_migrates_wallet_with_credentials(self) -> None:
        wallet = WalletFactory()
        credentials_data = {"api_key": "test_key", "api_secret": "test_secret"}

        Wallet.objects.filter(id=wallet.id).update(
            credentials=credentials_data,
            credentials_encrypted=None,
        )
        wallet.refresh_from_db()

        call_command("migrate_sensitive_data")

        wallet.refresh_from_db()

        assert wallet.credentials_encrypted is not None
        assert wallet.credentials_encrypted.get_secret_value() == credentials_data

    def test_migrates_wallet_with_complex_credentials(self) -> None:
        """Test that command handles complex nested credentials data."""
        wallet = WalletFactory()
        complex_credentials = {
            "base_url": "https://api.example.com",
            "auth": {
                "username": "user",
                "password": "pass",
                "token": "token123",
            },
            "settings": {
                "timeout": 30,
                "retries": 3,
            },
            "endpoints": ["/deposit", "/withdraw", "/status"],
        }

        Wallet.objects.filter(id=wallet.id).update(
            credentials=complex_credentials,
            credentials_encrypted=None,
        )
        wallet.refresh_from_db()

        call_command("migrate_sensitive_data")

        wallet.refresh_from_db()

        assert wallet.credentials_encrypted is not None
        migrated_credentials = wallet.credentials_encrypted.get_secret_value()
        assert migrated_credentials == complex_credentials
        assert migrated_credentials["auth"]["username"] == "user"
        assert migrated_credentials["endpoints"] == ["/deposit", "/withdraw", "/status"]

    def test_migrates_multiple_wallets(self) -> None:
        """Test that command processes multiple wallets correctly."""
        wallets = []
        for i in range(3):
            wallet = WalletFactory()
            credentials = {
                "wallet_id": i,
                "api_key": f"key_{i}",
                "data": f"value_{i}",
            }
            Wallet.objects.filter(id=wallet.id).update(
                credentials=credentials,
                credentials_encrypted=None,
            )
            wallet.refresh_from_db()
            wallets.append((wallet, credentials))

        call_command("migrate_sensitive_data")

        for wallet, original_credentials in wallets:
            wallet.refresh_from_db()
            assert wallet.credentials_encrypted is not None
            assert wallet.credentials_encrypted.get_secret_value() == original_credentials

    def test_skips_wallet_with_existing_credentials_encrypted(self) -> None:
        """Test that command skips wallets that already have credentials_encrypted."""
        wallet_to_migrate = WalletFactory()
        credentials_to_migrate = {"should": "migrate"}
        Wallet.objects.filter(id=wallet_to_migrate.id).update(
            credentials=credentials_to_migrate,
            credentials_encrypted=None,
        )
        wallet_to_migrate.refresh_from_db()

        wallet_to_skip = WalletFactory()
        existing_credentials = {"already": "encrypted"}
        wallet_to_skip.credentials_encrypted = existing_credentials
        wallet_to_skip.save()

        original_skip_credentials = (
            wallet_to_skip.credentials_encrypted.get_secret_value()  # type: ignore[attr-defined]
        )

        call_command("migrate_sensitive_data")

        wallet_to_migrate.refresh_from_db()
        wallet_to_skip.refresh_from_db()

        # Verify first wallet was migrated
        assert wallet_to_migrate.credentials_encrypted is not None
        migrated_credentials = (
            wallet_to_migrate.credentials_encrypted.get_secret_value()  # type: ignore[attr-defined]
        )
        assert migrated_credentials == credentials_to_migrate

        # Verify second wallet was not changed
        skip_credentials = (
            wallet_to_skip.credentials_encrypted.get_secret_value()  # type: ignore[attr-defined]
        )
        assert skip_credentials == original_skip_credentials

    def test_wallet_idempotent_execution(self) -> None:
        """Test that running the command multiple times produces the same result for wallets."""
        wallet = WalletFactory()
        credentials_data = {"test": "data", "number": 123}
        Wallet.objects.filter(id=wallet.id).update(
            credentials=credentials_data,
            credentials_encrypted=None,
        )
        wallet.refresh_from_db()

        # Run command first time
        call_command("migrate_sensitive_data")
        wallet.refresh_from_db()
        first_run_credentials = wallet.credentials_encrypted.get_secret_value()  # type: ignore[union-attr]

        # Run command second time
        call_command("migrate_sensitive_data")
        wallet.refresh_from_db()
        second_run_credentials = wallet.credentials_encrypted.get_secret_value()  # type: ignore[union-attr]

        # Results should be the same
        assert first_run_credentials == second_run_credentials

    def test_migrates_wallet_with_empty_credentials(self) -> None:
        """Test that command handles wallet with empty credentials dict."""
        wallet = WalletFactory()
        Wallet.objects.filter(id=wallet.id).update(
            credentials={},
            credentials_encrypted=None,
        )
        wallet.refresh_from_db()

        call_command("migrate_sensitive_data")

        wallet.refresh_from_db()

        assert wallet.credentials_encrypted is not None
        assert wallet.credentials_encrypted.get_secret_value() == {}
