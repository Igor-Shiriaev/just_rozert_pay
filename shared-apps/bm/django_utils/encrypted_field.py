import binascii
import datetime
import hashlib
import hmac
import json
import os
import warnings
from enum import Enum, auto
from typing import Any, Callable, NewType

from bm.common.entities import StrEnum
from bm.django_utils.encryption import SecretValue
from bm.utils import BMJsonEncoder
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django import forms
from django.db import models
from django.db.models.fields import Field
from django.utils.functional import cached_property
from pydantic import BaseModel, SecretBytes, validator

EncryptionKeyId = NewType('EncryptionKeyId', str)


class EncryptedFieldType(Enum):
    JSON = 'json'
    DATE = 'date'
    DATETIME = 'datetime'
    STRING = 'string'
    BOOL = 'bool'
    INTEGER = 'integer'
    FLOAT = 'float'


def serialize_json(value: dict | list) -> str:
    return json.dumps(value, cls=BMJsonEncoder)

def deserialize_json(value: str) -> dict | list:
    return json.loads(value)


def serialize_date(value: datetime.date) -> str:
    return value.isoformat()

def deserialize_date(value: str) -> datetime.date:
    return datetime.date.fromisoformat(value)


def serialize_datetime(value: datetime.datetime) -> str:
    return value.isoformat()

