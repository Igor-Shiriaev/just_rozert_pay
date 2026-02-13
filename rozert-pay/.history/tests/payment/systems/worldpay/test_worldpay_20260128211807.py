from copy import deepcopy
from unittest.mock import MagicMock

import jwt
import pytest
import requests_mock
from pydantic import SecretStr
from rest_framework.test import APIClient
from rozert_pay.common.const import TransactionStatus
from rozert_pay.payment.models import Merchant, PaymentTransaction, Wallet
from rozert_pay.payment.systems.worldpay.helpers import (
    generate_3ds_jwt,
    generate_ddc_jwt,
)
from rozert_pay.payment.systems.worldpay.worldpay_client import WorldpayClient
from rozert_pay.payment.tasks import check_status
from tests.conftest import cm_mock_check_status_task
from tests.payment.api_v1 import matchers
from tests.payment.systems.worldpay.constants import (
    MERCHANT_CODE,
    ORDER_CODE,
    WORLDPAY_DEPOSIT_REQUEST_PAYLOAD,
    get_3ds_challenge_required_response,
    get_3ds_challenge_required_response_v210,
    get_deposit_finalize_failed_response,
    get_deposit_finalize_success_response,
    get_immediate_successful_deposit_response,
    get_refused_deposit_response,
    get_refused_get_status_deposit_response,
    get_status_of_deposit_which_is_not_ready_yet_response,
    get_successful_deposit_callback_payload,
    get_successful_get_status_deposit_response,
    get_successful_get_status_deposit_response_with_commission_and_net_amounts,
    get_successful_pending_deposit_response,
)


class TestJwt:
    def test_generates_valid_ddc_jwt(self):
        jwt_issuer = SecretStr("test_issuer")
        jwt_org_unit_id = SecretStr("test_org_unit")
        jwt_mac_key = SecretStr("test_secret_key_12345")

        token = generate_ddc_jwt(jwt_issuer, jwt_org_unit_id, jwt_mac_key)

        decoded = jwt.decode(token, "test_secret_key_12345", algorithms=["HS256"])

        assert decoded["iss"] == "test_issuer"
        assert decoded["OrgUnitId"] == "test_org_unit"
        assert "jti" in decoded
        assert "iat" in decoded
        assert "exp" in decoded

    def test_custom_expiration(self):
        jwt_issuer = SecretStr("test_issuer")
        jwt_org_unit_id = SecretStr("test_org_unit")
        jwt_mac_key = SecretStr("test_secret_key_12345")

        token = generate_ddc_jwt(
            jwt_issuer, jwt_org_unit_id, jwt_mac_key, exp_seconds=3600
        )

        decoded = jwt.decode(token, "test_secret_key_12345", algorithms=["HS256"])

        assert decoded["exp"] - decoded["iat"] == 3600

    def test_generates_valid_3ds_jwt(self):
        jwt_issuer = SecretStr("test_issuer")
        jwt_org_unit_id = SecretStr("test_org_unit")
        jwt_mac_key = SecretStr("test_secret_key_12345")

        token = generate_3ds_jwt(
            jwt_issuer=jwt_issuer,
            jwt_org_unit_id=jwt_org_unit_id,
            jwt_mac_key=jwt_mac_key,
            return_url="https://example.com/return",
            acs_url="https://acs.example.com",
            cardinal_payload="test_payload",
            transaction_id="test_txn_123",
        )

        decoded = jwt.decode(token, "test_secret_key_12345", algorithms=["HS256"])

        assert decoded["iss"] == "test_issuer"
        assert decoded["OrgUnitId"] == "test_org_unit"
        assert decoded["ReturnUrl"] == "https://example.com/return"
        assert decoded["ObjectifyPayload"] is True
        assert decoded["Payload"]["ACSUrl"] == "https://acs.example.com"
        assert decoded["Payload"]["Payload"] == "test_payload"
        assert decoded["Payload"]["TransactionId"] == "test_txn_123"

    def test_unique_jti_per_call(self):
        jwt_issuer = SecretStr("test_issuer")
        jwt_org_unit_id = SecretStr("test_org_unit")
        jwt_mac_key = SecretStr("test_secret_key_12345")

        token1 = generate_3ds_jwt(
            jwt_issuer,
            jwt_org_unit_id,
            jwt_mac_key,
            "url",
            "acs",
            "payload",
            "txn1",
        )
        token2 = generate_3ds_jwt(
            jwt_issuer,
            jwt_org_unit_id,
            jwt_mac_key,
            "url",
            "acs",
            "payload",
            "txn2",
        )

        decoded1 = jwt.decode(token1, "test_secret_key_12345", algorithms=["HS256"])
        decoded2 = jwt.decode(token2, "test_secret_key_12345", algorithms=["HS256"])

        assert decoded1["jti"] != decoded2["jti"]


