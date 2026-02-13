from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from .constants import CasinoProviderType


class CasinoRewardConfigFormData(BaseModel):
    casino_provider: CasinoProviderType
    game_name: str
    game_uuid: UUID
    game_id: int
    game_type: Optional[str] = None
    extra: dict
