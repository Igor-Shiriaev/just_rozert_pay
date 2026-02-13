import logging
import time
from typing import Iterable

from django.db import models

logger = logging.getLogger(__name__)


class BigTableServices:
    @classmethod
    def get_ids_ranges_for_big_table(
        cls,
        model: type[models.Model],
        min_id: int | None = None,
        max_id: int | None = None,
        chunk_size: int = 1000,
        additional_q: models.Q = models.Q(),
    ) -> Iterable[list[int]]:
        # Returns
        left = min_id or 0
        qs: models.QuerySet[models.Model] = model.objects  # type: ignore[attr-defined]
        last = qs.last()
        if not last:
            return

        max_id = max_id or last.pk

        start = time.time()
        processed = 0

        while True:
            el = qs.filter(id__gt=left + chunk_size).order_by("id").first()
            right = min(el.pk, max_id) if el else max_id

            ids_to_return = list(
                qs.filter(
                    id__gte=left,
                    id__lte=right,
                )
                .filter(additional_q)
                .values_list("id", flat=True)
            )

            processed += right - left

            avg_items_per_sec = round(processed / (time.time() - start), 2) or 1
            remain_items = max_id - right
            remain_sec = round(remain_items / avg_items_per_sec, 2)
            logger.info(
                f"Remained {remain_items} items "
                f"(speed={round(avg_items_per_sec, 2)}it/s "
                f"remained={remain_sec}s)"
            )

            if ids_to_return:
                yield ids_to_return  # type: ignore

            left = right
            if right >= max_id:
                break
