from typing import Optional, List, Dict, Union

try:
    from django.http import JsonResponse
except ImportError:
    class JsonResponse:  # type: ignore[no-redef]
        def __init__(self, payload: dict):
            self.payload = payload
            self.status_code = 200

ValidationErrorDetail = Dict[str, List[str]]
_ValidationErrorDetail = Union[
    str,
    Dict[str, str],
    Dict[str, List[str]]
]


class ValidationError(Exception):
    """
    raise ValidationError() -> {'non_field_errors': ['Validation error']}
    raise ValidationError('Foo') -> {'non_field_errors': ['Foo']}
    raise ValidationError({'foo': 'Bar'}) -> {'foo': ['Bar']}
    raise ValidationError({'foo': ['Bar']}) -> {'foo': ['Bar']}
    """
    NON_FIELD_ERRORS_KEY = 'non_field_errors'
    DEFAULT_ERROR = 'VALIDATION_ERROR'
    detail: ValidationErrorDetail

    def __init__(
        self,
        detail: Optional[_ValidationErrorDetail] = None
    ) -> None:
        if not detail:
            detail = self.DEFAULT_ERROR
        if isinstance(detail, str):
            self.detail = {self.NON_FIELD_ERRORS_KEY: [detail]}
        elif isinstance(detail, dict):
            self.detail = {}
            for key, value in detail.items():
                if isinstance(value, str):
                    value = [value]
                self.detail[key] = value
        else:
            self.detail = {self.NON_FIELD_ERRORS_KEY: [self.DEFAULT_ERROR]}     # type: ignore

    @property
    def non_field_errors(self) -> Optional[List[str]]:
        return self.detail.get(self.NON_FIELD_ERRORS_KEY)

    def __str__(self) -> str:
        return str(self.detail)


class ClientError(Exception):
    pass


class NonReportableValueError(ValueError):
    pass


class BadRequest(ClientError):
    def __init__(self, detail: Dict):
        self.detail = detail


HTTP_BAD_REQUEST = {
    'code': 'HTTP_BAD_REQUEST',
    'message': 'Bad request'
}

HTTP_UNAUTHORIZED = {
    'code': 'HTTP_UNAUTHORIZED',
    'message': 'Authentication credentials were not provided'
}

HTTP_FORBIDDEN = {
    'code': 'HTTP_FORBIDDEN',
    'message': 'Forbidden'
}

HTTP_NOT_FOUND = {
    'code': 'HTTP_NOT_FOUND',
    'message': 'Not found'
}

HTTP_VALIDATION_FAILED = {
    'code': 'HTTP_VALIDATION_FAILED',
    'message': 'Validation failed'
}

HTTP_INVALID_JSON = {
    'code': 'HTTP_INVALID_JSON',
    'message': 'Invalid data'
}

HTTP_SERVER_ERROR = {
    'code': 'HTTP_SERVER_ERROR',
    'message': 'Server error',
}


class HTTPError(Exception):
    status: int
    code: Dict
    detail: Dict

    def __init__(
        self, *,
        status: int = None,
        code: Dict = None,
        message: str = None,
        detail: Dict = None,
    ) -> None:
        if status is not None:
            self.status = status
        if code is not None:
            self.code = code
        if message is not None:
            self.code.update({'message': message})
        self.detail = {}
        if detail is not None:
            self.detail = detail

    def as_data(self) -> Dict:
        return {
            'detail': self.detail,
            **self.code,
        }

    def as_response(self) -> JsonResponse:
        out = JsonResponse(self.as_data())
        out.status_code = self.status
        return out


class HTTPBadRequest(HTTPError):
    status = 400
    code = HTTP_BAD_REQUEST


class HTTPUnauthorized(HTTPError):
    status = 401
    code = HTTP_UNAUTHORIZED


class HTTPForbidden(HTTPError):
    status = 403
    code = HTTP_FORBIDDEN


class HTTPNotFound(HTTPError):
    status = 404
    code = HTTP_NOT_FOUND


class HTTPServerError(HTTPError):
    status = 500
    code = HTTP_SERVER_ERROR
