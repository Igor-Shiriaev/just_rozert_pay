from typing import Dict, Generic, Iterable, TypeVar

from django.http import HttpRequest, QueryDict

_T = TypeVar('_T')


class TypedRequest(HttpRequest):
    GET: QueryDict
    POST: QueryDict


class OpenAPIRequest(TypedRequest, Generic[_T]):
    payload_model: _T
    payload: Dict


class TrafaretApiRequest(TypedRequest):
    payload: Dict


Value = TypeVar('Value', bound=str)
VerboseValue = TypeVar('VerboseValue', bound=str)

FormChoices = Iterable[tuple[Value, VerboseValue]]
