from datetime import timedelta
from functools import partial

import freezegun
from django.utils import timezone
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


def test_cleanup_cache_thread():
    now = timezone.now()
    _state = 0

    def on_set():
        nonlocal _state
        _state += 1
        return _state

    cache._cache = {}
    key = cache.CacheKey("key")

    call1 = partial(
        cache.memory_cache_get_set, key, int, on_set, ttl=timedelta(minutes=10)
    )
    with freezegun.freeze_time(now - timedelta(days=1)):
        assert call1() == 1
        assert cache.memory_cache_get(key, int) == 1

    assert len(cache._cache) == 1

    cache._CleanupCacheThread()._one_cycle(sleep=False)

    assert len(cache._cache) == 0
