import logging
from typing import Any

import requests

from rozert_pay.common.logger import logger


def log_event(level: int, message: str, extra: dict[str, Any] | None = None) -> None:
    extra_data = extra or {}
    extra_data['country_code'] = country_code
    logger.log(level, message, extra=extra_data)

def fetch_bitso_banks() -> list[dict[str, Any]]:
    """Fetch banks from Bitso API for Mexico."""
    url = f'https://bitso.com/api/v3/banks/{country_code}'
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        if not data.get('success'):
            log_event(
                logging.ERROR,
                'Bitso API returned unsuccessful response',
                extra={'data': data},
            )
            return []
        return data.get('payload', [])
    except requests.RequestException as e:
        log_event(
            logging.ERROR,
            'Failed to fetch Bitso banks',
            extra={'error': str(e)},
        )
        return []