class TestWorldpayClientHelpers:
    def test_format_cookies_for_header_single_cookie(self):
        cookies = {"machine": "0aa20016"}
        result = WorldpayClient._format_cookies_for_header(cookies)
        assert result == "machine=0aa20016"

    def test_format_cookies_for_header_multiple_cookies(self):
        cookies = {"machine": "0aa20016", "sessionID": "1_517e8a88"}
        result = WorldpayClient._format_cookies_for_header(cookies)
        assert "machine=0aa20016" in result
        assert "sessionID=1_517e8a88" in result
        assert "; " in result

    def test_format_cookies_for_header_empty(self):
        cookies: dict[str, str] = {}
        result = WorldpayClient._format_cookies_for_header(cookies)
        assert result == ""

    @pytest.mark.parametrize(
        "phone,expected",
        [
            ("+52 55 1234 5678", "525512345678"),
            ("1-800-555-1234", "18005551234"),
            ("525512345678", "525512345678"),
        ],
    )
    def test_standardize_phone_number(self, phone: str, expected: str):
        client = MagicMock(spec=WorldpayClient)
        client.trx = MagicMock()
        client.trx.id = 1
        result = WorldpayClient._standardize_phone_number(client, phone)
        assert result == expected

    def test_standardize_phone_number_truncates_long_phone(self, disable_error_logs):
        """Phone numbers longer than 15 digits are truncated and an error is logged."""
        client = MagicMock(spec=WorldpayClient)
        client.trx = MagicMock()
        client.trx.id = 1
        result = WorldpayClient._standardize_phone_number(
            client,
            "12345678901234567890",
        )
        assert result == "123456789012345"


