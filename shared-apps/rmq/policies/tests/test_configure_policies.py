import pytest
import requests
import requests_mock

from rmq.http_client import RabbitHTTPClient
from rmq.policies.config import QueuesPoliciesByVHOSTConfiguration
from rmq.policies.const import PolicyName
from rmq.policies.services import configure_policies


class TestConfigurePolicies:
    @pytest.fixture
    def rabbit_http_client(self):
        return RabbitHTTPClient(host='example.com', port=15672, username='user', password='pass')

    def test_when_several_vhosts_and_definitions(self, rabbit_http_client):
        config = QueuesPoliciesByVHOSTConfiguration.parse_obj(
            {
                '/vhost-1': {
                    'queue-1': [PolicyName.TTL_10_SEC],
                    'queue-2': [PolicyName.TTL_1_MIN],
                },
                '/vhost-2': {'queue-3': [PolicyName.TTL_20_MIN]},
            }
        )

        with requests_mock.Mocker() as mocker:
            mocker.put('http://example.com:15672/api/policies/%2Fvhost-1/TTL-10sec')
            mocker.put('http://example.com:15672/api/policies/%2Fvhost-1/TTL-1min')
            mocker.put('http://example.com:15672/api/policies/%2Fvhost-2/TTL-20min')

            configure_policies(config, rabbit_http_client)

            assert mocker.call_count == 3
            assert mocker.request_history[-3].json() == {
                'apply-to': 'queues',
                'definition': {'message-ttl': 10000},
                'pattern': '^(queue\\-1)$',
            }
            assert mocker.request_history[-2].json() == {
                'apply-to': 'queues',
                'definition': {'message-ttl': 60000},
                'pattern': '^(queue\\-2)$',
            }
            assert mocker.request_history[-1].json() == {
                'apply-to': 'queues',
                'definition': {'message-ttl': 1200000},
                'pattern': '^(queue\\-3)$',
            }

    def test_when_definitions_are_combined(self, rabbit_http_client):
        config = QueuesPoliciesByVHOSTConfiguration.parse_obj(
            {
                '/vhost-1': {
                    'queue-1': [
                        PolicyName.TTL_3_DAY,
                        PolicyName.HA_EXACTLY_2,
                    ],
                    'queue-2': [
                        PolicyName.HA_EXACTLY_2,
                        PolicyName.TTL_3_DAY,
                    ],
                }
            }
        )

        with requests_mock.Mocker() as mocker:
            mock_adapter = mocker.put(
                'http://example.com:15672/api/policies/%2Fvhost-1/HA-exactly-2&TTL-3day'
            )

            configure_policies(config, rabbit_http_client)

            assert mock_adapter.last_request.json() == {
                'apply-to': 'queues',
                'definition': {
                    'ha-mode': 'exactly',
                    'ha-params': 2,
                    'ha-promote-on-failure': 'always',
                    'ha-promote-on-shutdown': 'when-synced',
                    'ha-sync-mode': 'automatic',
                    'message-ttl': 259200000,
                },
                'pattern': '^(queue\\-1|queue\\-2)$',
            }

    def test_when_http_error(self, rabbit_http_client):
        config = QueuesPoliciesByVHOSTConfiguration.parse_obj(
            {'/vhost-1': {'queue-1': [PolicyName.TTL_10_SEC]}}
        )

        with requests_mock.Mocker() as mocker:
            mocker.put(
                'http://example.com:15672/api/policies/%2Fvhost-1/TTL-10sec',
                status_code=500,
                text='server-error',
            )

            with pytest.raises(requests.exceptions.HTTPError):
                configure_policies(config, rabbit_http_client)
