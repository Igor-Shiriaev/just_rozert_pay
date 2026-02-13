import json
from enum import StrEnum
from typing import Any

from bm.django_utils import encrypted_field, encryption
from bm.django_utils.encrypted_field import (
    EncryptedFieldType,
    EncryptedFormField,
    EncryptionKeySet,
)
from bm.django_utils.encryption import get_key  # noqa: F401
from bm.django_utils.thread_local_middleware import get_current_request
from bm.django_utils.widgets import JSONEditorWidget
from django.conf import settings
from django.core.exceptions import ValidationError
from rozert_pay.payment import permissions


class EncryptedField(encryption.EncryptedField):
    """
    Deprecated, use EncryptedFieldV2
    """

    def get_keys(self) -> list[str]:
        return settings.ENCRYPTION_KEYS


class EncryptedFieldV2(encrypted_field.BaseEncryptedTextField):
    def __init__(
        self,
        *args: Any,
        view_permission: permissions.Permission | str,
        encryption_version: str = "v1",
        key_set_id: str = "default",
        field_type: str | EncryptedFieldType = EncryptedFieldType.STRING,
        **kwargs: Any,
    ) -> None:
        self.view_permission = view_permission
        super().__init__(
            *args,
            encryption_version=encryption_version,
            key_set_id=key_set_id,
            field_type=field_type,
            **kwargs,
        )

    def deconstruct(self):  # type: ignore
        name, path, args, kwargs = super().deconstruct()
        kwargs["view_permission"] = self.view_permission
        return name, path, args, kwargs

    def get_key_set(self, key_set_id: str) -> EncryptionKeySet:
        return EncryptionKeySet(**settings.ENCRYPTION_KEY_SET[KeySetId(key_set_id)])

    def formfield(
        self,
        **kwargs: Any,
    ) -> Any:
        return _EncryptedFieldV2FormField(
            view_permission=self.view_permission,
            field_type=self.field_type or EncryptedFieldType.STRING,
            **kwargs,
        )


class _EncryptedFieldV2FormField(EncryptedFormField):
    def __init__(
        self,
        field_type: EncryptedFieldType,
        view_permission: permissions.Permission | str,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.field_type = field_type
        self.view_permission = view_permission

        self._has_permission = False

        request = get_current_request()
        if request and hasattr(request, "user"):
            user = request.user
            if isinstance(self.view_permission, str):
                if user.has_perm(self.view_permission):
                    self._has_permission = True
            else:
                if self.view_permission.allowed_for(user):
                    self._has_permission = True

        # Enable nice json widget if has permission
        if self.field_type == EncryptedFieldType.JSON and self._has_permission:
            self.widget = JSONEditorWidget(mode=JSONEditorWidget.MODE_CODE)

        # Disable edit if no permission
        if not self._has_permission:
            self.widget.attrs["readonly"] = True

    def to_python(self, value: Any) -> Any:
        """
        Convert the value from the form (JSON string from widget) to Python object.
        For JSON fields, parse JSON string to dict/list before parent class processes it.
        """
        # For JSON fields, the widget sends JSON string, we need to parse it to dict/list
        if self.field_type == EncryptedFieldType.JSON and value is not None:
            if isinstance(value, str):
                # Empty string should be treated as None
                if not value.strip():
                    return None

                if value == "None":
                    return None

                # Parse JSON string to dict/list
                try:
                    return json.loads(value)
                except Exception:
                    raise ValidationError("Incorrect json value passed")

        # For non-JSON fields or if parsing failed, use parent implementation
        return super().to_python(value)

    def prepare_value(self, value: Any) -> Any:
        if value == "None":
            value = None

        if not self._has_permission:
            return f"<No permissions! Required {self.view_permission}>"

        # Extract value from SecretValue if needed
        if value is not None and hasattr(value, "get_secret_value"):
            value = value.get_secret_value()

        # For JSON fields with JSONEditorWidget, we need to return valid JSON string
        # The widget expects JSON string in textarea, not Python dict
        if self.field_type == EncryptedFieldType.JSON and value is not None:
            # If value is already a string, try to parse and re-serialize to ensure valid JSON
            if isinstance(value, str):
                # Parse to validate and normalize

                try:
                    parsed = json.loads(value)
                except Exception:
                    raise ValidationError("Incorrect json value passed")

                # Return as JSON string - widget will parse it
                return json.dumps(parsed, ensure_ascii=False)
            else:
                # If value is dict/list, serialize to JSON string
                return json.dumps(value, ensure_ascii=False)

        return super().prepare_value(value)


class DeterministicHashField(encrypted_field.BaseDeterministicHashTextField):
    def get_key_set(self, key_set_id: str) -> EncryptionKeySet:
        return EncryptionKeySet(**settings.ENCRYPTION_KEY_SET[KeySetId(key_set_id)])


class KeySetId(StrEnum):
    PII = "pii"
    CARD_DATA = "card_data"
    PII_HASH = "pii_hash"
    CARD_DATA_HASH = "card_data_hash"
