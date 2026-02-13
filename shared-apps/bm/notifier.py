import json
import logging
from typing import Tuple, Dict
from uuid import UUID

import jwt
import requests

from .utils import BMJsonEncoder

logger = logging.getLogger(__name__)


class _settings:
    JWT_SECRET: str
    NOTIFIER_API_URLS_BY_SHARD: dict[int, str]


def init(jwt_secret: str, notifier_api_urls_by_shard: dict[int, str]) -> None:
    _settings.JWT_SECRET = jwt_secret
    _settings.NOTIFIER_API_URLS_BY_SHARD = notifier_api_urls_by_shard


def _notify(*, url: str, payload: Dict, http_headers: Dict = None) -> None:
    http_headers = http_headers or {}
    http_headers.setdefault('Content-Type', 'application/json')
    try:
        response = requests.post(
            url=url,
            headers=http_headers,
            data=json.dumps({
                'payload': jwt.encode(
                    payload=payload,
                    key=_settings.JWT_SECRET,
                    algorithm='HS256',
                    json_encoder=BMJsonEncoder
                ),
            }),
            timeout=(2, 5)
        )
        response.raise_for_status()
    except requests.exceptions.RequestException:
        logger.exception('notifier service error')


def notify_all(message: Dict) -> None:
    payload = {
        'message': message
    }

    # NOTE: could be refactored with ioloop and 3 parallel requests. But we do not
    # use this method at all (or very rarely), so it's not worth it now.
    for api_url in _settings.NOTIFIER_API_URLS_BY_SHARD.values():
        _notify(url=f'{api_url}/api/notify/all', payload=payload)


def notify_single(user_notifier_info: Tuple[str, int],
                  message: Dict, http_headers: Dict = None) -> None:
    user_uuid, user_notifier_shard = user_notifier_info
    payload = {
        'user_uuid': user_uuid,
        'message': message
    }

    api_url = _settings.NOTIFIER_API_URLS_BY_SHARD[user_notifier_shard]
    _notify(url=f'{api_url}/api/notify/single', payload=payload, http_headers=http_headers)


def get_user_notifier_shard(user_uuid: UUID) -> int:
    # NOTE: 3 shards in total: 0, 1 and 2.
    # 3 is hardcoded and can't be easily changed.
    # See betmanager/.helm/values.yaml
    return int(user_uuid) % 3