class TestWorldpaySystem:
    def test_deposit_validation(
        self,
        merchant_client: APIClient,
        wallet_worldpay: Wallet,
    ):
        # missing data
        response = merchant_client.post(
            path="/api/payment/v1/worldpay/deposit/",
            data={
                "amount": "2333.71",
                "currency": "MXN",
                "wallet_id": wallet_worldpay.uuid,
                "customer_id": "customer1",
                "user_data": {},
            },
            format="json",
        )
        assert response.status_code == 400
        assert response.json() == {
            "card": ["This field is required."],
            "browser_data": ["This field is required."],
            "session_id": ["This field is required."],
            "user_data": {
                "email": ["This field is required."],
                "address": ["This field is required."],
                "city": ["This field is required."],
                "post_code": ["This field is required."],
                "country": ["This field is required."],
                "ip_address": ["This field is required."],
                "phone": ["This field is required."],
            },
        }

    def test_deposit_success(
        self,
        merchant_client: APIClient,
        merchant: Merchant,
        wallet_worldpay: Wallet,
        disable_error_logs,
    ):
        with requests_mock.Mocker() as m:
            m.post(
                "https://secure-test.worldpay.com/jsp/merchant/xml/paymentService.jsp",
                [
                    {
                        "text": get_successful_pending_deposit_response(
                            MERCHANT_CODE, ORDER_CODE
                        ),
                        "headers": {"Content-Type": "text/plain"},
                    },
                    {
                        "text": get_successful_get_status_deposit_response(
                            MERCHANT_CODE, ORDER_CODE
                        ),
                        "headers": {"Content-Type": "text/plain"},
                    },
                ],
            )

            request_payload = deepcopy(WORLDPAY_DEPOSIT_REQUEST_PAYLOAD)
            request_payload["wallet_id"] = str(wallet_worldpay.uuid)

            response = merchant_client.post(
                path="/api/payment/v1/worldpay/deposit/",
                data=request_payload,
                format="json",
            )
            assert response.status_code == 201
            assert response.json()["status"] == "pending"

            trx = PaymentTransaction.objects.get()

            assert trx.id_in_payment_system == ORDER_CODE
            assert trx.status == TransactionStatus.SUCCESS

            response = merchant_client.get(
                f"/api/payment/v1/transaction/{trx.uuid}/",
            )
            assert response.status_code == 200
            assert response.json() == matchers.DictContains(
                {
                    "amount": "2333.71",
                    "currency": "MXN",
                    "status": "success",
                    "type": "deposit",
                    "user_data": matchers.DictContains(
                        {
                            "post_code": "12345",
                            "city": "Mexico City",
                            "country": "MX",
                        }
                    ),
                }
            )

            trx.refresh_from_db()
            assert trx.status == TransactionStatus.SUCCESS

    def test_deposit_immediate_success(
        self,
        merchant_client: APIClient,
        merchant: Merchant,
        wallet_worldpay: Wallet,
        disable_error_logs,
    ):
        with requests_mock.Mocker() as m:
            m.post(
                "https://secure-test.worldpay.com/jsp/merchant/xml/paymentService.jsp",
                [
                    {
                        "text": get_immediate_successful_deposit_response(
                            MERCHANT_CODE, ORDER_CODE
                        ),
                        "headers": {"Content-Type": "text/plain"},
                    },
                    {
                        "text": get_successful_get_status_deposit_response(
                            MERCHANT_CODE, ORDER_CODE
                        ),
                        "headers": {"Content-Type": "text/plain"},
                    },
                ],
            )

            request_payload = deepcopy(WORLDPAY_DEPOSIT_REQUEST_PAYLOAD)
            request_payload["wallet_id"] = str(wallet_worldpay.uuid)

            response = merchant_client.post(
                path="/api/payment/v1/worldpay/deposit/",
                data=request_payload,
                format="json",
            )
            assert response.status_code == 201
            assert response.json()["status"] == "pending"

            trx = PaymentTransaction.objects.get()

            assert trx.id_in_payment_system == ORDER_CODE
            assert trx.status == TransactionStatus.SUCCESS

            response = merchant_client.get(
                f"/api/payment/v1/transaction/{trx.uuid}/",
            )
            assert response.status_code == 200
            assert response.json() == matchers.DictContains(
                {
                    "amount": "2333.71",
                    "currency": "MXN",
                    "status": "success",
                    "type": "deposit",
                    "user_data": matchers.DictContains(
                        {
                            "post_code": "12345",
                            "city": "Mexico City",
                            "country": "MX",
                        }
                    ),
                }
            )

            trx.refresh_from_db()
            assert trx.status == TransactionStatus.SUCCESS

    def test_deposit_failed_instantly(
        self,
        merchant_client: APIClient,
        merchant: Merchant,
        wallet_worldpay: Wallet,
        disable_error_logs,
    ):
        with requests_mock.Mocker() as m:
            m.post(
                "https://secure-test.worldpay.com/jsp/merchant/xml/paymentService.jsp",
                [
                    {
                        "text": get_refused_deposit_response(MERCHANT_CODE, ORDER_CODE),
                        "headers": {"Content-Type": "text/plain"},
                    },
                    {
                        "text": get_refused_get_status_deposit_response(
                            MERCHANT_CODE, ORDER_CODE
                        ),
                        "headers": {"Content-Type": "text/plain"},
                    },
                ],
            )

            request_payload = deepcopy(WORLDPAY_DEPOSIT_REQUEST_PAYLOAD)
            request_payload["wallet_id"] = str(wallet_worldpay.uuid)

            response = merchant_client.post(
                path="/api/payment/v1/worldpay/deposit/",
                data=request_payload,
                format="json",
            )
            assert response.status_code == 201
            assert response.json()["status"] == "pending"

            trx = PaymentTransaction.objects.get()

            assert trx.id_in_payment_system == ORDER_CODE
            assert trx.status == TransactionStatus.FAILED

            response = merchant_client.get(
                f"/api/payment/v1/transaction/{trx.uuid}/",
            )
            assert response.status_code == 200
            assert response.json() == matchers.DictContains(
                {
                    "amount": "2333.71",
                    "currency": "MXN",
                    "status": "failed",
                    "type": "deposit",
                    "user_data": matchers.DictContains(
                        {
                            "post_code": "12345",
                            "city": "Mexico City",
                            "country": "MX",
                        }
                    ),
                }
            )

            trx.refresh_from_db()
            assert trx.status == TransactionStatus.FAILED

    def test_deposit_failed_not_instantly(
        self,
        merchant_client: APIClient,
        merchant: Merchant,
        wallet_worldpay: Wallet,
        disable_error_logs,
    ):
        with requests_mock.Mocker() as m:
            m.post(
                "https://secure-test.worldpay.com/jsp/merchant/xml/paymentService.jsp",
                [
                    {
                        "text": get_successful_pending_deposit_response(
                            MERCHANT_CODE, ORDER_CODE
                        ),
                        "headers": {"Content-Type": "text/plain"},
                    },
                    {
                        "text": get_refused_get_status_deposit_response(
                            MERCHANT_CODE, ORDER_CODE
                        ),
                        "headers": {"Content-Type": "text/plain"},
                    },
                ],
            )

            request_payload = deepcopy(WORLDPAY_DEPOSIT_REQUEST_PAYLOAD)
            request_payload["wallet_id"] = str(wallet_worldpay.uuid)

            response = merchant_client.post(
                path="/api/payment/v1/worldpay/deposit/",
                data=request_payload,
                format="json",
            )
            assert response.status_code == 201
            assert response.json()["status"] == "pending"

            trx = PaymentTransaction.objects.get()

            assert trx.id_in_payment_system == ORDER_CODE
            assert trx.status == TransactionStatus.FAILED

            response = merchant_client.get(
                f"/api/payment/v1/transaction/{trx.uuid}/",
            )
            assert response.status_code == 200
            assert response.json() == matchers.DictContains(
                {
                    "amount": "2333.71",
                    "currency": "MXN",
                    "status": "failed",
                    "type": "deposit",
                    "user_data": matchers.DictContains(
                        {
                            "post_code": "12345",
                            "city": "Mexico City",
                            "country": "MX",
                        }
                    ),
                }
            )

            trx.refresh_from_db()
            assert trx.status == TransactionStatus.FAILED

    def test_deposit_not_ready_yet(
        self,
        merchant_client: APIClient,
        merchant: Merchant,
        wallet_worldpay: Wallet,
        disable_error_logs,
    ):
        with requests_mock.Mocker() as m:
            m.post(
                "https://secure-test.worldpay.com/jsp/merchant/xml/paymentService.jsp",
                [
                    {
                        "text": get_successful_pending_deposit_response(
                            MERCHANT_CODE, ORDER_CODE
                        ),
                        "headers": {"Content-Type": "text/plain"},
                    },
                    {
                        "text": get_status_of_deposit_which_is_not_ready_yet_response(
                            MERCHANT_CODE, ORDER_CODE
                        ),
                        "headers": {"Content-Type": "text/plain"},
                    },
                    {
                        "text": get_successful_get_status_deposit_response(
                            MERCHANT_CODE, ORDER_CODE
                        ),
                        "headers": {"Content-Type": "text/plain"},
                    },
                ],
            )

            request_payload = deepcopy(WORLDPAY_DEPOSIT_REQUEST_PAYLOAD)
            request_payload["wallet_id"] = str(wallet_worldpay.uuid)

            response = merchant_client.post(
                path="/api/payment/v1/worldpay/deposit/",
                data=request_payload,
                format="json",
            )
            assert response.status_code == 201
            assert response.json()["status"] == "pending"

            trx = PaymentTransaction.objects.get()

            assert trx.id_in_payment_system == ORDER_CODE
            assert trx.status == TransactionStatus.PENDING

            check_status.delay(trx.id)

            response = merchant_client.get(
                f"/api/payment/v1/transaction/{trx.uuid}/",
            )
            assert response.status_code == 200

            trx.refresh_from_db()
            assert trx.status == TransactionStatus.SUCCESS

    def test_callback(
        self,
        merchant_client: APIClient,
        merchant: Merchant,
        wallet_worldpay: Wallet,
        disable_error_logs,
    ):
        with requests_mock.Mocker() as m:
            m.post(
                "https://secure-test.worldpay.com/jsp/merchant/xml/paymentService.jsp",
                [
                    {
                        "text": get_successful_pending_deposit_response(
                            MERCHANT_CODE,
                            ORDER_CODE,
                        ),
                        "headers": {"Content-Type": "text/plain"},
                    },
                    {
                        "text": get_successful_pending_deposit_response(
                            MERCHANT_CODE,
                            ORDER_CODE,
                        ),
                        "headers": {"Content-Type": "text/plain"},
                    },
                    {
                        "text": get_successful_get_status_deposit_response(
                            MERCHANT_CODE, ORDER_CODE
                        ),
                        "headers": {"Content-Type": "text/plain"},
                    },
                ],
            )

            request_payload = deepcopy(WORLDPAY_DEPOSIT_REQUEST_PAYLOAD)
            request_payload["wallet_id"] = str(wallet_worldpay.uuid)

            response = merchant_client.post(
                path="/api/payment/v1/worldpay/deposit/",
                data=request_payload,
                format="json",
            )
            assert response.status_code == 201
            assert response.json()["status"] == "pending"

            trx = PaymentTransaction.objects.get()

            assert trx.id_in_payment_system == ORDER_CODE
            assert trx.status == TransactionStatus.PENDING

            # Callback
            response = merchant_client.post(
                path="/api/payment/v1/callback/worldpay/",
                data=get_successful_deposit_callback_payload(MERCHANT_CODE, ORDER_CODE),
                content_type="text/plain",
            )
            assert response.status_code == 200

            trx.refresh_from_db()
            assert trx.status == TransactionStatus.SUCCESS

    def test_commission_and_net_amounts(
        self,
        merchant_client: APIClient,
        merchant: Merchant,
        wallet_worldpay: Wallet,
        disable_error_logs,
    ):
        with requests_mock.Mocker() as m:
            m.post(
                "https://secure-test.worldpay.com/jsp/merchant/xml/paymentService.jsp",
                [
                    {
                        "text": get_successful_pending_deposit_response(
                            MERCHANT_CODE,
                            ORDER_CODE,
                        ),
                        "headers": {"Content-Type": "text/plain"},
                    },
                    {
                        "text": get_successful_get_status_deposit_response_with_commission_and_net_amounts(
                            MERCHANT_CODE,
                            ORDER_CODE,
                        ),
                        "headers": {"Content-Type": "text/plain"},
                    },
                ],
            )

            request_payload = deepcopy(WORLDPAY_DEPOSIT_REQUEST_PAYLOAD)
            request_payload["wallet_id"] = str(wallet_worldpay.uuid)

            response = merchant_client.post(
                path="/api/payment/v1/worldpay/deposit/",
                data=request_payload,
                format="json",
            )
            assert response.status_code == 201
            assert response.json()["status"] == "pending"

            trx = PaymentTransaction.objects.get()

            assert trx.id_in_payment_system == ORDER_CODE
            assert trx.status == TransactionStatus.SUCCESS

            response = merchant_client.get(
                f"/api/payment/v1/transaction/{trx.uuid}/",
            )
            assert response.status_code == 200
            assert response.json() == matchers.DictContains(
                {
                    "amount": "2333.71",
                    "currency": "MXN",
                    "status": "success",
                    "type": "deposit",
                    "user_data": matchers.DictContains(
                        {
                            "post_code": "12345",
                            "city": "Mexico City",
                            "country": "MX",
                        }
                    ),
                }
            )

            trx.refresh_from_db()
            assert trx.status == TransactionStatus.SUCCESS

    def test_deposit_with_3ds_challenge(
        self,
        merchant_client: APIClient,
        merchant: Merchant,
        wallet_worldpay: Wallet,
    ):
        with requests_mock.Mocker() as m:
            m.post(
                "https://secure-test.worldpay.com/jsp/merchant/xml/paymentService.jsp",
                [
                    {
                        "text": get_3ds_challenge_required_response(
                            MERCHANT_CODE,
                            ORDER_CODE,
                        ),
                        "headers": {"Content-Type": "text/plain"},
                        "cookies": {"machine": "0aa20016", "sessionID": "1_517e8a88"},
                    },
                    {
                        "text": get_deposit_finalize_success_response(
                            MERCHANT_CODE,
                            ORDER_CODE,
                        ),
                        "headers": {"Content-Type": "text/plain"},
                    },
                    {
                        "text": get_successful_get_status_deposit_response(
                            MERCHANT_CODE,
                            ORDER_CODE,
                        ),
                        "headers": {"Content-Type": "text/plain"},
                    },
                ],
            )

            request_payload = deepcopy(WORLDPAY_DEPOSIT_REQUEST_PAYLOAD)
            request_payload["wallet_id"] = str(wallet_worldpay.uuid)

            with cm_mock_check_status_task():
                response = merchant_client.post(
                    path="/api/payment/v1/worldpay/deposit/",
                    data=request_payload,
                    format="json",
                )
            assert response.status_code == 201
            response_data = response.json()
            assert response_data["status"] == "pending"

            trx = PaymentTransaction.objects.get()
            assert trx.status == TransactionStatus.PENDING
            assert trx.form is not None
            assert trx.form.method == "post"
            assert "JWT" in trx.form.fields
            assert trx.extra.get("worldpay_cookies") == {
                "machine": "0aa20016",
                "sessionID": "1_517e8a88",
            }

    def test_deposit_with_3ds_challenge_v210_uses_fixed_iframe_size(
        self,
        merchant_client: APIClient,
        merchant: Merchant,
        wallet_worldpay: Wallet,
    ):
        with requests_mock.Mocker() as m:
            m.post(
                "https://secure-test.worldpay.com/jsp/merchant/xml/paymentService.jsp",
                [
                    {
                        "text": get_3ds_challenge_required_response_v210(
                            MERCHANT_CODE, ORDER_CODE
                        ),
                        "headers": {"Content-Type": "text/plain"},
                        "cookies": {"machine": "test"},
                    },
                ],
            )

            request_payload = deepcopy(WORLDPAY_DEPOSIT_REQUEST_PAYLOAD)
            request_payload["wallet_id"] = str(wallet_worldpay.uuid)

            with cm_mock_check_status_task():
                response = merchant_client.post(
                    path="/api/payment/v1/worldpay/deposit/",
                    data=request_payload,
                    format="json",
                )
            assert response.status_code == 201

            trx = PaymentTransaction.objects.get()
            assert trx.form is not None
            # For 3DS v2.1.0, iframe size should be fixed 390x400
            assert trx.form.fields["iframeHeight"] == 390
            assert trx.form.fields["iframeWidth"] == 400

    def test_ddc_jwt_endpoint(
        self,
        merchant_client: APIClient,
        wallet_worldpay: Wallet,
    ):
        response = merchant_client.get(
            path="/api/payment/v1/worldpay/ddc-jwt/",
        )
        assert response.status_code == 200
        response_data = response.json()
        assert "jwt_token" in response_data

        # Verify JWT is valid and contains expected claims
        token = response_data["jwt_token"]
        decoded = jwt.decode(token, "fake_jwt_mac_key", algorithms=["HS256"])
        assert decoded["iss"] == "fake_jwt_issuer"
        assert decoded["OrgUnitId"] == "fake_jwt_org_unit_id"

    def test_ddc_jwt_endpoint_wallet_not_found(
        self,
        merchant_client: APIClient,
    ):
        # No wallet_worldpay fixture - merchant has no Worldpay wallet
        response = merchant_client.get(
            path="/api/payment/v1/worldpay/ddc-jwt/",
        )
        assert response.status_code == 404

    def test_deposit_finalize_after_3ds_redirect(
        self,
        client: APIClient,
        merchant_client: APIClient,
        wallet_worldpay: Wallet,
    ):
        """Test deposit_finalize flow through redirect endpoint after 3DS challenge."""
        with requests_mock.Mocker() as m:
            m.post(
                "https://secure-test.worldpay.com/jsp/merchant/xml/paymentService.jsp",
                [
                    {
                        "text": get_3ds_challenge_required_response(
                            MERCHANT_CODE,
                            ORDER_CODE,
                        ),
                        "headers": {"Content-Type": "text/plain"},
                        "cookies": {"machine": "0aa20016", "sessionID": "1_517e8a88"},
                    },
                    {
                        "text": get_deposit_finalize_success_response(
                            MERCHANT_CODE,
                            ORDER_CODE,
                        ),
                        "headers": {"Content-Type": "text/plain"},
                    },
                    {
                        "text": get_successful_get_status_deposit_response(
                            MERCHANT_CODE,
                            ORDER_CODE,
                        ),
                        "headers": {"Content-Type": "text/plain"},
                    },
                ],
            )

            request_payload = deepcopy(WORLDPAY_DEPOSIT_REQUEST_PAYLOAD)
            request_payload["wallet_id"] = str(wallet_worldpay.uuid)

            with cm_mock_check_status_task():
                response = merchant_client.post(
                    path="/api/payment/v1/worldpay/deposit/",
                    data=request_payload,
                    format="json",
                )
            assert response.status_code == 201

            trx = PaymentTransaction.objects.get()
            assert trx.status == TransactionStatus.PENDING
            assert trx.extra.get("worldpay_cookies") == {
                "machine": "0aa20016",
                "sessionID": "1_517e8a88",
            }

            # Simulate customer returning after 3DS challenge
            redirect_response = client.post(
                f"/api/payment/v1/redirect/worldpay/?transaction_id={trx.uuid}",
            )
            assert redirect_response.status_code == 302
            assert redirect_response.headers["Location"] == trx.redirect_url

            # Check that finalization was called and status checks were scheduled
            trx.refresh_from_db()
            assert trx.extra.get("is_finalization_performed") is True

    def test_deposit_finalize_failure(
        self,
        client: APIClient,
        merchant_client: APIClient,
        wallet_worldpay: Wallet,
    ):
        """Test deposit_finalize failure (e.g., insufficient funds after 3DS)."""
        with requests_mock.Mocker() as m:
            m.post(
                "https://secure-test.worldpay.com/jsp/merchant/xml/paymentService.jsp",
                [
                    {
                        "text": get_3ds_challenge_required_response(
                            MERCHANT_CODE,
                            ORDER_CODE,
                        ),
                        "headers": {"Content-Type": "text/plain"},
                        "cookies": {"machine": "0aa20016", "sessionID": "1_517e8a88"},
                    },
                    {
                        "text": get_deposit_finalize_failed_response(
                            MERCHANT_CODE,
                            ORDER_CODE,
                        ),
                        "headers": {"Content-Type": "text/plain"},
                    },
                ],
            )

            request_payload = deepcopy(WORLDPAY_DEPOSIT_REQUEST_PAYLOAD)
            request_payload["wallet_id"] = str(wallet_worldpay.uuid)

            with cm_mock_check_status_task():
                response = merchant_client.post(
                    path="/api/payment/v1/worldpay/deposit/",
                    data=request_payload,
                    format="json",
                )
            assert response.status_code == 201

            trx = PaymentTransaction.objects.get()
            assert trx.status == TransactionStatus.PENDING

            # Simulate customer returning after 3DS challenge
            redirect_response = client.post(
                f"/api/payment/v1/redirect/worldpay/?transaction_id={trx.uuid}",
            )
            assert redirect_response.status_code == 302

            trx.refresh_from_db()
            assert trx.status == TransactionStatus.FAILED
            assert trx.decline_code == "51"
            assert trx.decline_reason == "INSUFFICIENT FUNDS"

    def test_deposit_finalize_3ds_cancelled(
        self,
        client: APIClient,
        merchant_client: APIClient,
        wallet_worldpay: Wallet,
    ):
        """Test deposit_finalize when user cancels 3DS challenge - status stays PENDING."""
        with requests_mock.Mocker() as m:
            m.post(
                "https://secure-test.worldpay.com/jsp/merchant/xml/paymentService.jsp",
                [
                    {
                        "text": get_3ds_challenge_required_response(
                            MERCHANT_CODE,
                            ORDER_CODE,
                        ),
                        "headers": {"Content-Type": "text/plain"},
                        "cookies": {"machine": "0aa20016", "sessionID": "1_517e8a88"},
                    },
                    {
                        # User cancelled 3DS - same challengeRequired response returned
                        "text": get_3ds_challenge_required_response(
                            MERCHANT_CODE,
                            ORDER_CODE,
                        ),
                        "headers": {"Content-Type": "text/plain"},
                    },
                ],
            )

            request_payload = deepcopy(WORLDPAY_DEPOSIT_REQUEST_PAYLOAD)
            request_payload["wallet_id"] = str(wallet_worldpay.uuid)

            with cm_mock_check_status_task():
                response = merchant_client.post(
                    path="/api/payment/v1/worldpay/deposit/",
                    data=request_payload,
                    format="json",
                )
            assert response.status_code == 201

            trx = PaymentTransaction.objects.get()
            assert trx.status == TransactionStatus.PENDING

            # Simulate customer returning after cancelling 3DS challenge
            redirect_response = client.post(
                f"/api/payment/v1/redirect/worldpay/?transaction_id={trx.uuid}",
            )
            assert redirect_response.status_code == 302

            trx.refresh_from_db()
            assert trx.status == TransactionStatus.PENDING


