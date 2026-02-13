from pydantic import BaseModel, Field, validator

from bm.payment import CARD_TYPE_CHOICES, CardClass, COUNTRY_CHOICES

VALID_COUNTRIES = {code for code, _ in COUNTRY_CHOICES}
VALID_CARD_TYPES = {code for code, _ in CARD_TYPE_CHOICES}
VALID_CARD_CLASSES = set(CardClass.values)


class BankInfo(BaseModel):
    name: str
    is_non_bank: bool = False


class BitsoBankInfo(BaseModel):
    code: str
    name: str
    country_code: str
    is_active: bool = True


class CardBinData(BaseModel):
    bin: str
    bank: BankInfo
    card_type: int  # shared-apps/bm/payment.py -> CARD_TYPE_CHOICES
    card_class: str | None = None  # shared-apps/bm/payment.py -> CardClass
    country: str  # shared-apps/bm/payment.py -> COUNTRY_CHOICES
    is_virtual: bool = False
    is_prepaid: bool = False
    raw_category: str | None = None
    remark: str | None = None
    bitso_banks: list[BitsoBankInfo] = Field(default_factory=list)

    @validator('country')
    def validate_country(cls, v: str) -> str:
        if v not in VALID_COUNTRIES:
            raise ValueError(f'Invalid country code: {v}')
        return v

    @validator('card_type')
    def validate_card_type(cls, v: int) -> int:
        if v not in VALID_CARD_TYPES:
            raise ValueError(f'Invalid card type: {v}')
        return v

    @validator('card_class')
    def validate_card_class(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_CARD_CLASSES:
            raise ValueError(f'Invalid card class: {v}')
        return v


class PaginatedCardBinDataResponse(BaseModel):
    next: str | None
    previous: str | None
    results: list[CardBinData]