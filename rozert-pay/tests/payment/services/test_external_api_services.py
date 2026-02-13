from unittest import mock

import pytest
import requests_mock
from rozert_pay.payment.models import PaymentTransactionEventLog
from rozert_pay.payment.services import external_api_services
from tests.factories import PaymentTransactionFactory


@pytest.mark.django_db
class TestExternalApiSession:
    def test_write_error_request(self):
        with requests_mock.Mocker() as m:
            m.post("http://test", status_code=500, json={"error": "error"})

            trx = PaymentTransactionFactory.create()
            sess = external_api_services.get_external_api_session(
                trx_id=trx.id,
                timeout=10,
            )
            sess.post("http://test")

            assert PaymentTransactionEventLog.objects.count() == 1
            item = PaymentTransactionEventLog.objects.get()
            assert item.event_type == "external_api_request"
            assert item.extra == {
                "duration": mock.ANY,
                "error": None,
                "request": {
                    "data": None,
                    "headers": None,
                    "method": "POST",
                    "url": "http://test",
                },
                "response": {"status_code": 500, "text": {"error": "error"}},
            }

    def test_write_connection_error_request(self):
        with requests_mock.Mocker() as m:
            # imitate connection error
            m.post(
                "http://test",
                exc=ConnectionError("OLALA!"),
            )

            trx = PaymentTransactionFactory.create()
            sess = external_api_services.get_external_api_session(
                trx_id=trx.id,
                timeout=10,
            )
            with pytest.raises(ConnectionError):
                sess.post("http://test")

            assert PaymentTransactionEventLog.objects.count() == 1
            item = PaymentTransactionEventLog.objects.get()
            assert item.event_type == "external_api_request"
            assert item.extra == {
                "duration": mock.ANY,
                "error": {"cls": "ConnectionError", "data": "{}", "message": "OLALA!"},
                "request": {
                    "data": None,
                    "headers": None,
                    "method": "POST",
                    "url": "http://test",
                },
                "response": None,
            }
