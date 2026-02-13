import pytest
from rozert_pay.common.tasks import collect_rabbit_queues_metrics
from tests.helpers.prometheus import has_metric_line


@pytest.fixture(autouse=True)
def _rabbit_settings(settings):
    settings.RABBITMQ_HOST = "rabbit"
    settings.RABBITMQ_USER = "user"
    settings.RABBITMQ_PASSWORD = "pass"


def test_collect_rabbit_queues_metrics_sets_gauges_for_vhost(
    requests_mock, settings, monkeypatch
):
    settings.CELERY_BROKER_URL = "amqp://user:pass@rabbit:5672//rozertpay"
    # default management: http:15672

    queues_payload = [
        {
            "name": "high",
            "vhost": "rozertpay",
            "messages": 3,
            "consumers": 2,
            "messages_unacknowledged": 1,
            "messages_ready": 2,
        },
        {
            "name": "foreign",
            "vhost": "other",
            "messages": 100,
            "consumers": 0,
            "messages_unacknowledged": 0,
            "messages_ready": 100,
        },
    ]
    requests_mock.get(
        "http://rabbit:15672/api/queues", json=queues_payload, status_code=200
    )

    collect_rabbit_queues_metrics()

    labels = {"queue": "high", "vhost": "rozertpay"}

    assert has_metric_line("rozert_rabbit_queue_messages", labels, 3)
    assert has_metric_line("rozert_rabbit_queue_consumers", labels, 2)
    assert has_metric_line("rozert_rabbit_queue_messages_unacked", labels, 1)
    assert has_metric_line("rozert_rabbit_queue_messages_ready", labels, 2)

    # Ensure foreign vhost not present
    assert not has_metric_line(
        "rozert_rabbit_queue_messages", {"queue": "foreign", "vhost": "other"}, 100
    )


def test_collect_rabbit_queues_metrics_ignores_other_vhost(requests_mock, settings):
    settings.CELERY_BROKER_URL = "amqp://user:pass@rabbit:5672//myvhost"

    queues_payload = [
        {
            "name": "q1",
            "vhost": "other",
            "messages": 5,
            "consumers": 1,
            "messages_unacknowledged": 0,
            "messages_ready": 5,
        },
        {
            "name": "q2",
            "vhost": "myvhost",
            "messages": 7,
            "consumers": 3,
            "messages_unacknowledged": 2,
            "messages_ready": 5,
        },
    ]
    requests_mock.get(
        "http://rabbit:15672/api/queues", json=queues_payload, status_code=200
    )

    collect_rabbit_queues_metrics()

    assert not has_metric_line(
        "rozert_rabbit_queue_messages", {"queue": "q1", "vhost": "other"}, 5
    )
    assert has_metric_line(
        "rozert_rabbit_queue_messages", {"queue": "q2", "vhost": "myvhost"}, 7
    )


def test_collect_rabbit_queues_metrics_handles_errors(requests_mock, settings):
    settings.CELERY_BROKER_URL = "amqp://user:pass@rabbit:5672//rozertpay"

    requests_mock.get("http://rabbit:15672/api/queues", status_code=500)

    # Should not raise
    collect_rabbit_queues_metrics()

    # No assertions needed; just ensure it completes without exception.
