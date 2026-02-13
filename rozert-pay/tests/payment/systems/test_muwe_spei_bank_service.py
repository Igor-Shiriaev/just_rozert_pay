import json

import pytest
import requests_mock
from rozert_pay.payment.systems.muwe_spei import bank_service, muwe_spei_helpers
from rozert_pay.payment.systems.muwe_spei.models import MuweSpeiBank


@pytest.mark.django_db
class TestFetchBankList:
    def test_fetch_bank_list_success(self):
        base_api_url = "https://test.sipelatam.mx"
        mch_id = "fake_mch_id"
        api_key = "fake_api_key"

        banks_data = {
            "40014": "SANTANDER",
            "40012": "BBVA BANCOMER",
            "40002": "BANAMEX",
        }

        response_payload = {
            "resCode": "SUCCESS",
            "mchId": mch_id,
            "nonceStr": "test123",
            "banks": json.dumps(banks_data),
        }
        response_payload["sign"] = muwe_spei_helpers.calculate_signature(
            response_payload, api_key
        )

        with requests_mock.Mocker() as m:
            m.post(
                f"{base_api_url}/common/query/bank",
                json=response_payload,
            )

            result = bank_service.fetch_bank_list(
                base_api_url=base_api_url,
                mch_id=mch_id,
                api_key=api_key,
            )

            assert result == banks_data


@pytest.mark.django_db
class TestSyncBankList:
    def test_sync_bank_list_create_new_banks(self):
        base_api_url = "https://test.sipelatam.mx"
        mch_id = "fake_mch_id"
        api_key = "fake_api_key"

        banks_data = {
            "40014": "SANTANDER",
            "40012": "BBVA BANCOMER",
        }

        response_payload = {
            "resCode": "SUCCESS",
            "mchId": mch_id,
            "nonceStr": "test123",
            "banks": json.dumps(banks_data),
        }
        response_payload["sign"] = muwe_spei_helpers.calculate_signature(
            response_payload, api_key
        )

        with requests_mock.Mocker() as m:
            m.post(
                f"{base_api_url}/common/query/bank",
                json=response_payload,
            )

            result = bank_service.sync_bank_list(
                base_api_url=base_api_url,
                mch_id=mch_id,
                api_key=api_key,
            )

            assert result is True
            assert MuweSpeiBank.objects.count() == 2

            santander = MuweSpeiBank.objects.get(code="40014")
            assert santander.name == "SANTANDER"
            assert santander.is_active is True

            bbva = MuweSpeiBank.objects.get(code="40012")
            assert bbva.name == "BBVA BANCOMER"
            assert bbva.is_active is True

    def test_sync_bank_list_update_existing_banks(self):
        MuweSpeiBank.objects.create(
            code="40014",
            name="OLD_NAME",
            is_active=True,
        )

        base_api_url = "https://test.sipelatam.mx"
        mch_id = "fake_mch_id"
        api_key = "fake_api_key"

        banks_data = {
            "40014": "SANTANDER",  # New name
        }

        response_payload = {
            "resCode": "SUCCESS",
            "mchId": mch_id,
            "nonceStr": "test123",
            "banks": json.dumps(banks_data),
        }
        response_payload["sign"] = muwe_spei_helpers.calculate_signature(
            response_payload, api_key
        )

        with requests_mock.Mocker() as m:
            m.post(
                f"{base_api_url}/common/query/bank",
                json=response_payload,
            )

            result = bank_service.sync_bank_list(
                base_api_url=base_api_url,
                mch_id=mch_id,
                api_key=api_key,
            )

            assert result is True
            assert MuweSpeiBank.objects.count() == 1

            santander = MuweSpeiBank.objects.get(code="40014")
            assert santander.name == "SANTANDER"  # Updated
            assert santander.is_active is True

    def test_sync_bank_list_deactivate_removed_banks(self):
        MuweSpeiBank.objects.create(code="40014", name="SANTANDER", is_active=True)
        MuweSpeiBank.objects.create(code="40012", name="BBVA", is_active=True)
        MuweSpeiBank.objects.create(code="99999", name="OLD_BANK", is_active=True)

        base_api_url = "https://test.sipelatam.mx"
        mch_id = "fake_mch_id"
        api_key = "fake_api_key"

        banks_data = {
            "40014": "SANTANDER",
            "40012": "BBVA BANCOMER",
        }

        response_payload = {
            "resCode": "SUCCESS",
            "mchId": mch_id,
            "nonceStr": "test123",
            "banks": json.dumps(banks_data),
        }
        response_payload["sign"] = muwe_spei_helpers.calculate_signature(
            response_payload, api_key
        )

        with requests_mock.Mocker() as m:
            m.post(
                f"{base_api_url}/common/query/bank",
                json=response_payload,
            )

            result = bank_service.sync_bank_list(
                base_api_url=base_api_url,
                mch_id=mch_id,
                api_key=api_key,
            )

            assert result is True
            assert MuweSpeiBank.objects.count() == 3

            # Active banks
            santander = MuweSpeiBank.objects.get(code="40014")
            assert santander.is_active is True

            bbva = MuweSpeiBank.objects.get(code="40012")
            assert bbva.is_active is True

            # Deactivated bank
            old_bank = MuweSpeiBank.objects.get(code="99999")
            assert old_bank.is_active is False


@pytest.mark.django_db
class TestGetBankCodeByClabe:
    def test_matching_bank_found(self):
        MuweSpeiBank.objects.create(code="40002", name="BANAMEX", is_active=True)

        result = bank_service.get_bank_code_by_clabe("002115016003269411")
        assert result == "40002"

    def test_no_matching_bank_raises(self):
        with pytest.raises(AssertionError, match="Could not determine bankCode"):
            bank_service.get_bank_code_by_clabe("002115016003269411")

    def test_inactive_bank_raises(self):
        MuweSpeiBank.objects.create(code="40002", name="BANAMEX", is_active=False)

        with pytest.raises(AssertionError, match="Could not determine bankCode"):
            bank_service.get_bank_code_by_clabe("002115016003269411")

    def test_invalid_clabe_raises_value_error(self):
        with pytest.raises(ValueError):
            bank_service.get_bank_code_by_clabe("00211501")

        with pytest.raises(ValueError):
            bank_service.get_bank_code_by_clabe("abcdefghijklmnopqr")


@pytest.mark.django_db
@pytest.mark.usefixtures("disable_cache")
class TestGetBankNameByCode:
    def test_get_bank_name_by_code_exists(self):
        MuweSpeiBank.objects.create(
            code="40014",
            name="SANTANDER",
            is_active=True,
        )

        result = bank_service.get_bank_name_by_code("40014")
        assert result == "SANTANDER"

    def test_get_bank_name_by_code_not_found(self):
        result = bank_service.get_bank_name_by_code("99999")
        assert result is None

    def test_get_bank_name_by_code_inactive(self, disable_cache):
        MuweSpeiBank.objects.create(
            code="40014",
            name="SANTANDER",
            is_active=False,
        )

        result = bank_service.get_bank_name_by_code("40014")
        assert result is None
