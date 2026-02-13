import base64
import json
from typing import Any, Generic, TypeVar

from bm.utils import BMJsonEncoder
from cryptography.fernet import Fernet, MultiFernet
from django.db import models
from pydantic import SecretStr

ENCRYPTION_VERSION = 'v1'


def get_key() -> str:
    """
    Generates secret key for encryption
    """
    return Fernet.generate_key().decode()


def encrypt(payload: str, keys: list[SecretStr]) -> str:
    """
    Encrypts payload using secret key.
    Uses MultiFernet to allow easy key's rotation.
    Returns base64 of encrypted payload with prefix
    """
    f = MultiFernet([Fernet(key.get_secret_value()) for key in keys])

    encrypted = base64.b64encode(f.encrypt(payload.encode()))
    return f"{ENCRYPTION_VERSION}${encrypted.decode()}"


def decrypt(payload: str, keys: list[SecretStr]) -> str:
    """
    Decrypts payload using secret keys
    """
    version, encrypted = payload.split('$')
    if version != ENCRYPTION_VERSION:
        raise ValueError(f"Unsupported encryption version: {version}")

    f = MultiFernet([Fernet(key.get_secret_value()) for key in keys])
    return f.decrypt(base64.b64decode(encrypted)).decode()


def rotate_key(payload: str, keys: list[SecretStr]) -> str:
    """
    Decrypts payload and encrypts again
    """
    return encrypt(decrypt(payload, keys), keys)


class EncryptedField(models.TextField):
    """
    Encrypted django field.
    """

    def get_keys(self) -> list[str]:
        raise NotImplementedError

    @property
    def keys(self) -> list[SecretStr]:
        return [SecretStr(x) for x in self.get_keys()]

    def from_db_value(self, value, expression, connection):  # type: ignore[no-untyped-def]
        if value is None:
            return value
        return json.loads(decrypt(value, self.keys))

    def get_prep_value(self, value):  # type: ignore[no-untyped-def]
        if value is None:
            return value

        value = json.dumps(value, cls=BMJsonEncoder)
        return encrypt(value, self.keys)

    def to_python(self, value): # type: ignore
        return value


T = TypeVar("T")


class SecretValue(Generic[T]):
    """
    Generic wrapper to hide sensitive values from repr/str.
    Works for any type (string, number, list, dict, datetime, etc.).
    """

    __slots__ = ('_value',)

    def __init__(self, value: T):
        self._value = value

    def get_secret_value(self) -> T:
        """Return the underlying secret value."""
        return self._value

    def __repr__(self) -> str:
        return "SecretValue('***')"

    def __str__(self) -> str:
        return '***'

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, SecretValue):
            return self._value == other._value
        return self._value == other

    def __hash__(self) -> int:
        return hash(self._value)

    def __bool__(self) -> bool:
        return bool(self._value)
