from enum import StrEnum

from bm.django_utils import encrypted_field, encryption
from bm.django_utils.encrypted_field import EncryptionKeySet
from bm.django_utils.encryption import get_key  # noqa: F401
from django.conf import settings


class EncryptedField(encryption.EncryptedField):
    """
    Deprecated, use EncryptedFieldV2
    """

    def get_keys(self) -> list[str]:
        return settings.ENCRYPTION_KEYS


class EncryptedFieldV2(encrypted_field.BaseEncryptedTextField):
    def get_key_set(self, key_set_id: str) -> EncryptionKeySet:
        return EncryptionKeySet(**settings.ENCRYPTION_KEY_SET[KeySetId(key_set_id)])


class DeterministicHashField(encrypted_field.BaseDeterministicHashTextField):
    def get_key_set(self, key_set_id: str) -> EncryptionKeySet:
        return EncryptionKeySet(**settings.ENCRYPTION_KEY_SET[KeySetId(key_set_id)])


class KeySetId(StrEnum):
    PII = "pii"
    CARD_DATA = "card_data"
    PII_HASH = "pii_hash"
    CARD_DATA_HASH = "card_data_hash"
    
