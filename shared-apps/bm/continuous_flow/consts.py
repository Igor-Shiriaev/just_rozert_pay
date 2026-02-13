from enum import auto
from typing import Literal

from bm.constants import StrEnum


class ContinuousFlow(StrEnum):
    uk_continuous_play_flow = auto()


class ContinuousFlowStep(StrEnum):
    reality_check_on_180_min = auto()
    reality_check_on_210_min = auto()
    reality_check_on_240_min = auto()


ContinuousSessionDurationThreshold = Literal['3h', '3.5h', '4h']
