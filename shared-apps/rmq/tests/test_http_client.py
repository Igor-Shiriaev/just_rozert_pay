from unittest import mock

import pytest
import requests
import requests_mock

from rmq.http_client import RabbitHTTPClient


class TestRabbitHTTPClient:
    @pytest.fixture
    def client(self):
        return RabbitHTTPClient(
            host='example.com', port=15672, username='user', password='pass'
        )

    def test_set_policy(self, client):
        with requests_mock.Mocker() as mocker:
            mock_adapter = mocker.put(
                'http://example.com:15672/api/policies/%2Fvhost/policy-name'
            )

            client.set_policy(
                policy_name='policy-name',
                resources_pattern='pattern',
                vhost='/vhost',
                policy_definition={'message-ttl': 10000},
                apply_to='queues',
            )

            assert mock_adapter.last_request.json() == {
                'apply-to': 'queues',
                'definition': {'message-ttl': 10000},
                'pattern': 'pattern',
            }

    @mock.patch('rmq.http_client.logger')
    def test_set_policy_when_http_error(self, logger_mock, client):
        with requests_mock.Mocker() as mocker:
            mocker.put(
                'http://example.com:15672/api/policies/%2Fvhost/policy-name',
                status_code=500,
                text='server-error',
            )

            with pytest.raises(requests.exceptions.HTTPError):
                client.set_policy(
                    policy_name='policy-name',
                    resources_pattern='pattern',
                    vhost='/vhost',
                    policy_definition={'message-ttl': 10000},
                    apply_to='queues',
                )

        logger_mock.error.assert_called_once_with(
            'error response from RMQ HTTP API', extra={'_response_text': 'server-error'}
        )

    def test_get_queues_info(self, client):
        with requests_mock.Mocker() as mocker:
            mocker.get('http://example.com:15672/api/queues/', json=[{'queue': 'info'}])

            assert client.get_queues_info() == [{'queue': 'info'}]

    def test_get_queues_info_when_http_error(self, client):
        with requests_mock.Mocker() as mocker:
            mocker.get(
                'http://example.com:15672/api/queues/',
                status_code=500,
                text='server-error',
            )

            with pytest.raises(requests.exceptions.HTTPError):
                client.get_queues_info()
