import logging
from typing import Any

import requests


def fetch_bitso_banks(logger: logging.Logger) -> list[dict[str, Any]]:
    """Fetch banks from Bitso API for Mexico."""
    
