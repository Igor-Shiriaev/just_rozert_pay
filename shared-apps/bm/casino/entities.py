from uuid import UUID

from pydantic import BaseModel


class CasinoGameListItem(BaseModel):
    name: str
    foreign_system_id: str
    uuid: UUID


class CasinoGame(CasinoGameListItem):
    currency_convertion_map: dict[str, str]
    freespin_settings: dict
