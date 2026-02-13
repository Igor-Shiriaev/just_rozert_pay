from typing import Any

from django.db.models import URLField


class ImageURLField(URLField):
    MAX_LENGTH = 500

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.update(
            {
                'blank': True,
                'max_length': self.MAX_LENGTH,
                'null': True,
            }
        )
        super().__init__(*args, **kwargs)
