from __future__ import annotations

import re
from typing import Any

from prometheus_client import generate_latest
from rozert_pay.common import metrics


def has_metric_line(metric: str, labels: dict[str, Any], value: int | float) -> bool:
    """
    Проверяет, что в экспозиции Prometheus присутствует строка метрики
    с указанными лейблами (порядок не важен) и значением.
    """
    text = generate_latest(metrics.prometheus_registry).decode("utf-8")
    lines = [line for line in text.splitlines() if line.startswith(metric)]
    for line in lines:
        if all(f'{k}="{v}"' in line for k, v in labels.items()) and re.search(
            rf"\s{value}(?:\.0+)?$", line
        ):
            return True
    return False
