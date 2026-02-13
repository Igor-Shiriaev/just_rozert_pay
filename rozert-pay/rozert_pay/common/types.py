from typing import Any
from uuid import UUID

from rest_framework import request
from rozert_pay.common.authorization import AuthData


class Request(request.Request):
    auth: AuthData | None


class AuthorizedRequest(request.Request):
    auth: AuthData


def to_uuid(value: str | UUID) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(value)


def to_any(value: Any) -> Any:
    return value
