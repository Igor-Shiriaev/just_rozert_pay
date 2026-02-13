from typing import Callable

from django.contrib import admin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import include, path, re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    generate_latest,
    multiprocess,
)
from rozert_pay.payment.api_v1.views import CallbackView


def allow_cors(view: Callable) -> Callable:  # type: ignore[type-arg]
    def wrapper(*args, **kwargs):  # type: ignore[no-untyped-def]
        response = view(*args, **kwargs)
        response["Access-Control-Allow-Origin"] = "*"
        return response

    return wrapper


def backoffice(request: HttpRequest) -> HttpResponse:
    return render(request, "backoffice.html")


def health(request: HttpRequest) -> HttpResponse:
    return HttpResponse("OK")


def prometheus_metrics(request: HttpRequest) -> HttpResponse:
    """
    Expose Prometheus metrics endpoint.

    Creates a new CollectorRegistry for each request to prevent metrics
    from registering themselves to a collector used by MultiProcessCollector.
    This avoids duplicate metrics: one for the multiprocess setup and one
    for the process serving the request.
    """
    # Create a new registry for each request (best practice for multiprocess)
    registry = CollectorRegistry()
    # Add multiprocess collector to aggregate metrics from all worker processes
    multiprocess.MultiProcessCollector(registry)  # type: ignore[no-untyped-call]
    # Generate metrics from the registry
    metrics = generate_latest(registry)
    return HttpResponse(metrics, content_type=CONTENT_TYPE_LATEST)


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/payment/v1/", include("rozert_pay.payment.api_v1.urls")),
    path("api/ps/<str:system>/", CallbackView.as_view(), name="callback_external"),
    path("api/backoffice/v1/", include("rozert_pay.payment.api_backoffice.urls")),
    path("api/account/v1/", include("rozert_pay.account.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "schema/public/",
        SpectacularAPIView.as_view(
            custom_settings={
                "PREPROCESSING_HOOKS": [
                    "rozert_pay.api_schema.public_schema_pre_process_hook"
                ]
            }
        ),
        name="schema-public",
    ),
    path(
        "redoc/public/",
        SpectacularRedocView.as_view(url_name="schema-public"),
        name="redoc-public",
    ),
    re_path("backoffice/.*", backoffice),
    re_path("health/?", health),
    re_path("metrics/?", prometheus_metrics),
]
