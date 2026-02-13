"""
Кастомные Django template фильтры.
"""
import contextlib
import threading
from typing import Generator, TypedDict, cast

from bm.django_utils.encrypted_field import SecretValue
from django import template
from django.contrib.admin.helpers import AdminReadonlyField
from django.db import models
from rozert_pay.account.models import User
from rozert_pay.common.encryption import EncryptedFieldV2
from rozert_pay.payment import permissions

register = template.Library()


class _FieldPermissionInfo(TypedDict):
    view_permission: permissions.Permission | str
    has_permission: bool
    value: SecretValue


class _AdminDisplayContextType(TypedDict):
    field_permissions: dict[str, _FieldPermissionInfo]


class _AdminDisplayLocalsType:
    context: _AdminDisplayContextType


_admin_display_locals = cast(_AdminDisplayLocalsType, threading.local())


@contextlib.contextmanager
def admin_display_context(
    user: User, model: models.Model | None
) -> Generator[None, None, None]:
    """
    Context manager для установки контекста отображения зашифрованных полей в админке.

    Сохраняет информацию о разрешениях пользователя для каждого EncryptedFieldV2 поля модели.
    """
    # Инициализируем контекст, если его еще нет
    assert not hasattr(_admin_display_locals, "context")
    _admin_display_locals.context = {"field_permissions": {}}

    # Сохраняем информацию о разрешениях для каждого EncryptedFieldV2 поля
    field_permissions: dict[str, _FieldPermissionInfo] = {}

    if not model:
        yield
        return

    for field in model._meta.fields:
        if isinstance(field, EncryptedFieldV2):
            view_permission = field.view_permission

            # Проверяем права доступа
            if isinstance(view_permission, str):
                has_permission = user.has_perm(view_permission)
            else:
                has_permission = view_permission.allowed_for(user)

            field_permissions[field.name] = {
                "view_permission": view_permission,
                "has_permission": has_permission,
                "value": getattr(model, field.name),
            }

    # Сохраняем в контекст
    _admin_display_locals.context["field_permissions"] = field_permissions

    try:
        yield
    finally:
        # Очищаем контекст после использования
        del _admin_display_locals.context


@register.filter(name="to_repr")
def to_repr(field: AdminReadonlyField) -> str:
    """
    Преобразует значение в его строковое представление.

    Для EncryptedFieldV2 полей проверяет разрешения пользователя:
    - Если есть разрешение - расшифровывает и возвращает значение
    - Если нет разрешения - возвращает зашифрованное значение как есть

    Использование в шаблоне:
        {{ some_value|to_repr }}
    """
    field_name = field.field["name"]

    # Получаем информацию о разрешениях из контекста
    if not hasattr(_admin_display_locals, "context"):
        return field.contents()

    field_permissions = _admin_display_locals.context["field_permissions"]
    permission_info = field_permissions.get(field_name)

    # Если это не EncryptedFieldV2 поле или нет информации о разрешениях, возвращаем как есть
    if not permission_info:
        return field.contents()

    # Если у пользователя нет разрешения, возвращаем зашифрованное значение
    if not permission_info["has_permission"]:
        return field.contents()

    value = permission_info["value"]
    decrypted_value = value.get_secret_value()
    return decrypted_value