def deserialize_datetime(value: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(value)


def serialize_string(value: str) -> str:
    return str(value)

def deserialize_string(value: str) -> str:
    return value


def serialize_bool(value: bool) -> str:
    return "1" if value else "0"

def deserialize_bool(value: str) -> bool:
    return value == "1"


def serialize_int(value: int) -> str:
    return str(value)

def deserialize_int(value: str) -> int:
    return int(value)


def serialize_float(value: float) -> str:
    return repr(value)

def deserialize_float(value: str) -> float:
    return float(value)


SERIALIZERS_MAP_BY_FIELD_TYPE: dict[EncryptedFieldType, tuple[Callable[[Any], str], Callable[[str], Any]]] = {
    EncryptedFieldType.JSON: (serialize_json, deserialize_json),
    EncryptedFieldType.DATE: (serialize_date, deserialize_date),
    EncryptedFieldType.DATETIME: (serialize_datetime, deserialize_datetime),
    EncryptedFieldType.STRING: (serialize_string, deserialize_string),
    EncryptedFieldType.BOOL: (serialize_bool, deserialize_bool),
    EncryptedFieldType.INTEGER: (serialize_int, deserialize_int),
    EncryptedFieldType.FLOAT: (serialize_float, deserialize_float),
}


class EncryptionKeyStatus(StrEnum):
    # Primary key in the key set used for all encryption operations.
    ENABLED = auto()
    # Means key is not used for encryption, but can be used for decryption. not rotated yet.
    DISABLED = auto()
    # Means key has been rotated and is no longer used for encryption (records that used this key are re-encrypted with a new primary key).
    ROTATED = auto()
    # Means that ROTATED key was never shown in any exceptions (there were no errors in rotation and no records that used this key), so the key material can be safely deleted
    DESTROYED = auto()



with warnings.catch_warnings():
    warnings.filterwarnings(
        "ignore",
        message=r"Pydantic V1 style `@validator` validators are deprecated.*",
        category=DeprecationWarning,
    )

    class EncryptionKey(BaseModel):
        key_id: EncryptionKeyId
        key_material: SecretBytes
        description: str
        created_at: datetime.datetime
        status: EncryptionKeyStatus

        @validator('key_material', pre=True)
        def decode_hex(cls, v):  # type: ignore[no-untyped-def]
            if isinstance(v, str):  # we suppose it's hex string
                try:
                    return binascii.unhexlify(v)
                except binascii.Error as e:
                    raise ValueError(f"Invalid hex for key_material: {e}")
            elif isinstance(v, bytes):
                return SecretBytes(v)
            else:
                return v


class EncryptionKeySet(BaseModel):
    key_set_id: str
    primary_key_id: EncryptionKeyId
    keys: list[EncryptionKey]

    @property
    def primary_key(self) -> EncryptionKey:
        keys = [key for key in self.keys if key.key_id == self.primary_key_id and key.status == EncryptionKeyStatus.ENABLED]
        assert len(keys) == 1, f"Primary key {self.primary_key_id} not found in key set {self.key_set_id}"
        return keys[0]


class EncryptedFormField(forms.CharField):
    def prepare_value(self, value: Any) -> Any:
        if isinstance(value, SecretValue):
            value = value.get_secret_value()
        return super().prepare_value(value)

    def to_python(self, value: str) -> 'SecretValue[str] | None':
        if value in self.empty_values:
            return None
        return super().to_python(value)


class EncryptedDateFormField(forms.DateField):
    def prepare_value(self, value: Any) -> Any:
        if isinstance(value, SecretValue):
            value = value.get_secret_value()
        return super().prepare_value(value)

    def to_python(self, value: str) -> 'SecretValue[datetime.date] | None':
        if value in self.empty_values:
            return None
        return super().to_python(value)


class EncryptedJSONFormField(forms.JSONField):
    def prepare_value(self, value: Any) -> Any:
        if isinstance(value, SecretValue):
            value = value.get_secret_value()
        return super().prepare_value(value)

    def to_python(self, value: str) -> 'SecretValue[dict | list] | None':
        if value in self.empty_values:
            return None
        return super().to_python(value)


class BaseEncryptedTextField(models.TextField):
    description = "Text field that transparently encrypts and decrypts using AES-GCM."

    DELIMITER = '$$'

    def __init__(  # type: ignore[no-untyped-def]
        self,
        *args,
        encryption_version: str = 'v1',
        key_set_id: str = 'default',
        field_type: str | EncryptedFieldType = EncryptedFieldType.STRING,
        **kwargs
    ):
        self.encryption_version = encryption_version
        self.key_set_id = key_set_id

        if not isinstance(field_type, EncryptedFieldType):
            field_type = EncryptedFieldType(field_type)
        self.field_type: EncryptedFieldType = field_type
        self.serializer: Callable[[Any], str]
        self.deserializer: Callable[[str], Any]
        self.serializer, self.deserializer = SERIALIZERS_MAP_BY_FIELD_TYPE[field_type]

        super().__init__(*args, **kwargs)

    def contribute_to_class(self, cls, name, private_only=False):  # type: ignore
        """So that access to the field is always through the descriptor."""
        super().contribute_to_class(cls, name, private_only=private_only)
        setattr(cls, self.name, EncryptedAttribute(self))  # Replace default descriptor

    def deconstruct(self):  # type: ignore
        """Teach django to include the right field arguments during migration.
        For example in migration it becomes:
            migrations.CreateModel(
                name='UserPersonalData',
                fields=[
                    ...
                    (
                        'date_of_birth',
                        common.fields.EncryptedTextField(
                            blank=True,
                            encryption_version='v1',
                            field_type='date',
                            key_set_id='sensitive_data',
                            null=True,
                        ),
                    ),
                ),
            )
        """
        name, path, args, kwargs = super().deconstruct()
        kwargs['encryption_version'] = self.encryption_version
        kwargs['key_set_id'] = self.key_set_id
        kwargs['field_type'] = self.field_type.value
        return name, path, args, kwargs

    def get_key_set(self, key_set_id: str) -> EncryptionKeySet:
        raise NotImplementedError

    @cached_property
    def key_set(self) -> EncryptionKeySet:
        return self.get_key_set(self.key_set_id)

    @cached_property
    def primary_encryption_key(self) -> EncryptionKey:
        return self.key_set.primary_key

    def encrypt(self, value: str) -> str:
        nonce = os.urandom(12)  # AESGCM requires "Nonce must be between 8 and 128 bytes", usually 12 bytes is used
        # use only primary key for encryption
        key_id = self.primary_encryption_key.key_id
        aesgcm = AESGCM(self.primary_encryption_key.key_material.get_secret_value())
        ciphertext = aesgcm.encrypt(
            nonce=nonce,
            data=value.encode(),
            associated_data=self.encryption_version.encode(),
        ).hex()
        return f'{self.encryption_version}{self.DELIMITER}{key_id}{self.DELIMITER}{nonce.hex()}{self.DELIMITER}{ciphertext}'

    def decrypt(self, stored_value: str) -> str:
        try:
            version, key_id, nonce_hex_str, ciphertext_hex_str = stored_value.split(self.DELIMITER, 3)
        except ValueError:
            raise ValueError('Invalid encrypted text value format')
        if version != 'v1':
            raise ValueError(f'Unsupported encryption version: {version}')
        assert version == 'v1'

        # use historical key (non rotated and non destroyed) that was used to encrypt this record
        key_used = None
        for k in self.key_set.keys:
            if k.key_id == key_id:
                key_used = k
                break
        if key_used is None:
            raise ValueError(f'No key found for key_id: {key_id}')
        if key_used.status in [EncryptionKeyStatus.ROTATED, EncryptionKeyStatus.DESTROYED]:
            raise ValueError(f'Key with id {key_id} is not usable: status {key_used.status}')

        aesgcm = AESGCM(key_used.key_material.get_secret_value())
        return self.deserializer(
            aesgcm.decrypt(
                nonce=bytes.fromhex(nonce_hex_str),
                data=bytes.fromhex(ciphertext_hex_str),
                associated_data=self.encryption_version.encode(),
            ).decode()
        )

    def get_prep_value(self, value):  # type: ignore[no-untyped-def]
        """Called before saving to DB — encrypt here."""
        if value is None:
            return None
        v = value.get_secret_value() if isinstance(value, SecretValue) else value
        if v is None:
            return None
        return self.encrypt(self.serializer(v))

    def from_db_value(self, value, expression, connection):  # type: ignore[no-untyped-def]
        """Called when reading from DB — decrypt here."""
        if value is None:
            return SecretValue(None)
        return SecretValue(self.decrypt(value))

    def to_python(self, value) -> SecretValue:  # type: ignore[no-untyped-def]
        """Ensure Python code always sees plaintext."""
        if value is None:
            return SecretValue(None)

        # Already wrapped
        if isinstance(value, SecretValue):
            return value

        # If already decrypted, skip
        # If not a valid encrypted value, skip decryption
        if not (isinstance(value, str) and value.startswith(self.encryption_version + self.DELIMITER) and value.count(self.DELIMITER) == 3):
            return SecretValue(value)

        return SecretValue(self.decrypt(value))

    def formfield(
        self,
        **kwargs: Any,
    ) -> Any:
        return super().formfield(
            **{
                'form_class': EncryptedFormField,
                **kwargs,
            }
        )



class EncryptedAttribute:
    """
    Custom descriptor to intercept assignments and retrievals.
    Wraps all assigned values in SecretValue, and uses Field.to_python
    for DB-loaded values.
    """
    def __init__(self, field: Field):
        self.field = field

    def __get__(self, instance, owner=None):  # type: ignore
        if instance is None:  # default behaviour when accessing the class, not an instance, e.g., MyModel.my_field
            return self
        return instance.__dict__.get(self.field.name)

    def __set__(self, instance, value):  # type: ignore
        # Wrap only if not already wrapped
        if not isinstance(value, SecretValue):
            value = SecretValue(value)
        instance.__dict__[self.field.name] = value


class BaseDeterministicHashTextField(models.TextField):
    description = "Text field that transparently calculates deterministic hashes using HMAC."

    DELIMITER = '$$'

    def __init__(  # type: ignore[no-untyped-def]
        self,
        *args,
        deterministic_hash_version: str = 'v1',
        key_set_id: str = 'default',
        field_type: str | EncryptedFieldType = EncryptedFieldType.STRING,
        **kwargs
    ):
        self.deterministic_hash_version = deterministic_hash_version
        self.key_set_id = key_set_id

        if not isinstance(field_type, EncryptedFieldType):
            field_type = EncryptedFieldType(field_type)
        if field_type is EncryptedFieldType.JSON:
            # because json serialization can be not reproducible (e.g. dict key order), we do not allow JSON here
            raise ValueError('Deterministic hash field cannot be of type JSON')
        self.field_type: EncryptedFieldType = field_type
        self.serializer: Callable[[Any], str]
        self.serializer, _ = SERIALIZERS_MAP_BY_FIELD_TYPE[field_type]

        super().__init__(*args, **kwargs)

    def deconstruct(self):  # type: ignore
        """Teach django to include the right field arguments during migration.
        For example in migration it becomes:
            migrations.CreateModel(
                name='UserPersonalData',
                fields=[
                    ...
                    (
                        'date_of_birth_deterministic_hash',
                        common.fields.DeterministicHashTextField(
                            blank=True,
                            deterministic_hash_version='v1',
                            field_type='date',
                            key_set_id='sensitive_data',
                            null=True,
                        ),
                    ),
                ),
            )
        """
        name, path, args, kwargs = super().deconstruct()
        kwargs['deterministic_hash_version'] = self.deterministic_hash_version
        kwargs['key_set_id'] = self.key_set_id
        kwargs['field_type'] = self.field_type.value
        return name, path, args, kwargs

    def get_key_set(self, key_set_id: str) -> EncryptionKeySet:
        raise NotImplementedError

    @cached_property
    def key_set(self) -> EncryptionKeySet:
        return self.get_key_set(self.key_set_id)

    @cached_property
    def primary_hashing_key(self) -> EncryptionKey:
        return self.key_set.primary_key

    def get_prep_value(self, value):  # type: ignore[no-untyped-def]
        """Called before saving to DB — calculate deterministic hash here."""
        if isinstance(value, SecretValue):
            v = value.get_secret_value()
        else:
            v = value
        if v is None:
            return None
        return self._calculate_deterministic_hash(hashing_key=self.primary_hashing_key, value=self.serializer(v))

    def _calculate_deterministic_hash(self, *, hashing_key: EncryptionKey, value: str) -> str:
        ciphertext = hmac.new(
            key=hashing_key.key_material.get_secret_value(),
            msg=value.encode('utf-8'),
            digestmod=hashlib.sha256,
        ).digest().hex()
        return f'{self.deterministic_hash_version}{self.DELIMITER}{hashing_key.key_id}{self.DELIMITER}{ciphertext}'
