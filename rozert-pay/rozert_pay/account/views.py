from typing import Any

from django.contrib.auth import logout
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.utils import extend_schema
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import NotAuthenticated
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rozert_pay.account import serializers
from rozert_pay.account.serializers import get_role_from_session


class CSRFExemptSessionAuthentication(SessionAuthentication):
    def enforce_csrf(self, request: Request) -> None:
        return


class CSRFExemptSessionAuthenticationSchema(OpenApiAuthenticationExtension):  # type: ignore
    target_class = "rozert_pay.account.views.CSRFExemptSessionAuthentication"
    name = "CSRFExemptSessionAuthentication"

    def get_security_definition(self, auto_schema: Any) -> list:
        return []


class LoginView(APIView):
    authentication_classes = [CSRFExemptSessionAuthentication]

    @extend_schema(
        request=serializers.LoginSerializer,
        responses={
            200: None,
            400: serializers.LoginRole(many=True),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = serializers.LoginSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.create(serializer.validated_data)
        return Response()


class AccountView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: serializers.AccountSerializer})
    def get(self, request: Request) -> Response:
        user = request.user
        assert user.is_authenticated
        if not get_role_from_session(request):
            raise NotAuthenticated()

        return Response(
            serializers.AccountSerializer(
                instance=user, context={"request": request}
            ).data
        )


@extend_schema(request=None)
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [CSRFExemptSessionAuthentication]

    @extend_schema(responses={200: None}, request=None)
    def post(self, request: Request) -> Response:
        logout(request)
        return Response()
