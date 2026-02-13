import json

from typing import Dict, Any, cast

from trafaret import DataError

from django.http import HttpRequest, JsonResponse
from django.http.response import HttpResponseBase
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.core.exceptions import ValidationError

from bm.exceptions import HTTPError, HTTPBadRequest, HTTP_VALIDATION_FAILED


class ParsedRequest(HttpRequest):
    data: Dict
    query_params: Dict

    @classmethod
    def from_request(cls, request: HttpRequest) -> 'ParsedRequest':     # type: ignore
        cls._prepare_request_data(request)
        return cast(ParsedRequest, request)

    @staticmethod
    def _prepare_request_data(request: HttpRequest) -> None:        # type: ignore
        assert request.content_type is not None
        request = cast(ParsedRequest, request)
        if request.content_type and 'json' in request.content_type:
            request.data = json.loads(request.body.decode('utf-8'))
        else:
            request.data = request.POST.dict()
        request.query_params = request.GET.dict()


class APIView(View):
    request: ParsedRequest

    @method_decorator(csrf_exempt)
    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:    # type: ignore
        try:
            self.request = request = ParsedRequest.from_request(request)
            try:
                response = super().dispatch(request, *args, **kwargs)
            except DataError as exc:
                raise HTTPBadRequest(code=HTTP_VALIDATION_FAILED, detail=exc.as_dict())
            except ValidationError as exc:
                raise HTTPBadRequest(code=HTTP_VALIDATION_FAILED, detail=exc.message_dict)
        except HTTPError as exc:
            return JsonResponse(exc.as_data(), status=exc.status)
        return response
