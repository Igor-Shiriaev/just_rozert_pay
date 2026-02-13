from typing import Generator

import requests

from rozert_pay_shared.const import CARD_BIN_DATA_ENDPOINT
from rozert_pay_shared.dto import CardBinData, PaginatedCardBinDataResponse


class RozertPrivateApi:
    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update(
            {
                'X-Back-Secret-Key': self.api_key,
                'Content-Type': 'application/json',
            }
        )

    def get_card_bin_data_paginated(self) -> Generator[list[CardBinData], None, None]:
        url: str | None = f'{self.base_url}{CARD_BIN_DATA_ENDPOINT}'
        while url:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
            pydantic_response = PaginatedCardBinDataResponse.parse_obj(data)
            yield pydantic_response.results
            url = pydantic_response.next
