"""
Django settings for rozert pay project to run in Kubernetes env.
"""

import os  # noqa

from . import get_secrets_value  # noqa
from .settings import *  # noqa

CREDENTIALS_PATH = "/etc/credentials"  # Google credentials path
SECRETS_PATH = "/etc/secrets"  # Local helm secrets path

SECRET_KEY = get_secrets_value("SECRET_KEY", base_path=SECRETS_PATH)
ENCRYPTION_KEYS = [
    get_secrets_value("ENCRYPTION_KEYS", base_path=SECRETS_PATH),
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql_psycopg2",
        "NAME": os.environ.get("POSTGRES_DATABASE", "rozertpay"),
        "USER": os.environ.get("POSTGRES_USER", "rozertpay"),
        "PASSWORD": get_secrets_value("POSTGRES_PASSWORD", base_path=SECRETS_PATH),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", 5432),
    },
}

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": f"redis://:{get_secrets_value('REDIS_PASSWORD', base_path=SECRETS_PATH)}@{os.environ.get('REDIS_HOST', 'localhost')}:6379/1",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    },
}

RABBITMQ_HOST = os.environ.get("RABBITMQ_HOST", "mq-backend")
RABBITMQ_USER = os.environ.get("RABBITMQ_USER", "rozertpay")
RABBITMQ_PASSWORD = get_secrets_value("RABBITMQ_PASSWORD", base_path=SECRETS_PATH)
CELERY_BROKER_URL = (
    f"amqp://{RABBITMQ_USER}:{RABBITMQ_PASSWORD}@{RABBITMQ_HOST}:5672//rozertpay"
)

DEBUG = False
SENTRY_DSN = get_secrets_value("SENTRY_DSN", None, base_path=SECRETS_PATH)  # type: ignore

SLACK_TOKEN = get_secrets_value("SLACK_TOKEN", None, base_path=SECRETS_PATH)  # type: ignore

EXTERNAL_ROZERT_HOST = os.environ.get("EXTERNAL_ROZERT_HOST", "localhost")
