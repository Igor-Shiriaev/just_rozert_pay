import logging
from functools import cached_property
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)


class RabbitHTTPClient:
    def __init__(self, host: str, port: int, username: str, password: str) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password

    def set_policy(
        self,
        policy_name: str,
        resources_pattern: str,
        vhost: str,
        policy_definition: dict,
        apply_to: str,
    ) -> None:
        """Find docs at https://pulse.mozilla.org/api/index.html and
        https://www.rabbitmq.com/parameters.html#policies.
        """
        vhost = quote(vhost, safe='')
        payload = {
            'pattern': resources_pattern,
            'definition': policy_definition,
            'apply-to': apply_to,
            'priority': 4,
        }

        response = requests.put(
            url=f'http://{self._host}:{self._port}/api/policies/{vhost}/{policy_name}',
            auth=(self._username, self._password),
            json=payload,
        )

        if not response.ok:
            logger.error(
                'error response from RMQ HTTP API',
                extra={'_response_text': response.text},
            )
        response.raise_for_status()

    def get_queues_info(self) -> list:
        response = requests.get(
            url=f'http://{self._host}:{self._port}/api/queues/',
            auth=(self._username, self._password),
        )
        response.raise_for_status()
        return response.json()

    def get_vhosts(self) -> list[str]:
        resp = requests.get(
            url=f'http://{self._host}:{self._port}/api/vhosts',
            auth=(self._username, self._password),
        )

        return [
            el['name']
            for el in resp.json()
        ]

    @cached_property
    def cached_vhosts(self) -> list[str]:
        return self.get_vhosts()

    def create_vhost(self, name: str) -> None:
        if name in self.cached_vhosts:
            return

        response = requests.put(
            url=f'http://{self._host}:{self._port}/api/vhosts/{quote(name, safe="")}',
            auth=(self._username, self._password),
        )
        response.raise_for_status()
        self.cached_vhosts.append(name)
        logger.info('created vhost %s', name)
