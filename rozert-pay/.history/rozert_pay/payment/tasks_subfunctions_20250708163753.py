import logging
from typing import Any

import requests


def fetch_bitso_banks(logger: logging.Logger) -> list[dict[str, Any]]:
    """Fetch banks from Bitso API for Mexico."""
    url = 'https://bitso.com/api/v3/banks/MX'
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        if not data.get('success'):
            logger.error(
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