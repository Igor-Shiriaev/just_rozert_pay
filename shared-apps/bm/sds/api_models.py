from typing import Optional

from pydantic import BaseModel, SecretStr, Field
from .const import SDType
from .type_aliases import SDET, SDDHT


class SDItem(BaseModel):
    type: SDType
    plaintext: SecretStr


class EncryptOneContract(BaseModel):
    item: SDItem


class EncryptManyContract(BaseModel):
    items: list[SDItem]


class EncryptOneWithUpdateContract(BaseModel):
    item: SDItem
    token: SDET


class DecryptOneContract(BaseModel):
    token: SDET
    ignore_missing: bool


class DecryptManyContract(BaseModel):
    # The same batch size as in EncryptManyResponse
    tokens: list[SDET] = Field(..., max_length=1000)
    ignore_missing: bool


class EncryptOneResponse(BaseModel):
    token: SDET


class EncryptManyResponse(BaseModel):
    # 1000 seems like a reasonable batch size, even though encryption is not
    # so expensive as deterministic hashing. Could be increased if needed.
    tokens: list[SDET] = Field(..., max_length=1000)


class EncryptOneWithUpdateResponse(BaseModel):
    token: SDET


class SDItemDecrypted(BaseModel):
    type: SDType
    plaintext: str


class DecryptOneResponse(BaseModel):
    item: Optional[SDItemDecrypted]


class DecryptManyResponse(BaseModel):
    items: list[Optional[SDItemDecrypted]]


class DeterministicHashOneContract(BaseModel):
    item: SDItem
    create_if_missing: bool


class DeterministicHashManyContract(BaseModel):
    # Deterministic hashing is CPU expensive operation (hundrends of milliseconds for
    # one item), so 20 is ok, otherwise it will be very long http request.
    items: list[SDItem] = Field(..., max_length=20)
    create_if_missing: bool


class DeterministicHashOneResponse(BaseModel):
    token: Optional[SDDHT]


class DeterministicHashManyResponse(BaseModel):
    tokens: list[Optional[SDDHT]]


class EncryptAndDeterministicHashContract(BaseModel):
    encryption: EncryptManyContract
    deterministic_hashing: DeterministicHashManyContract


class EncryptAndDeterministicHashResponse(BaseModel):
    encryption: EncryptManyResponse
    deterministic_hashing: DeterministicHashManyResponse
