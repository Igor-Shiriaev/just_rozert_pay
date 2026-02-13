import os

from .settings import *  # NOQA

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql_psycopg2",
        "NAME": "rozert_pay",
        "USER": "rozert_pay",
        "PASSWORD": "rozert_pay",
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", 5432),
    },
}

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": os.environ.get("REDIS_HOST", "localhost"),
- "LOCATION": "redis://127.0.0.1:6379/1",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    },
}

CELERY_TASK_ALWAYS_EAGER = True

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

IS_UNITTESTS = True

REST_FRAMEWORK["TEST_REQUEST_RENDERER_CLASSES"] = (  # type: ignore[assignment] # noqa
    "rest_framework.renderers.MultiPartRenderer",
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.HTMLFormRenderer",
)
