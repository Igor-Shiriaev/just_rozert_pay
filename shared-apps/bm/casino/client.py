from typing import Dict, List, Union
from uuid import UUID

from bm.utils import requests_retry_session
from bm.exceptions import BadRequest

from .entities import CasinoGame, CasinoGameListItem
from .constants import CasinoProviderType


class CasinoHTTPClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url
        self.token = token

    def get_game(
        self,
        casino_provider: CasinoProviderType,
        game_uuid: UUID
    ) -> CasinoGame:
        response = self._send_request(
            url=f'{self.base_url}/private-api/casino/games/{casino_provider}/{game_uuid}/',
            method='get'
        )
        assert isinstance(response, dict), "mypy"
        return CasinoGame(**response)

    def get_games_freespins_available(
        self,
        casino_provider: CasinoProviderType
    ) -> List[CasinoGameListItem]:
        response = self._send_request(
            url=f'{self.base_url}/private-api/casino/games/{casino_provider}/freespins-available/',
            method='get'
        )
        return [CasinoGameListItem(**item) for item in response]

    def _send_request(
        self,
        url: str,
        method: str = 'post',
        data: Dict = None,
    ) -> Union[Dict, List[Dict]]:
        response = getattr(requests_retry_session(retries=1), method)(
            url,
            headers={
                'Authorization': f'Bearer {self.token}'
            },
            json=data
        )
        if response.status_code == 400:
            raise BadRequest(response.json())
        response.raise_for_status()
        return response.json()
