from typing import Optional
from uuid import UUID

from pydantic import BaseModel
from bm.datatypes import Money


class ChallengeActionContext(BaseModel):
    """IMPORTANT: This data will be visible by user, since it will be part of jwt
    token payload, and jwt token is not encrypted, just signed.
    Make sure there is no sensitive data like passwords or similar in this structure.
    """

class EmptyChallengeActionContext(ChallengeActionContext):

    class Config:
        extra = 'forbid'


class PaymentWithdrawChallengeContext(ChallengeActionContext):
    payment_system: str
    money: Money
    wallet_uuid: UUID

    class Config:
        extra = 'forbid'


class AuthChallengeContext(ChallengeActionContext):
    host: str
    auth_method: Optional[str] = None
    redirect_to: Optional[str] = None

    class Config:
        extra = 'forbid'
