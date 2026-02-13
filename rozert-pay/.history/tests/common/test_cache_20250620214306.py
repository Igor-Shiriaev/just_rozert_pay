from datetime import timedelta
from functools import partial

from rozert_pay.common.helpers import cache


def test_cache():
    key1 = cache.CacheKey("key1")
    key2 = cache.CacheKey("key2")

    _state = 0

    def on_set():
        nonlocal _state
        _state += 1
        return _state

    call1 = partial(
        cache.memory_cache_get_set, key1, int, on_set, ttl=timedelta(hours=1)
    )
    call2 = partial(
        cache.memory_cache_get_set, key2, int, on_set, ttl=timedelta(hours=1)
    )

    assert call1() == 1
    assert call1() == 1
    assert call2() == 2
    assert call2() == 2

    cache.memory_cache_invalidate(key1)
    assert call1() == 3
    assert call2() == 2
