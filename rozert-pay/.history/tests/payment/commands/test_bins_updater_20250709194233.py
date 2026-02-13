import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from rozert_pay.payment.models import Bank, PaymentCardBank


@pytest.mark.django_db
class TestBinsUpdaterCommand:
    """Test suite for bins_updater management command."""

    def test_command_with_default_path(self) -> None:
        """Test command runs with default path."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(
                {
                    "123456": {
                        "br": 1,
                        "bn": "Test Bank",
                        "cc": "US",
                        "type": "credit",
                        "virtual": False,
                        "prepaid": False,
                        "raw_category": "test_category",
                    }
                },
                f,
            )
            temp_path = f.name

        try:
            call_command("bins_updater", path=temp_path)

            # Verify Bank was created
            bank = Bank.objects.get(name="Test Bank")
            assert bank.name == "Test Bank"

            # Verify PaymentCardBank was created
            card_bank = PaymentCardBank.objects.get(bin=123456)
            assert card_bank.bank == bank
            assert card_bank.card_type == 1
            assert card_bank.card_class == "credit"
            assert card_bank.country == "US"
            assert card_bank.is_virtual is False
            assert card_bank.is_prepaid is False
            assert card_bank.raw_category == "test_category"

        finally:
            Path(temp_path).unlink()

    def test_command_with_custom_path(self) -> None:
        """Test command runs with custom path argument."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(
                {
                    "654321": {
                        "br": 2,
                        "bn": "Custom Bank",
                        "cc": "CA",
                        "type": "debit",
                        "virtual": True,
                        "prepaid": True,
                        "raw_category": "custom_category",
                    }
                },
                f,
            )
            temp_path = f.name

        try:
            call_command("bins_updater", path=temp_path)

            bank = Bank.objects.get(name="Custom Bank")
            card_bank = PaymentCardBank.objects.get(bin=654321)
            assert card_bank.bank == bank
            assert card_bank.card_type == 2
            assert card_bank.card_class == "debit"
            assert card_bank.country == "CA"
            assert card_bank.is_virtual is True
            assert card_bank.is_prepaid is True
            assert card_bank.raw_category == "custom_category"

        finally:
            Path(temp_path).unlink()

    def test_command_creates_bank_if_not_exists(self) -> None:
        """Test that command creates Bank if it doesn't exist."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(
                {
                    "111111": {
                        "br": 1,
                        "bn": "New Bank",
                        "cc": "GB",
                        "type": "credit",
                        "virtual": False,
                        "prepaid": False,
                        "raw_category": "new_category",
                    }
                },
                f,
            )
            temp_path = f.name

        try:
            assert Bank.objects.count() == 0
            call_command("bins_updater", path=temp_path)
            assert Bank.objects.count() == 1
            assert Bank.objects.get(name="New Bank")

        finally:
            Path(temp_path).unlink()

    def test_command_reuses_existing_bank(self) -> None:
        """Test that command reuses existing Bank."""
        existing_bank = Bank.objects.create(name="Existing Bank")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(
                {
                    "222222": {
                        "br": 1,
                        "bn": "Existing Bank",
                        "cc": "FR",
                        "type": "credit",
                        "virtual": False,
                        "prepaid": False,
                        "raw_category": "existing_category",
                    }
                },
                f,
            )
            temp_path = f.name

        try:
            call_command("bins_updater", path=temp_path)

            # Should still have only one bank
            assert Bank.objects.count() == 1
            card_bank = PaymentCardBank.objects.get(bin=222222)
            assert card_bank.bank == existing_bank

        finally:
            Path(temp_path).unlink()

    def test_command_updates_existing_payment_card_bank(self) -> None:
        """Test that command updates existing PaymentCardBank."""
        bank = Bank.objects.create(name="Update Bank")
        existing_card_bank = PaymentCardBank.objects.create(
            bin=333333,
            bank=bank,
            card_type=1,
            card_class="credit",
            country="DE",
            is_virtual=False,
            is_prepaid=False,
            raw_category="old_category",
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(
                {
                    "333333": {
                        "br": 2,
                        "bn": "Update Bank",
                        "cc": "IT",
                        "type": "debit",
                        "virtual": True,
                        "prepaid": True,
                        "raw_category": "new_category",
                    }
                },
                f,
            )
            temp_path = f.name

        try:
            call_command("bins_updater", path=temp_path)

            existing_card_bank.refresh_from_db()
            assert existing_card_bank.card_type == 2
            assert existing_card_bank.card_class == "debit"
            assert existing_card_bank.country == "IT"
            assert existing_card_bank.is_virtual is True
            assert existing_card_bank.is_prepaid is True
            assert existing_card_bank.raw_category == "new_category"

        finally:
            Path(temp_path).unlink()

    def test_command_processes_multiple_bins(self) -> None:
        """Test that command processes multiple BINs correctly."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(
                {
                    "111111": {
                        "br": 1,
                        "bn": "Bank One",
                        "cc": "US",
                        "type": "credit",
                        "virtual": False,
                        "prepaid": False,
                        "raw_category": "category1",
                    },
                    "222222": {
                        "br": 2,
                        "bn": "Bank Two",
                        "cc": "CA",
                        "type": "debit",
                        "virtual": True,
                        "prepaid": False,
                        "raw_category": "category2",
                    },
                    "333333": {
                        "br": 3,
                        "bn": "Bank Three",
                        "cc": "GB",
                        "type": "prepaid",
                        "virtual": False,
                        "prepaid": True,
                        "raw_category": "category3",
                    },
                },
                f,
            )
            temp_path = f.name

        try:
            call_command("bins_updater", path=temp_path)

            assert Bank.objects.count() == 3
            assert PaymentCardBank.objects.count() == 3

            # Verify all BINs were processed
            assert PaymentCardBank.objects.filter(bin=111111).exists()
            assert PaymentCardBank.objects.filter(bin=222222).exists()
            assert PaymentCardBank.objects.filter(bin=333333).exists()

        finally:
            Path(temp_path).unlink()

    def test_command_file_not_found(self) -> None:
        """Test command handles file not found error."""
        with pytest.raises(FileNotFoundError):
            call_command("bins_updater", path="nonexistent_file.json")

    def test_command_invalid_json_format(self) -> None:
        """Test command handles invalid JSON format."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("invalid json content")
            temp_path = f.name

        try:
            with pytest.raises(Exception):  # ijson will raise an exception
                call_command("bins_updater", path=temp_path)
        finally:
            Path(temp_path).unlink()

    def test_command_with_empty_file(self) -> None:
        """Test command handles empty JSON file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({}, f)
            temp_path = f.name

        try:
            call_command("bins_updater", path=temp_path)

            # Should not create any records
            assert Bank.objects.count() == 0
            assert PaymentCardBank.objects.count() == 0

        finally:
            Path(temp_path).unlink()

    def test_command_with_missing_optional_fields(self) -> None:
        """Test command handles missing optional fields in JSON."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(
                {
                    "444444": {
                        "br": 1,
                        "bn": "Minimal Bank",
                        "cc": "US",
                        # Missing optional fields
                    }
                },
                f,
            )
            temp_path = f.name

        try:
            with pytest.raises(KeyError):
                call_command("bins_updater", path=temp_path)
        finally:
            Path(temp_path).unlink()

    def test_command_output_formatting(self) -> None:
        """Test command output formatting and progress reporting."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            # Create 150 records to trigger progress reporting
            data = {}
            for i in range(150):
                data[str(500000 + i)] = {
                    "br": 1,
                    "bn": f"Progress Bank {i}",
                    "cc": "US",
                    "type": "credit",
                    "virtual": False,
                    "prepaid": False,
                    "raw_category": f"progress_category_{i}",
                }
            json.dump(data, f)
            temp_path = f.name

        try:
            from io import StringIO

            out = StringIO()
            call_command("bins_updater", path=temp_path, stdout=out)

            output = out.getvalue()
            assert "Try to open file:" in output
            assert "File is opened" in output
            assert "Starting to update bins" in output
            assert "Processed 100 bins" in output
            assert "150 BINs were updated successfully" in output

        finally:
            Path(temp_path).unlink()
