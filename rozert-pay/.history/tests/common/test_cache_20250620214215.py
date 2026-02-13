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


def test_cache_disabled_in_unittests():
    """Test that cache is disabled when IS_UNITTESTS is True"""
    key = cache.CacheKey("test_key")
    
    # Test that cache_get returns None when disabled
    result = cache.memory_cache_get(key, int)
    assert result is None
    
    # Test that cache_set does nothing when disabled
    cache.memory_cache_set(key, 42, timedelta(hours=1))
    result = cache.memory_cache_get(key, int)
    assert result is None
    
    # Test that cache_invalidate does nothing when disabled
    cache.memory_cache_invalidate(key)
    
    # Test that cache_get_set calls on_miss when disabled
    call_count = 0
    def on_miss():
        nonlocal call_count
        call_count += 1
        return 123
    
    result = cache.memory_cache_get_set(key, int, on_miss, timedelta(hours=1))
    assert result == 123
    assert call_count == 1
    
    # Second call should still call on_miss (no caching)
    result = cache.memory_cache_get_set(key, int, on_miss, timedelta(hours=1))
    assert result == 123
    assert call_count == 2
