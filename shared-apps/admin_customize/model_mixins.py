import enum
from typing import Generator

from admin_customize.const import IMG_NO, IMG_YES
from bm.django_utils.encrypted_field import SecretValue
from django.db import models


class EasyAdminReprModel(models.Model):
    FIELDS_TO_REPR: list[str] = []

    def get_field_for_repr(self) -> Generator[tuple[str, str], None, None]:
        for field_name in self.FIELDS_TO_REPR:
            field_label = self._meta.get_field(field_name).verbose_name
            field_value = getattr(self, field_name)
            if isinstance(field_value, SecretValue):
                field_value = field_value.get_secret_value()
            if isinstance(field_value, bool):
                field_value = IMG_YES if field_value else IMG_NO
            if isinstance(field_value, enum.Enum):
                field_value = field_value.value

            yield field_label, field_value

    class Meta:
        abstract = True