class TestWorldpaySandboxSystem:
    def test_deposit_success(
        self,
        merchant_client: APIClient,
        merchant: Merchant,
        wallet_worldpay: Wallet,
        disable_error_logs,
    ):
        with requests_mock.Mocker() as m:
            m.post(
                "https://secure-test.worldpay.com/jsp/merchant/xml/paymentService.jsp",
                [
                    {
                        "text": get_successful_pending_deposit_response(
                            MERCHANT_CODE, ORDER_CODE
                        ),
                        "headers": {"Content-Type": "text/plain"},
                    },
                    {
                        "text": get_successful_get_status_deposit_response(
                            MERCHANT_CODE, ORDER_CODE
                        ),
                        "headers": {"Content-Type": "text/plain"},
                    },
                ],
            )

            request_payload = deepcopy(WORLDPAY_DEPOSIT_REQUEST_PAYLOAD)
            request_payload["wallet_id"] = str(wallet_worldpay.uuid)

            response = merchant_client.post(
                path="/api/payment/v1/worldpay/deposit/",
                data=request_payload,
                format="json",
            )
            assert response.status_code == 201
            assert response.json()["status"] == "pending"

            trx = PaymentTransaction.objects.get()

            assert trx.id_in_payment_system == ORDER_CODE
            assert trx.status == TransactionStatus.SUCCESS

            response = merchant_client.get(
                f"/api/payment/v1/transaction/{trx.uuid}/",
            )
            assert response.status_code == 200
            assert response.json() == matchers.DictContains(
                {
                    "amount": "2333.71",
                    "currency": "MXN",
                    "status": "success",
                    "type": "deposit",
                    "user_data": matchers.DictContains(
                        {
                            "post_code": "12345",
                            "city": "Mexico City",
                            "country": "MX",
                        }
                    ),
                }
            )

            trx.refresh_from_db()
            assert trx.status == TransactionStatus.SUCCESS

    def test_deposit_failed_instantly(
        self,
        merchant_client: APIClient,
        merchant: Merchant,
        wallet_worldpay: Wallet,
        disable_error_logs,
    ):
        with requests_mock.Mocker() as m:
            m.post(
                "https://secure-test.worldpay.com/jsp/merchant/xml/paymentService.jsp",
                [
                    {
                        "text": get_refused_deposit_response(MERCHANT_CODE, ORDER_CODE),
                        "headers": {"Content-Type": "text/plain"},
                    },
                    {
                        "text": get_refused_get_status_deposit_response(
                            MERCHANT_CODE, ORDER_CODE
                        ),
                        "headers": {"Content-Type": "text/plain"},
                    },
                ],
            )

            request_payload = deepcopy(WORLDPAY_DEPOSIT_REQUEST_PAYLOAD)
            request_payload["wallet_id"] = str(wallet_worldpay.uuid)

            response = merchant_client.post(
                path="/api/payment/v1/worldpay/deposit/",
                data=request_payload,
                format="json",
            )
            assert response.status_code == 201
            assert response.json()["status"] == "pending"

            trx = PaymentTransaction.objects.get()

            assert trx.id_in_payment_system == ORDER_CODE
            assert trx.status == TransactionStatus.FAILED

            response = merchant_client.get(
                f"/api/payment/v1/transaction/{trx.uuid}/",
            )
            assert response.status_code == 200
            assert response.json() == matchers.DictContains(
                {
                    "amount": "2333.71",
                    "currency": "MXN",
                    "status": "failed",
                    "type": "deposit",
                    "user_data": matchers.DictContains(
                        {
                            "post_code": "12345",
                            "city": "Mexico City",
                            "country": "MX",
                        }
                    ),
                }
            )

            trx.refresh_from_db()
            assert trx.status == TransactionStatus.FAILED

    def test_deposit_failed_not_instantly(
        self,
        merchant_client: APIClient,
        merchant: Merchant,
        wallet_worldpay: Wallet,
        disable_error_logs,
    ):
        with requests_mock.Mocker() as m:
            m.post(
                "https://secure-test.worldpay.com/jsp/merchant/xml/paymentService.jsp",
                [
                    {
                        "text": get_successful_pending_deposit_response(
                            MERCHANT_CODE, ORDER_CODE
                        ),
                        "headers": {"Content-Type": "text/plain"},
                    },
                    {
                        "text": get_refused_get_status_deposit_response(
                            MERCHANT_CODE, ORDER_CODE
                        ),
                        "headers": {"Content-Type": "text/plain"},
                    },
                ],
            )

            request_payload = deepcopy(WORLDPAY_DEPOSIT_REQUEST_PAYLOAD)
            request_payload["wallet_id"] = str(wallet_worldpay.uuid)

            response = merchant_client.post(
                path="/api/payment/v1/worldpay/deposit/",
                data=request_payload,
                format="json",
            )
            assert response.status_code == 201
            assert response.json()["status"] == "pending"

            trx = PaymentTransaction.objects.get()

            assert trx.id_in_payment_system == ORDER_CODE
            assert trx.status == TransactionStatus.FAILED

            response = merchant_client.get(
                f"/api/payment/v1/transaction/{trx.uuid}/",
            )
            assert response.status_code == 200
            assert response.json() == matchers.DictContains(
                {
                    "amount": "2333.71",
                    "currency": "MXN",
                    "status": "failed",
                    "type": "deposit",
                    "user_data": matchers.DictContains(
                        {
                            "post_code": "12345",
                            "city": "Mexico City",
                            "country": "MX",
                        }
                    ),
                }
            )

            trx.refresh_from_db()
            assert trx.status == TransactionStatus.FAILED
