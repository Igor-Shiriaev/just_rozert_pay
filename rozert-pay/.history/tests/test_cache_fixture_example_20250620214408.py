from datetime import timedelta
from typing import List

from rozert_pay.common.helpers.cache import (CacheKey, memory_cache_get,
                                             memory_cache_get_set,
                                             memory_cache_set)


def test_cache_disabled_with_fixture(disable_cache):
    """Test that cache is disabled when using the disable_cache fixture."""
    key: CacheKey = CacheKey("test_key")
    
    # Test that memory_cache_get returns None when cache is disabled
    result = memory_cache_get(key, List[str])
    assert result is None
    
    # Test that memory_cache_set does nothing when cache is disabled
    test_data = ["item1", "item2"]
    memory_cache_set(key, test_data, timedelta(minutes=5))
    
    # Verify the data is not actually cached
    cached_result = memory_cache_get(key, List[str])
    assert cached_result is None


def test_cache_get_set_with_fixture(disable_cache):
    """Test that memory_cache_get_set calls the on_miss function when cache is disabled."""
    key: CacheKey = CacheKey("test_key")
    
    def on_miss() -> List[str]:
        return ["generated_item1", "generated_item2"]
    
    # Test that memory_cache_get_set calls on_miss and returns the result
    result = memory_cache_get_set(key, List[str], on_miss, timedelta(minutes=5))
    assert result == ["generated_item1", "generated_item2"]


def test_cache_works_without_fixture():
    """Test that cache works normally when fixture is not used."""
    key: CacheKey = CacheKey("test_key_normal")
    
    # Set a value in cache
    test_data = ["cached_item1", "cached_item2"]
    memory_cache_set(key, test_data, timedelta(minutes=5))
    
    # Get the value from cache
    cached_result = memory_cache_get(key, List[str])
    assert cached_result == test_data 